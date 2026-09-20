"""Battle pages, explicit results, permissions and fixed query growth."""

from datetime import date
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.crews import save_crew
from n26.core.forms import BattleForm
from n26.core.models import Battle, CampaignEvent, Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.post_battle import start_report
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def flag():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def arbitrator(client):
    user = User.objects.create_user("arbitrator")
    client.force_login(user)
    return user


@pytest.fixture
def campaign(arbitrator, campaign_type):
    return found_campaign("Dust Falls", campaign_type, owner=arbitrator)


@pytest.fixture
def gang(arbitrator, gang_type, campaign):
    gang = found_gang("The Ashen Choir", gang_type, owner=arbitrator)
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def battle(campaign, arbitrator, gang):
    with campaign_operation(campaign, actor=arbitrator) as act:
        return act.record_battle(date(2026, 8, 3), [gang], scenario="Stand-off")


def address(campaign, battle, suffix=""):
    return f"/n26/campaigns/{campaign.pk}/battles/{battle.pk}/{suffix}"


def fields(gang=None, **changes):
    return {
        "scenario": "Stand-off",
        "date": "2026-08-03",
        "result": "not_recorded",
        "gangs": [str(gang.pk)] if gang else [],
        "winners": [],
    } | changes


class TestBattleForm:
    def test_requires_scenario_date_and_explicit_result(self):
        form = BattleForm({}, playing=Gang.objects.none())
        assert not form.is_valid()
        assert set(form.errors) == {"scenario", "date", "result"}

    @pytest.mark.parametrize(
        "result,winners", [("draw", True), ("not_recorded", True), ("winners", False)]
    )
    def test_result_matches_winners(self, gang, result, winners):
        form = BattleForm(
            fields(gang, result=result, winners=[str(gang.pk)] if winners else []),
            playing=Gang.objects.all(),
        )
        assert not form.is_valid()
        assert "winners" in form.errors

    def test_winner_is_a_participant(self, gang):
        form = BattleForm(
            fields(result="winners", winners=[str(gang.pk)]), playing=Gang.objects.all()
        )
        assert not form.is_valid()
        assert "Every winner must be a participant." in form.errors["winners"]

    def test_outside_gang_is_not_a_choice(self, gang):
        form = BattleForm(
            fields(gang, result="winners", winners=[str(gang.pk)]),
            playing=Gang.objects.none(),
        )
        assert not form.is_valid()
        assert set(form.errors) == {"gangs", "winners"}


