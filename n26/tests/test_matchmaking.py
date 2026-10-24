"""Which campaign gangs the matchmaker offers, and whom each last fought."""

from datetime import date

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.matchmaking import campaign_entrants
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign
from n26.tests.test_views_campaigns import seat

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 19)
RESULT_TITLES = 'label[for^="matchmaker-result-"] .font-semibold'


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaign(arbitrator, campaign_type):
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator)


@pytest.fixture
def gangs(arbitrator, gang_type, campaign):
    made = {}
    for name in ("Adam", "Ben", "Chris", "David"):
        made[name] = found_gang(name, gang_type, owner=arbitrator)
        join_campaign(made[name], campaign)
    return made


def record(campaign, arbitrator, on, *gangs, result="draw", archived=False):
    with campaign_operation(campaign, actor=arbitrator) as act:
        battle = act.record_battle(on, gangs, scenario="Stand-off", result=result)
    if archived:
        battle.archive()
    return battle


def entrants(campaign):
    return {entrant.name: entrant for entrant in campaign_entrants(campaign, TODAY)}


def test_every_playing_gang_is_offered_by_name(campaign, gangs):
    assert list(entrants(campaign)) == ["Adam", "Ben", "Chris", "David"]
    assert all(entrant.available for entrant in entrants(campaign).values())


def test_a_battle_without_a_result_makes_its_gangs_unavailable(
    campaign, arbitrator, gangs
):
    record(
        campaign,
        arbitrator,
        date(2026, 10, 1),
        gangs["Adam"],
        gangs["Ben"],
        result="not_recorded",
    )
    found = entrants(campaign)
    assert not found["Adam"].available
    assert not found["Ben"].available
    assert found["Chris"].available


def test_a_battle_dated_after_today_makes_its_gangs_unavailable(
    campaign, arbitrator, gangs
):
    record(campaign, arbitrator, date(2026, 10, 26), gangs["Chris"], gangs["David"])
    found = entrants(campaign)
    assert not found["Chris"].available
    assert found["Adam"].available


def test_an_archived_battle_is_ignored(campaign, arbitrator, gangs):
    record(
        campaign,
        arbitrator,
        date(2026, 10, 26),
        gangs["Adam"],
        gangs["Ben"],
        archived=True,
    )
    found = entrants(campaign)
    assert found["Adam"].available
    assert found["Adam"].last_opponents == frozenset()


def test_only_the_latest_battle_names_last_opponents(campaign, arbitrator, gangs):
    record(campaign, arbitrator, date(2026, 9, 1), gangs["Adam"], gangs["Ben"])
    record(campaign, arbitrator, date(2026, 10, 1), gangs["Adam"], gangs["Chris"])
    found = entrants(campaign)
    assert found["Adam"].last_opponents == {str(gangs["Chris"].pk)}
    assert found["Adam"].last_size == 2
    assert found["Ben"].last_opponents == {str(gangs["Adam"].pk)}
    assert found["David"].last_opponents == frozenset()


def test_reading_the_campaign_takes_two_queries(
    campaign, arbitrator, gangs, django_assert_num_queries
):
    for day in range(1, 6):
        record(campaign, arbitrator, date(2026, 9, day), gangs["Adam"], gangs["Ben"])
    with django_assert_num_queries(2):
        campaign_entrants(campaign, TODAY)


