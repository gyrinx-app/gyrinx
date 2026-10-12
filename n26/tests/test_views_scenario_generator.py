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
from n26.flags import CAMPAIGNS
from n26.library.scenario_tables import table
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


def generated(client, campaign, **picks):
    response = client.get(generator_url(campaign), {"generate": "1", **picks})
    assert response.status_code == 302
    location = response["Location"]
    assert location.startswith(generator_url(campaign) + "?")
    return location, parse_qs(urlparse(location).query)


def test_the_page_opens_with_the_four_components_set_to_roll(client, campaign):
    response = client.get(generator_url(campaign))
    assert response.status_code == 200
    assert response.context["scenario"] == []
    form = response.context["form"]
    assert [field.label for field in form] == [
        "Deployment",
        "Objective",
        "Side job",
        "Crew",
    ]
    assert form.picks() == {
        "deployment": "roll",
        "objective": "roll",
        "side_job": "roll",
        "crew": "roll",
    }
    body = response.content.decode()
    assert "Roll a D6" in body and "Leave out" in body
    assert 'aria-label="Share"' not in body


def test_a_signed_out_reader_is_told_nothing_is_there(client, campaign):
    client.logout()
    assert client.get(generator_url(campaign)).status_code == 404


def test_generating_rolls_every_table_by_default(client, campaign):
    location, query = generated(client, campaign)
    assert set(query) == {"deployment", "objective", "side_job", "crew"}
    response = client.get(location)
    assert [result.table.key for result in response.context["scenario"]] == [
        "deployment",
        "objective",
        "side_job",
        "crew",
    ]
    body = response.content.decode()
    assert "Generate again" in body
    assert 'aria-label="Share"' in body


def test_a_pick_can_choose_an_entry_or_leave_a_table_out(client, campaign):
    location, query = generated(
        client, campaign, deployment_pick="3", side_job_pick="leave"
    )
    assert query["deployment"] == ["3"]
    assert "side_job" not in query
    assert {"objective", "crew"} <= set(query)
    # The picks ride the link, so generating again keeps them.
    assert query["deployment_pick"] == ["3"]
    assert query["side_job_pick"] == ["leave"]
    assert "objective_pick" not in query

    form = client.get(location).context["form"]
    assert form.picks()["deployment"] == "3"
    assert form.picks()["side_job"] == "leave"


def test_leaving_every_table_out_gives_an_empty_scenario(client, campaign):
    picks = {
        f"{each}_pick": "leave"
        for each in ("deployment", "objective", "side_job", "crew")
    }
    location, query = generated(client, campaign, **picks)
    assert not {"deployment", "objective", "side_job", "crew"} & set(query)
    assert client.get(location).context["scenario"] == []


def test_a_pick_that_is_not_an_option_is_refused(client, campaign):
    response = client.get(
        generator_url(campaign), {"generate": "1", "deployment_pick": "9"}
    )
    assert response.status_code == 200
    assert "Select an option for Deployment." in response.content.decode()


def test_a_link_with_a_component_off_its_table_shows_no_scenario(client, campaign):
    response = client.get(
        generator_url(campaign), {"deployment": "7", "objective": "2"}
    )
    assert response.context["scenario"] == []
    assert "not on its table" in response.content.decode()


class TestWhoGetsWhichButton:
    query = {"deployment": "3"}

    def test_the_arbitrator_may_save_record_and_share(self, client, campaign):
        response = client.get(generator_url(campaign), self.query)
        assert response.context["record_href"]
        assert response.context["save_href"] == f"{save_url(campaign)}?deployment=3"
        body = response.content.decode()
        assert "Save to log" in body
        assert 'aria-label="Share"' in body

    def test_a_player_may_save_record_and_share(self, client, campaign, player):
        response = client.get(generator_url(campaign), self.query)
        assert response.context["record_href"]
        assert response.context["save_href"]

    def test_anybody_else_may_only_share(self, client, campaign, stranger):
        response = client.get(generator_url(campaign), self.query)
        assert not response.context["record_href"]
        assert not response.context["save_href"]
        body = response.content.decode()
        assert "Save to log" not in body
        assert 'aria-label="Share"' in body


def saved_events():
    return CampaignEvent.objects.filter(kind=CampaignEvent.Kind.SCENARIO_SAVED)