class TestBattlePages:
    def test_own_gang_first_with_shared_colour_and_type_flair(
        self, client, campaign, battle, gang, gang_type, flag, arbitrator, monkeypatch
    ):
        opponent = found_gang(
            "A rival gang", gang_type, owner=User.objects.create_user("rival")
        )
        join_campaign(opponent, campaign)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.edit_battle(
                battle,
                scenario=battle.scenario,
                date=battle.date,
                gangs=[opponent, gang],
                result=battle.result,
                winners=[],
                revision=battle.revision,
            )
        gang.colour = "amber"
        gang.save(update_fields=["colour"])
        monkeypatch.setattr(
            "n26.library.models.gang_type.read_artwork",
            lambda _: '<svg viewBox="0 0 16 16"><path d="M0 0h16v16H0z"/></svg>',
        )

        response = client.get(address(campaign, battle))
        assert response.context["participants"][0].id == str(gang.pk)
        soup = BeautifulSoup(response.content, "html.parser")
        first = soup.select_one('[aria-labelledby="battle-participants-heading"] li')
        assert gang.name in first.get_text()
        assert first.select_one(".n26-icon-inline svg") is not None
        assert "--color-amber-500" in first.select_one("[style]")["style"]

    def test_full_campaign_log_links_to_older_battle(
        self, client, campaign, battle, flag
    ):
        drawn = client.get(f"/n26/campaigns/{campaign.pk}/log/").content.decode()
        assert f'href="{address(campaign, battle)}"' in drawn

    def test_create_redirects_to_permanent_detail(self, client, campaign, gang, flag):
        response = client.post(
            f"/n26/campaigns/{campaign.pk}/battles/new/", fields(gang)
        )
        battle = Battle.objects.get(campaign=campaign)
        assert response.url == address(campaign, battle)
        response = client.get(response.url)
        assert response.status_code == 200
        assert "Stand-off" in response.content.decode()
        assert "Not recorded" in response.content.decode()
        assert "Edit battle" in response.content.decode()

    def test_legacy_detail_and_campaign_do_not_invent_results(
        self, client, campaign, flag
    ):
        legacy = Battle.objects.create(campaign=campaign, date=date(2026, 8, 3))
        detail = client.get(address(campaign, legacy)).content.decode()
        assert "Battle on 2026-08-03" in detail
        assert "Scenario not recorded." in detail
        assert "Not recorded" in detail
        campaign_page = client.get(f"/n26/campaigns/{campaign.pk}/").content.decode()
        assert address(campaign, legacy) in campaign_page
        assert "Not recorded" in campaign_page

    def test_edit_records_result_without_gang_changes(
        self, client, campaign, battle, gang, flag
    ):
        before = LedgerEvent.objects.count()
        response = client.post(
            address(campaign, battle, "edit/"),
            fields(
                gang,
                scenario="Ambush",
                result="winners",
                winners=[str(gang.pk)],
                revision=0,
            ),
        )
        assert response.status_code == 302
        battle.refresh_from_db()
        assert battle.scenario == "Ambush"
        assert battle.result == "winners"
        assert list(battle.winners.all()) == [gang]
        assert LedgerEvent.objects.count() == before
        assert "Won by The Ashen Choir" in client.get(response.url).content.decode()

    def test_invalid_form_preserves_choices(self, client, campaign, battle, gang, flag):
        response = client.post(
            address(campaign, battle, "edit/"),
            fields(gang, result="draw", winners=[str(gang.pk)], revision=0),
        )
        assert response.status_code == 200
        form = response.context["form"]
        assert "winners" in form.errors
        assert list(form["gangs"])[0].data["selected"]
        assert list(form["winners"])[0].data["selected"]
        assert response.content.decode().count(" checked") == 2
        battle.refresh_from_db()
        assert battle.result == "not_recorded"

    def test_stale_edit_is_explained_without_overwriting(
        self, client, campaign, battle, gang, flag
    ):
        url = address(campaign, battle, "edit/")
        assert (
            client.post(url, fields(gang, scenario="Ambush", revision=0)).status_code
            == 302
        )
        response = client.post(url, fields(gang, scenario="Old edit", revision=0))
        assert response.status_code == 200
        assert "This battle changed." in response.content.decode()
        battle.refresh_from_db()
        assert battle.scenario == "Ambush"
        assert (
            campaign.events.filter(kind=CampaignEvent.Kind.BATTLE_EDITED).count() == 1
        )

    def test_edit_keeps_departed_participant_selectable(
        self, client, campaign, battle, gang, arbitrator, flag
    ):
        with operation(gang, actor=arbitrator) as op:
            op.leave_campaign()
        response = client.get(address(campaign, battle, "edit/"))
        assert gang in response.context["form"].fields["gangs"].queryset
        response = client.post(
            address(campaign, battle, "edit/"),
            fields(gang, result="winners", winners=[str(gang.pk)], revision=0),
        )
        assert response.status_code == 302

    def test_attributed_history_blocks_remove_get_and_post(
        self, client, campaign, battle, gang, flag
    ):
        LedgerEvent.objects.create(
            gang=gang, campaign=campaign, battle=battle, kind=LedgerEvent.Kind.ADDED
        )
        url = address(campaign, battle, "remove/")
        detail = client.get(address(campaign, battle)).content.decode()
        assert url not in detail
        question = client.get(url).content.decode()
        assert 'type="submit"' not in question
        assert "cannot remove it" in question
        response = client.post(url, {"revision": battle.revision}, follow=True)
        assert (
            "cannot remove a battle with recorded gang history"
            in response.content.decode()
        )
        assert Battle.objects.filter(pk=battle.pk).exists()

    def test_remove_confirmation_posts_its_reviewed_version(
        self, client, campaign, battle, flag
    ):
        url = address(campaign, battle, "remove/")
        confirmation = BeautifulSoup(client.get(url).content, "html.parser")
        revision = confirmation.select_one('input[name="revision"]')["value"]
        assert revision == str(battle.revision)
        assert client.post(url, {"revision": revision}).status_code == 302
        assert not Battle.objects.filter(pk=battle.pk).exists()

    def test_an_old_removal_form_cannot_delete_newer_battle_details(
        self, client, campaign, battle, gang, flag
    ):
        url = address(campaign, battle, "remove/")
        confirmation = BeautifulSoup(client.get(url).content, "html.parser")
        revision = confirmation.select_one('input[name="revision"]')["value"]
        assert (
            client.post(
                address(campaign, battle, "edit/"),
                fields(gang, scenario="Ambush", revision=revision),
            ).status_code
            == 302
        )
        response = client.post(url, {"revision": revision}, follow=True)
        assert "This battle changed." in response.content.decode()
        assert "before removing it" in response.content.decode()
        battle.refresh_from_db()
        assert battle.scenario == "Ambush"
        assert battle.revision == int(revision) + 1
        assert not campaign.events.filter(
            kind=CampaignEvent.Kind.BATTLE_REMOVED
        ).exists()

    @pytest.mark.parametrize("data", [{}, {"revision": ""}, {"revision": "bad"}])
    def test_removal_requires_a_valid_confirmation_version(
        self, client, campaign, battle, flag, data
    ):
        response = client.post(address(campaign, battle, "remove/"), data, follow=True)
        assert "version is missing or invalid" in response.content.decode()
        assert Battle.objects.filter(pk=battle.pk).exists()

    @pytest.mark.parametrize("record", ["crew", "report"])
    def test_saved_crews_and_reports_block_both_the_question_and_removal(
        self, client, campaign, battle, gang, arbitrator, flag, record
    ):
        if record == "crew":
            save_crew(
                battle=battle,
                gang=gang,
                actor=arbitrator,
                revision=0,
                selections=[],
            )
        else:
            start_report(gang, battle=battle, actor=arbitrator, request_key=uuid4())
        url = address(campaign, battle, "remove/")
        response = client.get(url)
        assert response.status_code == 200
        assert 'type="submit"' not in response.content.decode()
        assert "This battle has saved gang records" in response.content.decode()
        assert "cannot remove it" in response.content.decode()
        response = client.post(url, {"revision": battle.revision}, follow=True)
        assert "cannot remove a battle with a saved crew" in response.content.decode()
        assert Battle.objects.filter(pk=battle.pk).exists()