class TestMatchmakerPage:
    def url(self, campaign):
        return reverse("n26-campaign-matchmaker", args=[campaign.pk])

    def draw(self, client, campaign, gangs, **params):
        params.setdefault("mode", "pairs")
        params.setdefault("matchups", 1)
        params["gangs"] = [str(gang.pk) for gang in gangs]
        page = client.get(self.url(campaign), params)
        assert page.status_code == 200
        return BeautifulSoup(page.content, "html.parser")

    def test_the_battles_menu_links_to_it_for_the_arbitrator(
        self, client, arbitrator, campaign
    ):
        client.force_login(arbitrator)
        page = client.get(reverse("n26-campaign", args=[campaign.pk]))
        assert self.url(campaign) in page.content.decode()

    def test_a_player_neither_sees_the_link_nor_reaches_the_page(
        self, client, campaign
    ):
        player = User.objects.create_user("player")
        seat(campaign, player)
        client.force_login(player)
        page = client.get(reverse("n26-campaign", args=[campaign.pk]))
        assert self.url(campaign) not in page.content.decode()
        assert client.get(self.url(campaign)).status_code == 404

    def test_unavailable_gangs_are_shown_without_a_checkbox(
        self, client, arbitrator, campaign, gangs
    ):
        record(
            campaign,
            arbitrator,
            date(2026, 10, 1),
            gangs["Adam"],
            result="not_recorded",
        )
        client.force_login(arbitrator)
        soup = BeautifulSoup(client.get(self.url(campaign)).content, "html.parser")
        ticks = {box["value"] for box in soup.select('input[name="gangs"]')}
        assert str(gangs["Adam"].pk) not in ticks
        assert str(gangs["Ben"].pk) in ticks
        assert "In a battle with no result yet" in soup.get_text()

    def test_pairs_are_drawn_without_a_rematch(
        self, client, arbitrator, campaign, gangs
    ):
        record(campaign, arbitrator, date(2026, 9, 1), gangs["Adam"], gangs["Ben"])
        record(campaign, arbitrator, date(2026, 9, 2), gangs["Chris"], gangs["David"])
        client.force_login(arbitrator)
        soup = self.draw(client, campaign, gangs.values(), matchups=2)
        titles = [title.get_text(strip=True) for title in soup.select(RESULT_TITLES)]
        assert len(titles) == 2
        for title in titles:
            assert title.startswith("Pre-made match")
            assert not {"Adam", "Ben"} <= set(title.split())
            assert not {"Chris", "David"} <= set(title.split())

    def test_drawing_saves_nothing(self, client, arbitrator, campaign, gangs):
        client.force_login(arbitrator)
        self.draw(client, campaign, gangs.values(), matchups=2)
        assert not campaign.battles.exists()

    @pytest.mark.parametrize(
        "params, message",
        [
            ({"matchups": 2}, "Select 4 gangs."),
            ({"matchups": 11}, "Enter a number of matchups from 1 to 10."),
            ({"mode": "more", "ways": 9}, "Enter a number of gangs from 2 to 8."),
        ],
    )
    def test_bad_settings_are_refused_and_kept(
        self, client, arbitrator, campaign, gangs, params, message
    ):
        client.force_login(arbitrator)
        soup = self.draw(client, campaign, [gangs["Adam"], gangs["Ben"]], **params)
        assert message in soup.get_text()
        assert not soup.select(RESULT_TITLES)
        kept = {box["value"] for box in soup.select('input[name="gangs"][checked]')}
        assert kept == {str(gangs["Adam"].pk), str(gangs["Ben"].pk)}

    @pytest.mark.parametrize(
        "params",
        [
            {"mode": "pairs"},
            {"mode": "pairs", "allow_uneven": "on"},
            {"mode": "more", "ways": 3},
        ],
    )
    def test_one_gang_alone_cannot_be_matched(
        self, client, arbitrator, campaign, gangs, params
    ):
        client.force_login(arbitrator)
        soup = self.draw(client, campaign, [gangs["Adam"]], **params)
        assert "Select at least 2 gangs." in soup.get_text()
        assert not soup.select(RESULT_TITLES)

    def test_it_asks_for_rematches_when_nothing_else_works(
        self, client, arbitrator, campaign, gangs
    ):
        record(campaign, arbitrator, date(2026, 9, 1), gangs["Adam"], gangs["Ben"])
        client.force_login(arbitrator)
        soup = self.draw(client, campaign, [gangs["Adam"], gangs["Ben"]])
        assert "Tick Allow rematches" in soup.get_text()
        soup = self.draw(
            client, campaign, [gangs["Adam"], gangs["Ben"]], allow_rematches="on"
        )
        assert soup.select(RESULT_TITLES)


