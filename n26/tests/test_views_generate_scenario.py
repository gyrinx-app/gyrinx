"""The scenario generator outside a campaign, from the N26 menu: rolling,
choosing, printing, and saving or recording in a campaign the reader
chooses. The generator inside a campaign is tested in
test_views_scenario_generator.py."""

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
from n26.core.models import CampaignEvent
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


def generator_url(campaign=None):
    """The generator's address. It belongs to no campaign; ``campaign`` is
    accepted so call sites can still say which campaign a test is about."""
    return reverse("n26-generate-scenario")


def save_url():
    return reverse("n26-generate-scenario-save")


def record_url():
    return reverse("n26-generate-scenario-record")


def print_url():
    return reverse("n26-scenario-print")


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


def test_a_signed_out_reader_is_sent_to_sign_in(client, campaign):
    client.logout()
    response = client.get(generator_url(campaign))
    assert response.status_code == 302
    assert response.url == f"/accounts/login/?next={generator_url(campaign)}"


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
    assert shared.context["form"].picks()["side_job"] == "leave"


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


class TestWhoGetsWhichAction:
    query = {"deployment": "3"}

    def test_the_arbitrator_may_print_save_and_record(self, client, campaign):
        response = client.get(generator_url(), self.query)
        assert response.context["may_record"]
        body = response.content.decode()
        assert f'href="{print_url()}?deployment=3"' in body
        assert "Save to campaign" in body
        assert "Record a battle" in body
        assert 'aria-label="Share"' in body

    def test_an_accepted_player_may_print_save_and_record(
        self, client, campaign, player
    ):
        assert client.get(generator_url(), self.query).context["may_record"]

    def test_somebody_with_no_campaign_may_only_print_and_share(
        self, client, campaign, stranger
    ):
        response = client.get(generator_url(), {**self.query, "dialog": "save"})
        assert not response.context["may_record"]
        assert response.context["dialog"] is None
        body = response.content.decode()
        assert f'href="{print_url()}?deployment=3"' in body
        assert "Save to campaign" not in body
        assert 'aria-label="Share"' in body

    def test_no_actions_without_a_scenario(self, client, campaign):
        response = client.get(generator_url())
        assert not response.context["may_record"]
        assert "Save to campaign" not in response.content.decode()


def saved_events():
    return CampaignEvent.objects.filter(kind=CampaignEvent.Kind.SCENARIO_SAVED)


@pytest.fixture
def archived(campaign_type, player):
    """A campaign the player had a place in, since archived."""
    owner = User.objects.create_user("old-arb")
    old = found_campaign("Old Feud", campaign_type, owner=owner)
    with campaign_operation(old, actor=owner) as act:
        act.invite(player)
    with campaign_operation(old, actor=player) as act:
        act.answer_invitation(player, accepted=True)
    with campaign_operation(old, actor=owner) as act:
        act.archive()
    return old


class TestTheCampaignDialogs:
    def test_the_save_dialog_lists_only_campaigns_the_reader_may_record_in(
        self, client, campaign, player, archived, campaign_type
    ):
        found_campaign("Ash Wastes", campaign_type, owner=player)
        found_campaign("Elsewhere", campaign_type, owner=User.objects.create_user("x"))
        response = client.get(generator_url(), {"deployment": "3", "dialog": "save"})
        assert response.context["dialog"] == "save"
        offered = [
            c.name for c in response.context["dialog_form"].fields["campaign"].queryset
        ]
        assert offered == ["Ash Wastes", "Dust Falls"]
        body = response.content.decode()
        assert "Save to campaign" in body
        assert 'type="hidden" name="deployment" value="3"' in body
        assert "Scenario name" in body

    def test_the_record_dialog_asks_only_for_the_campaign(
        self, client, campaign, player
    ):
        response = client.get(generator_url(), {"deployment": "3", "dialog": "record"})
        assert response.context["dialog"] == "record"
        assert "name" not in response.context["dialog_form"].fields
        assert response.context["dialog_action"] == record_url()

    def test_the_dialogs_keep_the_picks_for_the_way_back(self, client, campaign):
        location, query = generated(
            client, campaign, deployment_pick="3", side_job_pick="leave"
        )
        page = client.get(f"{location.split('#')[0]}&dialog=save")
        action = page.context["dialog_action"]
        assert parse_qs(urlparse(action).query) == {
            "deployment_pick": ["3"],
            "side_job_pick": ["leave"],
        }
        assert parse_qs(urlparse(page.context["dialog_cancel_url"]).query) == query


