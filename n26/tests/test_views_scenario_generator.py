"""The scenario generator page: rolling, choosing, and who may do what
with a result."""

from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import Battle, CampaignEvent
from n26.core.scenarios import stamp, table
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


def name_of(key, roll):
    return table(key).entry(roll).label


@pytest.fixture
def campaign(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    owner = User.objects.create_user("arb")
    client.force_login(owner)
    return found_campaign("Dust Falls", campaign_type, owner=owner)


@pytest.fixture
def player(client, campaign):
    player = User.objects.create_user("player")
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.invite(player)
    with campaign_operation(campaign, actor=player) as act:
        act.answer_invitation(player, accepted=True)
    client.force_login(player)
    return player


@pytest.fixture
def stranger(client, campaign):
    stranger = User.objects.create_user("stranger")
    client.force_login(stranger)
    return stranger


def generator_url(campaign):
    return reverse("n26-scenario-generator", args=[campaign.pk])


def save_url(campaign):
    return reverse("n26-save-scenario", args=[campaign.pk])


def rolled_result(client, campaign, **query):
    response = client.get(generator_url(campaign), {"roll": "1", **query})
    assert response.status_code == 302
    return response["Location"]


def test_the_page_opens_with_only_the_controls(client, campaign):
    response = client.get(generator_url(campaign))
    assert response.status_code == 200
    assert response.context["results"] == []
    assert "Copy scenario" not in response.content.decode()


def test_a_signed_out_reader_is_told_nothing_is_there(client, campaign):
    client.logout()
    assert client.get(generator_url(campaign)).status_code == 404


def test_a_full_roll_redirects_to_a_stamped_address_of_four_rolls(client, campaign):
    location = rolled_result(client, campaign, mode="full")
    query = parse_qs(urlparse(location).query)
    rolls = {
        key: int(query[key][0])
        for key in ("deployment", "objective", "side_job", "crew")
    }
    assert query["check"] == [stamp(campaign.pk, rolls)]

    response = client.get(location)
    assert [result.roll for result in response.context["results"]] == list(
        rolls.values()
    )
    assert response.context["rolled"] is True
    assert "table: rolled" in response.content.decode()


def test_components_roll_only_the_tables_ticked(client, campaign):
    location = rolled_result(
        client, campaign, mode="components", tables=["crew", "objective"]
    )
    query = parse_qs(urlparse(location).query)
    assert "deployment" not in query
    assert {"crew", "objective"} <= set(query)


def test_components_with_no_table_ticked_is_refused(client, campaign):
    response = client.get(generator_url(campaign), {"roll": "1", "mode": "components"})
    assert response.status_code == 200
    assert "Select at least one table to roll on." in response.content.decode()


def test_choosing_takes_the_picks_and_reads_as_chosen(client, campaign):
    location = rolled_result(client, campaign, mode="choose", deployment="2")
    assert "check" not in parse_qs(urlparse(location).query)
    response = client.get(location)
    assert response.context["rolled"] is False
    assert "Deployment table: chose 2" in response.content.decode()


def test_choosing_nothing_is_refused(client, campaign):
    response = client.get(generator_url(campaign), {"roll": "1", "mode": "choose"})
    assert "Select a result from at least one table." in response.content.decode()


def test_an_edited_roll_reads_as_chosen(client, campaign):
    rolls = {"deployment": 6, "crew": 2}
    check = stamp(campaign.pk, rolls)
    response = client.get(
        generator_url(campaign),
        {"mode": "full", "deployment": "1", "crew": "2", "check": check},
    )
    assert response.context["rolled"] is False


class TestWhoGetsWhichButton:
    def query(self, campaign):
        rolls = {"deployment": 3}
        return {
            "mode": "components",
            "tables": "deployment",
            **rolls,
            "check": stamp(campaign.pk, rolls),
        }

    def test_the_arbitrator_may_record_and_copy_but_not_save(self, client, campaign):
        response = client.get(generator_url(campaign), self.query(campaign))
        assert response.context["record_href"]
        assert not response.context["may_save"]
        assert "Copy scenario" in response.content.decode()

    def test_a_player_may_record_copy_and_save(self, client, campaign, player):
        response = client.get(generator_url(campaign), self.query(campaign))
        assert response.context["record_href"]
        assert response.context["may_save"]
        assert "Save to campaign log" in response.content.decode()

    def test_anybody_else_may_only_copy(self, client, campaign, stranger):
        response = client.get(generator_url(campaign), self.query(campaign))
        assert not response.context["record_href"]
        assert not response.context["may_save"]
        assert "Copy scenario" in response.content.decode()


class TestSaving:
    def test_a_player_saves_a_stamped_roll_as_rolled(self, client, campaign, player):
        rolls = {"deployment": 6, "crew": 2}
        response = client.post(
            save_url(campaign),
            {
                "deployment": "6",
                "crew": "2",
                "check": stamp(campaign.pk, rolls),
                "name": "Dust-up at the sump",
            },
        )
        assert response.status_code == 302
        saved = CampaignEvent.objects.get(kind=CampaignEvent.Kind.SCENARIO_SAVED)
        assert saved.actor == player
        assert saved.note == "rolled deployment=6,crew=2 Dust-up at the sump"

        acts = campaign_history(campaign, viewer=player)
        line = "".join(span.text for span in acts[-1].spans)
        assert line == (
            "rolled a scenario for Dust-up at the sump: "
            f"Deployment 6 ({name_of('deployment', 6)}), "
            f"Crew 2 ({name_of('crew', 2)})"
        )
        assert "check=" in acts[-1].spans[0].href

    def test_an_edited_roll_is_saved_as_chosen(self, client, campaign, player):
        check = stamp(campaign.pk, {"deployment": 6})
        client.post(
            save_url(campaign), {"deployment": "1", "check": check, "name": "Grudge"}
        )
        saved = CampaignEvent.objects.get(kind=CampaignEvent.Kind.SCENARIO_SAVED)
        assert saved.note == "chose deployment=1 Grudge"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    def test_a_scenario_needs_a_name(self, client, campaign, player, name):
        client.post(save_url(campaign), {"deployment": "1", "name": name})
        assert not CampaignEvent.objects.filter(
            kind=CampaignEvent.Kind.SCENARIO_SAVED
        ).exists()

    def test_nothing_to_save_is_refused(self, client, campaign, player):
        client.post(save_url(campaign), {"deployment": "9", "name": "Grudge"})
        assert not CampaignEvent.objects.filter(
            kind=CampaignEvent.Kind.SCENARIO_SAVED
        ).exists()

    def test_the_arbitrator_cannot_save(self, client, campaign):
        response = client.post(save_url(campaign), {"deployment": "1"})
        assert response.status_code == 404

    def test_a_stranger_cannot_save(self, client, campaign, stranger):
        response = client.post(save_url(campaign), {"deployment": "1"})
        assert response.status_code == 404

    def test_saving_needs_a_post(self, client, campaign, player):
        assert client.get(save_url(campaign)).status_code == 404


def test_the_campaign_page_offers_the_generator_to_every_reader(
    client, campaign, stranger
):
    body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert generator_url(campaign) in body
    assert "Record a battle" not in body


class TestRecordingTheResult:
    def add_url(self, campaign):
        return reverse("n26-campaign-add-battle", args=[campaign.pk])

    def test_record_result_opens_the_battle_form_with_the_rolls(self, client, campaign):
        rolls = {"deployment": 6, "crew": 2}
        response = client.get(
            generator_url(campaign),
            {"mode": "full", **rolls, "check": stamp(campaign.pk, rolls)},
        )
        assert response.context["record_href"] == (
            f"{self.add_url(campaign)}?deployment=6&crew=2"
        )

    def test_the_battle_form_shows_the_scenario_and_asks_for_a_name(
        self, client, campaign
    ):
        response = client.get(self.add_url(campaign), {"deployment": "6", "crew": "2"})
        assert response.status_code == 200
        assert [r.roll for r in response.context["scenario_results"]] == [6, 2]
        assert not response.context["form"]["scenario"].value()
        body = response.content.decode()
        assert "Generated scenario" in body
        assert 'type="hidden" name="deployment" value="6"' in body

    def test_recording_saves_the_rolls_with_the_battle(self, client, campaign, player):
        response = client.post(
            self.add_url(campaign),
            {
                "scenario": "Ambush at the vents",
                "date": "2026-10-06",
                "deployment": "6",
                "crew": "2",
            },
        )
        assert response.status_code == 302
        battle = Battle.objects.get(campaign=campaign)
        assert battle.scenario == "Ambush at the vents"
        assert battle.scenario_rolls == {"deployment": 6, "crew": 2}
        assert (
            campaign.events.get(kind=CampaignEvent.Kind.BATTLE_RECORDED).actor == player
        )

        page = client.get(reverse("n26-battle", args=[campaign.pk, battle.pk]))
        assert [r.entry.label for r in page.context["battle"].scenario_results] == [
            name_of("deployment", 6),
            name_of("crew", 2),
        ]
        assert "Crew table: 2" in page.content.decode()

        acts = campaign_history(campaign, viewer=player)
        line = "".join(span.text for span in acts[-1].spans)
        assert line == (
            "recorded a scenario for Ambush at the vents on 6 October: "
            f"Deployment 6 ({name_of('deployment', 6)}), Crew 2 ({name_of('crew', 2)})"
        )

    def test_a_roll_off_the_table_is_refused(self, client, campaign):
        response = client.post(
            self.add_url(campaign),
            {"scenario": "Stand-off", "date": "2026-10-06", "deployment": "9"},
        )
        assert response.status_code == 200
        assert not Battle.objects.exists()

    def test_a_battle_without_a_generated_scenario_stores_no_rolls(
        self, client, campaign
    ):
        client.post(
            self.add_url(campaign), {"scenario": "Stand-off", "date": "2026-10-06"}
        )
        battle = Battle.objects.get(campaign=campaign)
        assert battle.scenario_rolls == {}
        page = client.get(reverse("n26-battle", args=[campaign.pk, battle.pk]))
        assert "Crew table" not in page.content.decode()