class TestPreviewActions:
    """Pre-recording and redrawing the ticked results."""

    def url(self, campaign, query=""):
        return reverse("n26-campaign-matchmaker", args=[campaign.pk]) + query

    def draw(self, client, campaign, gangs, matchups=2):
        query = f"?mode=pairs&allow_rematches=on&matchups={matchups}" + "".join(
            f"&gangs={gang.pk}" for gang in gangs
        )
        soup = BeautifulSoup(
            client.get(self.url(campaign, query)).content, "html.parser"
        )
        token = soup.select_one('input[name="draw"]')["value"]
        return query, token, soup

    def post(self, client, campaign, query, token, action, selected):
        return client.post(
            self.url(campaign, query),
            {"draw": token, "action": action, "selected": selected},
        )

    @pytest.fixture
    def signed_in(self, client, arbitrator):
        client.force_login(arbitrator)
        return client

    def test_pre_recording_creates_the_ticked_battles(self, signed_in, campaign, gangs):
        from datetime import timedelta

        from django.utils import timezone

        from n26.core.models import CampaignEvent

        query, token, soup = self.draw(signed_in, campaign, gangs.values())
        title = soup.select_one('label[for="matchmaker-result-2"] .font-semibold')
        response = self.post(signed_in, campaign, query, token, "record", ["2"])
        assert response.status_code == 302
        assert response["Location"] == reverse("n26-campaign", args=[campaign.pk])
        battle = campaign.battles.get()
        assert battle.scenario == title.get_text(strip=True)
        assert battle.scenario.startswith("Pre-made match 2: ")
        assert battle.date == timezone.localdate() + timedelta(days=7)
        assert battle.result == "not_recorded"
        assert battle.gangs.count() == 2
        note = CampaignEvent.objects.get(
            battle=battle, kind=CampaignEvent.Kind.BATTLE_RECORDED
        ).note
        assert note.endswith(" - created from Matchmaker")

    def test_nothing_ticked_records_nothing(self, signed_in, campaign, gangs):
        query, token, _ = self.draw(signed_in, campaign, gangs.values())
        response = self.post(signed_in, campaign, query, token, "record", [])
        assert "Select at least one matchup to pre-record." in response.content.decode()
        assert not campaign.battles.exists()

    def test_one_result_cannot_be_rematched(self, signed_in, campaign, gangs):
        query, token, _ = self.draw(signed_in, campaign, gangs.values())
        response = self.post(signed_in, campaign, query, token, "rematch", ["1"])
        assert "Select more results to rematch." in response.content.decode()

    def test_rematching_proposes_new_pairs_from_the_same_gangs(
        self, signed_in, campaign, gangs
    ):
        query, token, before = self.draw(signed_in, campaign, gangs.values())

        def pairs(soup):
            return {
                li.select_one(".text-muted").get_text(" ", strip=True)
                for li in soup.select("form[method=post] li")
            }

        response = self.post(signed_in, campaign, query, token, "rematch", ["1", "2"])
        after = BeautifulSoup(response.content, "html.parser")
        assert len(pairs(after)) == 2
        assert not pairs(before) & pairs(after)
        assert not campaign.battles.exists()

    def test_a_changed_token_is_refused(self, signed_in, campaign, gangs):
        query, token, _ = self.draw(signed_in, campaign, gangs.values())
        response = self.post(signed_in, campaign, query, token + "x", "record", ["1"])
        assert "Make the matchup again." in response.content.decode()
        assert not campaign.battles.exists()

    def test_a_gang_busy_since_the_draw_is_refused(
        self, signed_in, campaign, arbitrator, gangs
    ):
        query, token, _ = self.draw(signed_in, campaign, gangs.values())
        record(
            campaign,
            arbitrator,
            date(2026, 10, 1),
            gangs["Adam"],
            result="not_recorded",
        )
        response = self.post(signed_in, campaign, query, token, "record", ["1", "2"])
        assert "can no longer be matched" in response.content.decode()
        assert campaign.battles.count() == 1

    def test_a_player_cannot_pre_record(self, client, signed_in, campaign, gangs):
        query, token, _ = self.draw(signed_in, campaign, gangs.values())
        player = User.objects.create_user("player")
        seat(campaign, player)
        client.force_login(player)
        response = self.post(client, campaign, query, token, "record", ["1"])
        assert response.status_code == 404
        assert not campaign.battles.exists()

    def test_the_operation_refuses_anyone_but_the_arbitrator(self, campaign, gangs):
        from django.utils import timezone

        from n26.core.operations import Refusal

        player = User.objects.create_user("player")
        seat(campaign, player)
        with pytest.raises(Refusal, match="Only the arbitrator"):
            with campaign_operation(campaign, actor=player) as act:
                act.pre_record_matchups(
                    [("Pre-made match 1: Adam vs Ben", [gangs["Adam"], gangs["Ben"]])],
                    today=timezone.localdate(),
                )


def test_the_page_does_not_query_per_gang_or_battle(
    client, arbitrator, campaign, gangs, gang_type
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(arbitrator)
    url = reverse("n26-campaign-matchmaker", args=[campaign.pk])

    def count():
        query = "?mode=pairs&allow_rematches=on&matchups=2" + "".join(
            f"&gangs={gang.pk}" for gang in gangs.values()
        )
        client.get(url + query)
        with CaptureQueriesContext(connection) as captured:
            assert client.get(url + query).status_code == 200
        return len(captured)

    small = count()
    for index in range(8):
        extra = found_gang(f"Extra {index}", gang_type, owner=arbitrator)
        join_campaign(extra, campaign)
        record(campaign, arbitrator, date(2026, 9, index + 1), extra, gangs["Adam"])
    assert count() == small