class TestBattlePermissions:
    @pytest.mark.parametrize("suffix", ["", "edit/", "remove/"])
    def test_flag_off_blocks_get_and_post(self, client, campaign, battle, flag, suffix):
        flag.availability = Availability.OFF
        flag.save()
        url = address(campaign, battle, suffix)
        assert client.get(url).status_code == 404
        assert client.post(url, fields()).status_code == 404
        assert Battle.objects.filter(pk=battle.pk).exists()

    def test_non_owner_can_read_but_cannot_administer(
        self, client, campaign, battle, gang, flag
    ):
        player = User.objects.create_user("player")
        client.force_login(player)
        page = client.get(address(campaign, battle))
        assert page.status_code == 200
        drawn = page.content.decode()
        assert "Edit battle" not in drawn
        assert "Remove battle" not in drawn
        assert f"/n26/gangs/{gang.pk}/history/" not in drawn
        for url in (
            address(campaign, battle, "edit/"),
            address(campaign, battle, "remove/"),
            f"/n26/campaigns/{campaign.pk}/battles/new/",
        ):
            assert client.get(url).status_code == 404
            assert client.post(url, fields(gang, revision=0)).status_code == 404

    def test_gang_history_link_only_for_its_owner(
        self, client, campaign, battle, gang, flag
    ):
        drawn = client.get(address(campaign, battle)).content.decode()
        assert f"/n26/gangs/{gang.pk}/history/" in drawn

    @pytest.mark.parametrize("suffix", ["", "edit/", "remove/"])
    def test_foreign_or_invalid_battle_is_404(
        self, client, campaign, battle, campaign_type, arbitrator, flag, suffix
    ):
        foreign = found_campaign("Elsewhere", campaign_type, owner=arbitrator)
        for url in (
            address(foreign, battle, suffix),
            f"/n26/campaigns/{campaign.pk}/battles/not-an-id/{suffix}",
        ):
            assert client.get(url).status_code == 404
            assert client.post(url, fields(revision=0)).status_code == 404

    def test_anonymous_reader_does_not_reach_the_feature(
        self, client, campaign, battle, flag
    ):
        client.logout()
        response = client.get(address(campaign, battle))
        assert response.status_code == 404

    def test_flag_off_blocks_creation_get_and_post(self, client, campaign, flag):
        flag.availability = Availability.OFF
        flag.save()
        url = f"/n26/campaigns/{campaign.pk}/battles/new/"
        assert client.get(url).status_code == 404
        assert client.post(url, fields()).status_code == 404
        assert not Battle.objects.exists()


class TestBattleQueryGrowth:
    @pytest.mark.parametrize("screen", ["detail", "edit", "create", "campaign"])
    def test_participants_and_winners_add_no_queries(
        self, client, campaign, battle, gang, gang_type, arbitrator, flag, screen
    ):
        urls = {
            "detail": address(campaign, battle),
            "edit": address(campaign, battle, "edit/"),
            "create": f"/n26/campaigns/{campaign.pk}/battles/new/",
            "campaign": f"/n26/campaigns/{campaign.pk}/",
        }
        battle.result = "winners"
        battle.save(update_fields=["result"])
        battle.winners.add(gang)
        url = urls[screen]
        client.get(url)
        with CaptureQueriesContext(connection) as few:
            assert client.get(url).status_code == 200
        for index in range(3):
            extra = found_gang(f"Gang {index}", gang_type, owner=arbitrator)
            join_campaign(extra, campaign)
            battle.gangs.add(extra)
            battle.winners.add(extra)
        with CaptureQueriesContext(connection) as many:
            assert client.get(url).status_code == 200
        assert len(many) == len(few)

    def test_campaign_battle_rows_add_no_queries(
        self, client, campaign, battle, gang, arbitrator, flag
    ):
        url = f"/n26/campaigns/{campaign.pk}/"
        client.get(url)
        with CaptureQueriesContext(connection) as few:
            assert client.get(url).status_code == 200
        with campaign_operation(campaign, actor=arbitrator) as act:
            for day in range(4, 8):
                act.record_battle(
                    date(2026, 8, day),
                    [gang],
                    scenario="Stand-off",
                    result="winners",
                    winners=[gang],
                )
        with CaptureQueriesContext(connection) as many:
            assert client.get(url).status_code == 200
        assert len(many) == len(few)
