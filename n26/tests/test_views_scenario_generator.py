"""The scenario generator page: rolling, choosing, and who may do what
with a result."""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import Battle, CampaignEvent
from n26.library.scenario_tables import table
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


def name_of(key, roll):
    return table(key).entry(roll).label


@pytest.fixture
def campaign(client, campaign_type):
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


def test_the_page_opens_with_three_components_to_roll_and_a_side_job_to_choose(
    client, campaign
):
    response = client.get(generator_url(campaign))
    assert response.status_code == 200
    assert response.context["scenario"] == []
    form = response.context["form"]
    assert [field.label for field in form] == [
        "Deployment",
        "Objective",
        "Crew",
        "Side job 1",
    ]
    assert form.picks() == {
        "deployment": "roll",
        "objective": "roll",
        "crew": "roll",
    }
    assert form.side_job_picks() == [""]
    body = response.content.decode()
    assert "Roll a D6" in body and "Leave out" in body
    assert 'aria-label="Share result"' not in body


def test_a_signed_out_reader_is_sent_to_sign_in(client, campaign):
    client.logout()
    response = client.get(generator_url(campaign))
    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={generator_url(campaign)}"


def test_generating_rolls_every_table_and_no_side_job_by_default(client, campaign):
    location, query = generated(client, campaign)
    assert set(query) == {"deployment", "objective", "crew"}
    response = client.get(location)
    assert [result.table.key for result in response.context["scenario"]] == [
        "deployment",
        "objective",
        "crew",
    ]
    body = response.content.decode()
    assert "Generate again" in body
    assert 'aria-label="Share result"' in body


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
    assert form.side_job_picks() == ["leave"]


def test_sharing_keeps_query_separators_and_reproduces_the_complete_result(
    client, campaign
):
    location, query = generated(
        client, campaign, deployment_pick="3", side_job_pick="leave"
    )
    response = client.get(location)
    soup = BeautifulSoup(response.content, "html.parser")
    host = soup.select_one('[data-react-name="share"]')
    props = json.loads(soup.find(id=host["data-react-props"]).string)
    assert props["url"] == response.wsgi_request.get_full_path()
    assert "&amp;" not in props["url"]
    shared = client.get(props["url"])
    assert [r.roll for r in shared.context["scenario"]] == [
        int(query[key][0]) for key in ("deployment", "objective", "crew")
    ]
    assert shared.context["form"].picks()["deployment"] == "3"
    assert shared.context["form"].side_job_picks() == ["leave"]


def test_leaving_every_table_out_explains_that_a_component_is_needed(client, campaign):
    picks = {
        f"{each}_pick": "leave"
        for each in ("deployment", "objective", "side_job", "crew")
    }
    response = client.get(generator_url(campaign), {"generate": "1", **picks})
    assert response.status_code == 200
    assert response.context["scenario"] == []
    assert (
        "Select at least one component to roll or include." in response.content.decode()
    )
    assert set(response.context["form"].picks().values()) == {"leave"}


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


def test_rendering_more_components_does_not_add_database_queries(client, campaign):
    one = {"deployment": "3"}
    four = {"deployment": "3", "objective": "2", "side_job": "1", "crew": "6"}
    for query in (one, four):
        client.get(generator_url(campaign), query)
    with CaptureQueriesContext(connection) as single:
        response = client.get(generator_url(campaign), one)
    assert response.status_code == 200
    with CaptureQueriesContext(connection) as complete:
        response = client.get(generator_url(campaign), four)
    assert response.status_code == 200
    assert len(response.context["scenario"]) == 4
    assert len(complete) == len(single)


class TestWhoGetsWhichButton:
    query = {"deployment": "3"}

    def test_the_arbitrator_may_save_record_and_share(self, client, campaign):
        response = client.get(generator_url(campaign), self.query)
        assert response.context["record_href"]
        assert response.context["save_href"] == f"{save_url(campaign)}?deployment=3"
        body = response.content.decode()
        assert "Save to log" in body
        assert 'aria-label="Share result"' in body

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
        assert 'aria-label="Share result"' in body


def saved_events():
    return CampaignEvent.objects.filter(kind=CampaignEvent.Kind.SCENARIO_SAVED)


class TestSaving:
    def test_saving_and_cancelling_keep_chosen_and_omitted_components(
        self, client, campaign
    ):
        location, query = generated(
            client, campaign, deployment_pick="3", side_job_pick="leave"
        )
        page = client.get(location)
        saving = client.get(page.context["save_href"])
        expected = {key: value[0] for key, value in query.items()}
        assert parse_qs(urlparse(saving.context["cancel_url"]).query) == query
        action = saving.context["action_url"]
        assert parse_qs(urlparse(action).query) == {
            "deployment_pick": ["3"],
            "side_job_pick": ["leave"],
        }

        invalid = client.post(action, {**expected, "name": " "})
        assert invalid.status_code == 200
        assert invalid.context["action_url"] == action
        assert parse_qs(urlparse(invalid.context["cancel_url"]).query) == query
        saved = client.post(action, {**expected, "name": "The sump crossing"})
        assert saved.status_code == 302
        assert parse_qs(urlparse(saved.url).query) == query
        again = client.get(saved.url)
        assert again.context["form"].picks()["deployment"] == "3"
        assert again.context["form"].side_job_picks() == ["leave"]

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