class TestSaving:
    def test_a_player_saves_a_named_scenario_to_a_campaign(
        self, client, campaign, player
    ):
        response = client.post(
            f"{save_url()}?side_job_pick=leave",
            {
                "campaign": campaign.pk,
                "deployment": "6",
                "crew": "2",
                "name": "Dust-up at the sump",
            },
        )
        assert response.status_code == 302
        assert parse_qs(urlparse(response["Location"]).query) == {
            "side_job_pick": ["leave"],
            "deployment": ["6"],
            "crew": ["2"],
        }
        saved = saved_events().get()
        assert saved.campaign == campaign
        assert saved.actor == player
        assert saved.note == "deployment=6,crew=2 Dust-up at the sump"

        acts = campaign_history(campaign, viewer=player)
        line = "".join(span.text for span in acts[-1].spans)
        assert line == (
            "saved the scenario Dust-up at the sump: "
            f"Deployment 6 ({name_of('deployment', 6)}), "
            f"Crew 2 ({name_of('crew', 2)})"
        )
        # The log links to the campaign's own generator, as every saved
        # scenario's line does.
        campaign_generator = reverse("n26-scenario-generator", args=[campaign.pk])
        assert acts[-1].spans[0].href.startswith(campaign_generator + "?")

    def test_the_arbitrator_saves_too(self, client, campaign):
        client.post(
            save_url(), {"campaign": campaign.pk, "objective": "1", "name": "G"}
        )
        assert saved_events().get().actor == campaign.owner

    @pytest.mark.parametrize("name", ["", "   ", "x" * 201])
    def test_a_missing_or_long_name_reopens_the_dialog_with_entries_kept(
        self, client, campaign, player, name
    ):
        response = client.post(
            save_url(), {"campaign": campaign.pk, "deployment": "1", "name": name}
        )
        assert response.status_code == 200
        assert response.context["dialog"] == "save"
        body = response.content.decode()
        assert "Enter a scenario name of up to 200 characters." in body
        assert 'type="hidden" name="deployment" value="1"' in body
        assert [r.roll for r in response.context["scenario"]] == [1]
        assert not saved_events().exists()

    def test_a_campaign_must_be_chosen(self, client, campaign, player):
        response = client.post(save_url(), {"deployment": "1", "name": "Grudge"})
        assert response.status_code == 200
        assert "Select a campaign." in response.content.decode()
        assert 'value="Grudge"' in response.content.decode()
        assert not saved_events().exists()

    def test_a_component_off_its_table_refuses_the_whole_scenario(
        self, client, campaign, player
    ):
        response = client.post(
            save_url(),
            {"campaign": campaign.pk, "deployment": "7", "objective": "2", "name": "G"},
        )
        assert response.status_code == 200
        assert "A scenario component is not on its table." in response.content.decode()
        assert not saved_events().exists()

    def test_nothing_to_save_is_refused(self, client, campaign, player):
        response = client.post(save_url(), {"campaign": campaign.pk, "name": "G"})
        assert "There is no scenario to save." in response.content.decode()
        assert not saved_events().exists()

    def test_a_campaign_the_reader_has_no_place_in_is_refused(
        self, client, campaign, stranger
    ):
        response = client.post(
            save_url(), {"campaign": campaign.pk, "deployment": "1", "name": "x"}
        )
        assert response.status_code == 200
        assert not saved_events().exists()

    def test_an_archived_campaign_is_refused(self, client, archived, player):
        client.post(
            save_url(), {"campaign": archived.pk, "deployment": "1", "name": "x"}
        )
        assert not saved_events().exists()

    def test_saving_needs_a_post(self, client, campaign, player):
        assert client.get(save_url()).status_code == 404


class TestRecordingFromTheGenerator:
    def test_the_dialog_takes_the_scenario_to_the_chosen_campaign(
        self, client, campaign, player
    ):
        response = client.post(
            record_url(), {"campaign": campaign.pk, "deployment": "6", "crew": "2"}
        )
        add = reverse("n26-campaign-add-battle", args=[campaign.pk])
        assert response["Location"] == f"{add}?deployment=6&crew=2"

    def test_a_campaign_must_be_chosen(self, client, campaign, player):
        response = client.post(record_url(), {"deployment": "6"})
        assert response.status_code == 200
        assert response.context["dialog"] == "record"
        assert "Select a campaign." in response.content.decode()

    def test_a_campaign_the_reader_has_no_place_in_is_refused(
        self, client, campaign, stranger
    ):
        response = client.post(
            record_url(), {"campaign": campaign.pk, "deployment": "6"}
        )
        assert response.status_code == 200
        assert "Select one of your campaigns." in response.content.decode()


class TestPrinting:
    def test_the_print_page_shows_each_component_in_order_with_the_map(
        self, client, campaign
    ):
        response = client.get(
            print_url(), {"crew": "3", "deployment": "4", "side_job_pick": "leave"}
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
        assert name_of("crew", 3) in body
        assert parse_qs(urlparse(response.context["back_url"]).query) == {
            "side_job_pick": ["leave"],
            "deployment": ["4"],
            "crew": ["3"],
        }

    def test_any_signed_in_reader_may_print(self, client, campaign, stranger):
        assert client.get(print_url(), {"deployment": "4"}).status_code == 200

    @pytest.mark.parametrize("query", [{}, {"deployment": "7"}])
    def test_nothing_to_print_is_not_found(self, client, campaign, query):
        assert client.get(print_url(), query).status_code == 404


def test_the_menu_offers_this_generator_and_the_campaign_keeps_its_own(
    client, campaign
):
    body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert f'href="{generator_url()}"' in body
    assert "Scenario generator" in body
    campaign_generator = reverse("n26-scenario-generator", args=[campaign.pk])
    assert f'href="{campaign_generator}"' in body
    assert "Generate scenario" in body
    assert "Record battle" in body