class TestSaving:
    def test_the_save_page_shows_the_scenario_and_asks_for_a_name(
        self, client, campaign, player
    ):
        response = client.get(save_url(campaign), {"deployment": "6", "crew": "2"})
        assert response.status_code == 200
        assert [r.roll for r in response.context["scenario"]] == [6, 2]
        body = response.content.decode()
        assert "Scenario name" in body
        assert "Save scenario" in body
        assert 'type="hidden" name="deployment" value="6"' in body
        assert response.context["cancel_url"] == (
            f"{generator_url(campaign)}?deployment=6&crew=2#scenario"
        )

    def test_a_player_saves_a_named_scenario(self, client, campaign, player):
        response = client.post(
            save_url(campaign),
            {"deployment": "6", "crew": "2", "name": "Dust-up at the sump"},
        )
        assert response.status_code == 302
        assert response["Location"] == (
            f"{generator_url(campaign)}?deployment=6&crew=2#scenario"
        )
        saved = saved_events().get()
        assert saved.actor == player
        assert saved.note == "deployment=6,crew=2 Dust-up at the sump"

        acts = campaign_history(campaign, viewer=player)
        line = "".join(span.text for span in acts[-1].spans)
        assert line == (
            "saved the scenario Dust-up at the sump: "
            f"Deployment 6 ({name_of('deployment', 6)}), "
            f"Crew 2 ({name_of('crew', 2)})"
        )
        assert acts[-1].spans[0].href.startswith(generator_url(campaign) + "?")

    def test_the_arbitrator_saves_too(self, client, campaign):
        client.post(save_url(campaign), {"objective": "1", "name": "Grudge"})
        assert saved_events().get().actor == campaign.owner

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    def test_a_missing_or_long_name_is_shown_with_the_scenario_kept(
        self, client, campaign, player, name
    ):
        response = client.post(save_url(campaign), {"deployment": "1", "name": name})
        assert response.status_code == 200
        body = response.content.decode()
        assert "Enter a scenario name of up to 200 characters." in body
        assert 'type="hidden" name="deployment" value="1"' in body
        assert not saved_events().exists()

    def test_a_component_off_its_table_refuses_the_whole_scenario(
        self, client, campaign, player
    ):
        response = client.post(
            save_url(campaign),
            {"deployment": "7", "objective": "2", "name": "Grudge"},
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert "A scenario component is not on its table." in body
        assert 'value="Grudge"' in body
        assert not saved_events().exists()

    def test_nothing_to_save_is_refused(self, client, campaign, player):
        response = client.post(save_url(campaign), {"name": "Grudge"})
        assert "There is no scenario to save." in response.content.decode()
        assert not saved_events().exists()

    def test_a_stranger_cannot_save(self, client, campaign, stranger):
        assert client.get(save_url(campaign), {"deployment": "1"}).status_code == 404
        response = client.post(save_url(campaign), {"deployment": "1", "name": "x"})
        assert response.status_code == 404
        assert not saved_events().exists()

    def test_an_archived_campaign_cannot_be_saved_to(self, client, campaign):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.archive()
        response = client.post(save_url(campaign), {"deployment": "1", "name": "x"})
        assert response.status_code == 404


def test_the_campaign_page_offers_the_generator_to_every_reader(
    client, campaign, stranger
):
    body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert generator_url(campaign) in body
    assert "Record a battle" not in body


class TestRecordingTheResult:
    def add_url(self, campaign):
        return reverse("n26-campaign-add-battle", args=[campaign.pk])

    def test_record_a_battle_opens_the_battle_form_with_the_rolls(
        self, client, campaign
    ):
        response = client.get(generator_url(campaign), {"deployment": "6", "crew": "2"})
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
        assert "Scenario components" in body
        assert "View scenario details" in body
        assert 'type="hidden" name="deployment" value="6"' in body
        assert "Generate scenario" not in body

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
        assert [r.entry.label for r in page.context["scenario_results"]] == [
            name_of("deployment", 6),
            name_of("crew", 2),
        ]

        acts = campaign_history(campaign, viewer=player)
        line = "".join(span.text for span in acts[-1].spans)
        assert line == "recorded Ambush at the vents on 2026-10-06"

    def test_a_roll_off_the_table_is_refused_and_said(self, client, campaign):
        response = client.post(
            self.add_url(campaign),
            {"scenario": "Stand-off", "date": "2026-10-06", "deployment": "9"},
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert "A scenario component is not on its table." in body
        assert 'value="Stand-off"' in body
        assert not Battle.objects.exists()

    def test_a_link_with_a_component_off_its_table_attaches_nothing(
        self, client, campaign
    ):
        response = client.get(self.add_url(campaign), {"deployment": "7", "crew": "2"})
        assert response.context["scenario_results"] == []
        assert "not on its table" in response.content.decode()

    def test_an_error_keeps_the_scenario_and_what_was_entered(self, client, campaign):
        response = client.post(
            self.add_url(campaign),
            {"scenario": "Stand-off", "date": "", "deployment": "6", "crew": "2"},
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert 'value="Stand-off"' in body
        assert 'type="hidden" name="deployment" value="6"' in body
        assert [r.roll for r in response.context["scenario_results"]] == [6, 2]
        assert not Battle.objects.exists()

    def test_the_operation_refuses_a_roll_off_the_table(self, campaign):
        from datetime import date

        from n26.core.operations import Refusal

        with pytest.raises(Refusal):
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.record_battle(
                    date(2026, 10, 6),
                    scenario="Stand-off",
                    scenario_rolls={"deployment": 7, "crew": 2},
                )
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
        assert page.context["scenario_results"] == []