def test_the_campaign_page_keeps_the_generator_in_shared_navigation(
    client, campaign, stranger
):
    body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert generator_url(campaign) not in body
    assert reverse("n26-generate-scenario") in body
    assert "Record battle" not in body


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
        assert "Scenario" in body
        assert "Full details" in body
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

    def test_an_invalid_component_cannot_disappear_on_a_second_submit(
        self, client, campaign
    ):
        response = client.post(
            self.add_url(campaign),
            {
                "scenario": "Stand-off",
                "date": "2026-10-06",
                "deployment": "9",
                "crew": "2",
            },
        )
        form = BeautifulSoup(response.content, "html.parser").select_one(
            "form[method=post]"
        )
        hidden = {
            field["name"]: field.get("value", "")
            for field in form.select("input[type=hidden][name]")
        }
        assert hidden["deployment"] == "9"
        assert hidden["crew"] == "2"
        repeated = client.post(
            self.add_url(campaign),
            {**hidden, "scenario": "Stand-off", "date": "2026-10-06"},
        )
        assert repeated.status_code == 200
        assert "not on its table" in repeated.content.decode()
        assert not Battle.objects.exists()

    def test_a_link_with_a_component_off_its_table_attaches_nothing(
        self, client, campaign
    ):
        response = client.get(self.add_url(campaign), {"deployment": "7", "crew": "2"})
        assert response.context["scenario_results"] == []
        assert "not on its table" in response.content.decode()
        soup = BeautifulSoup(response.content, "html.parser")
        fields = {
            field["name"]: field.get("value", "")
            for field in soup.select("form[method=post] input[type=hidden][name]")
        }
        assert fields["deployment"] == "7"
        assert fields["crew"] == "2"
        submitted = client.post(
            self.add_url(campaign),
            {**fields, "scenario": "Stand-off", "date": "2026-10-06"},
        )
        assert submitted.status_code == 200
        assert not Battle.objects.exists()

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

    @pytest.mark.parametrize("value", [7, 3.5, True])
    def test_the_operation_refuses_a_roll_off_the_table(self, campaign, value):
        from datetime import date

        from n26.core.operations import Refusal

        with pytest.raises(Refusal):
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.record_battle(
                    date(2026, 10, 6),
                    scenario="Stand-off",
                    scenario_rolls={"deployment": value, "crew": 2},
                )
        assert not Battle.objects.exists()

    def test_archiving_and_restoring_a_battle_keeps_its_components(
        self, client, campaign
    ):
        from datetime import date

        components = {"deployment": 3, "crew": 2}
        with campaign_operation(campaign, actor=campaign.owner) as act:
            battle = act.record_battle(
                date(2026, 10, 25),
                scenario="The sump crossing",
                scenario_rolls=components,
            )
            act.remove_battle(battle, revision=battle.revision)
        battle.refresh_from_db()
        assert battle.archived
        assert battle.scenario_rolls == components
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.restore_battle(battle, revision=battle.revision)
        battle.refresh_from_db()
        assert not battle.archived
        assert battle.scenario_rolls == components
        page = client.get(reverse("n26-battle", args=[campaign.pk, battle.pk]))
        assert [result.roll for result in page.context["scenario_results"]] == [3, 2]

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


def campaign_print_url(campaign):
    return reverse("n26-campaign-scenario-print", args=[campaign.pk])


class TestPrintingFromTheCampaign:
    def test_print_comes_first_for_whoever_may_record(self, client, campaign):
        response = client.get(
            generator_url(campaign), {"deployment": "4", "side_job_pick": "leave"}
        )
        body = response.content.decode()
        print_link = f'href="{campaign_print_url(campaign)}?side_job_pick=leave&amp;deployment=4"'
        assert print_link in body
        assert body.index(print_link) < body.index("Save to log")

    def test_a_reader_who_may_not_record_may_still_print(
        self, client, campaign, stranger
    ):
        body = client.get(generator_url(campaign), {"deployment": "4"}).content.decode()
        assert f'href="{campaign_print_url(campaign)}?deployment=4"' in body
        assert "Save to log" not in body

    def test_the_print_page_returns_to_the_campaign_generator(self, client, campaign):
        response = client.get(
            campaign_print_url(campaign),
            {"crew": "3", "deployment": "4", "side_job_pick": "leave"},
        )
        assert response.status_code == 200
        assert [r.table.key for r in response.context["scenario"]] == [
            "deployment",
            "crew",
        ]
        body = response.content.decode()
        assert "Your scenario" in body
        assert "window.print()" in body
        assert "scenarios/deployment-4.png" in body
        back = urlparse(response.context["back_url"])
        assert back.path == generator_url(campaign)
        assert parse_qs(back.query) == {
            "side_job_pick": ["leave"],
            "deployment": ["4"],
            "crew": ["3"],
        }

    @pytest.mark.parametrize("query", [{}, {"deployment": "7"}])
    def test_nothing_to_print_is_not_found(self, client, campaign, query):
        assert client.get(campaign_print_url(campaign), query).status_code == 404

    def test_an_unknown_campaign_is_not_found(self, client, campaign):
        url = reverse(
            "n26-campaign-scenario-print", args=["01ARZ3NDEKTSV4RRFFQ69G5FAV"]
        )
        assert client.get(url, {"deployment": "4"}).status_code == 404
