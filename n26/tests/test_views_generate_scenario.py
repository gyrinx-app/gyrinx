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


class TestWhoGetsWhichAction:
    query = {"deployment": "3"}

    def test_the_arbitrator_may_print_save_and_record(self, client, campaign):
        response = client.get(generator_url(), self.query)
        assert response.context["may_record"]
        body = response.content.decode()
        assert f'href="{print_url()}?deployment=3"' in body
        assert "Connect to battle" in body
        assert "Create a battle" in body
        assert 'aria-label="Share result"' in body

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
        assert "Connect to battle" not in body
        assert 'aria-label="Share result"' in body

    def test_no_actions_without_a_scenario(self, client, campaign):
        response = client.get(generator_url())
        assert not response.context["may_record"]
        assert "Connect to battle" not in response.content.decode()


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
        assert offered == ["Ash Wastes"]
        body = response.content.decode()
        assert "Connect to battle" in body
        assert response.context["scenario_dialog"]["rolls"] == {"deployment": 3}
        assert "name" not in response.context["dialog_form"].fields

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


@pytest.fixture
def battle(campaign):
    from datetime import date

    with campaign_operation(campaign, actor=campaign.owner) as act:
        return act.record_battle(date(2026, 10, 26), scenario="Sump clash")


def connection_data(campaign, battle, **extra):
    return {
        "campaign": str(campaign.pk),
        "battle": str(battle.pk),
        "revision": battle.revision,
        "deployment": "6",
        "crew": "2",
        **extra,
    }


class TestConnecting:
    def test_connecting_keeps_the_battle_name_and_records_the_change(
        self, client, campaign, battle
    ):
        response = client.post(save_url(), connection_data(campaign, battle))
        assert response.status_code == 302
        assert response["Location"] == reverse(
            "n26-battle", args=[campaign.pk, battle.pk]
        )
        battle.refresh_from_db()
        assert battle.scenario == "Sump clash"
        assert battle.scenario_rolls == {"deployment": 6, "crew": 2}
        assert battle.revision == 1
        assert (
            CampaignEvent.objects.filter(
                battle=battle, kind=CampaignEvent.Kind.BATTLE_EDITED
            ).count()
            == 1
        )
        assert not saved_events().exists()

    def test_selecting_a_campaign_lists_its_battles_and_no_others(
        self, client, campaign, battle, campaign_type
    ):
        from datetime import date

        other = found_campaign("Other", campaign_type, owner=campaign.owner)
        with campaign_operation(other, actor=other.owner) as act:
            act.record_battle(date(2026, 10, 26), scenario="Other battle")
        response = client.get(
            generator_url(),
            {"deployment": "3", "dialog": "save", "campaign": str(campaign.pk)},
        )
        offered = response.context["scenario_dialog"]["battles"]
        assert [b["value"] for b in offered] == [str(battle.pk)]
        assert "name" not in response.context["dialog_form"].fields

    def test_battles_are_not_loaded_until_a_campaign_is_chosen(
        self, client, campaign, battle
    ):
        response = client.get(generator_url(), {"deployment": "3", "dialog": "save"})
        assert response.context["scenario_dialog"]["battles"] == []

    def test_a_battle_from_another_campaign_is_refused(
        self, client, campaign, battle, campaign_type
    ):
        other = found_campaign("Other", campaign_type, owner=campaign.owner)
        response = client.post(save_url(), connection_data(other, battle))
        assert "battle" in response.context["dialog_form"].errors
        battle.refresh_from_db()
        assert battle.scenario_rolls == {}

    def test_an_accepted_player_cannot_amend_an_existing_battle(
        self, client, campaign, battle, player
    ):
        assert not client.get(generator_url(), {"deployment": "3"}).context[
            "may_connect"
        ]
        response = client.post(save_url(), connection_data(campaign, battle))
        assert "campaign" in response.context["dialog_form"].errors
        battle.refresh_from_db()
        assert battle.scenario_rolls == {}
        from n26.core.operations import Refusal

        with pytest.raises(Refusal, match="Only the arbitrator"):
            with campaign_operation(campaign, actor=player) as act:
                act.connect_scenario(battle, {"crew": 2}, revision=0)

    def test_a_stale_revision_does_not_overwrite_a_later_scenario(
        self, client, campaign, battle
    ):
        data = connection_data(campaign, battle)
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.connect_scenario(battle, {"crew": 1}, revision=0)
        response = client.post(save_url(), data)
        assert "This battle changed." in response.content.decode()
        battle.refresh_from_db()
        assert battle.scenario_rolls == {"crew": 1}
        assert response.context["scenario_dialog"]["rolls"] == {
            "deployment": 6,
            "crew": 2,
        }

    @pytest.mark.parametrize("component", ["7", "bad"])
    def test_an_invalid_component_does_not_change_the_battle(
        self, client, campaign, battle, component
    ):
        response = client.post(
            save_url(), connection_data(campaign, battle, deployment=component)
        )
        assert response.status_code == 200
        assert response.context["dialog_form"].errors
        battle.refresh_from_db()
        assert battle.scenario_rolls == {}

    def test_an_empty_scenario_is_refused(self, client, campaign, battle):
        data = connection_data(campaign, battle)
        del data["deployment"], data["crew"]
        response = client.post(save_url(), data)
        assert response.context["dialog_form"].errors
        battle.refresh_from_db()
        assert battle.scenario_rolls == {}

    def test_an_archived_battle_is_not_offered_or_changed(
        self, client, campaign, battle
    ):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.remove_battle(battle, revision=0)
        response = client.post(save_url(), connection_data(campaign, battle))
        assert "battle" in response.context["dialog_form"].errors
        assert response.context["scenario_dialog"]["battles"] == []

    def test_an_archived_campaign_is_refused(self, client, campaign, battle):
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.archive()
        response = client.post(save_url(), connection_data(campaign, battle))
        assert "campaign" in response.context["dialog_form"].errors

    def test_a_missing_battle_reopens_the_dialog(self, client, campaign, battle):
        data = connection_data(campaign, battle)
        del data["battle"]
        response = client.post(save_url(), data)
        assert "battle" in response.context["dialog_form"].errors
        assert response.context["dialog"] == "save"

    def test_repeating_the_connection_does_not_add_another_event(
        self, client, campaign, battle
    ):
        client.post(save_url(), connection_data(campaign, battle))
        battle.refresh_from_db()
        client.post(save_url(), connection_data(campaign, battle))
        assert (
            CampaignEvent.objects.filter(
                battle=battle, kind=CampaignEvent.Kind.BATTLE_EDITED
            ).count()
            == 1
        )

    def test_more_battles_do_not_add_queries_per_battle(self, client, campaign, battle):
        from datetime import date

        query = {"deployment": "3", "dialog": "save", "campaign": str(campaign.pk)}
        client.get(generator_url(), query)
        with CaptureQueriesContext(connection) as small:
            client.get(generator_url(), query)
        with campaign_operation(campaign, actor=campaign.owner) as act:
            for i in range(12):
                act.record_battle(date(2026, 10, 26), scenario=f"Battle {i}")
        with CaptureQueriesContext(connection) as large:
            response = client.get(generator_url(), query)
        assert len(response.context["scenario_dialog"]["battles"]) == 13
        assert len(large) <= len(small)

    def test_connecting_requires_a_post(self, client, campaign):
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


def test_the_menu_offers_the_generator_without_a_campaign_header_button(
    client, campaign
):
    body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    assert f'href="{generator_url()}"' in body
    assert "Scenario generator" in body
    campaign_generator = reverse("n26-scenario-generator", args=[campaign.pk])
    assert f'href="{campaign_generator}"' not in body
    assert "Generate scenario" not in body
    assert "Record battle" in body


def test_inline_generation_returns_the_chosen_result_without_saving(client, campaign):
    response = client.get(
        generator_url(),
        {
            "generate": "1",
            "format": "json",
            "deployment_pick": "4",
            "side_job_pick": "leave",
        },
    )
    assert response.status_code == 200
    rolls = response.json()["rolls"]
    assert rolls["deployment"] == 4
    assert "side_job" not in rolls
    assert set(rolls) == {"deployment", "objective", "crew"}
    assert not saved_events().exists()


def test_inline_generation_reports_an_empty_selection(client, campaign):
    response = client.get(
        generator_url(),
        {
            "generate": "1",
            "format": "json",
            **{
                key + "_pick": "leave"
                for key in ("deployment", "objective", "side_job", "crew")
            },
        },
    )
    assert response.status_code == 400
    assert response.json()["errors"]


def test_a_battle_link_keeps_its_campaign_and_battle_when_generating(
    client, campaign, battle
):
    response = client.get(
        generator_url(),
        {"generate": "1", "campaign": str(campaign.pk), "battle": str(battle.pk)},
    )
    query = parse_qs(urlparse(response["Location"]).query)
    assert query["campaign"] == [str(campaign.pk)]
    assert query["battle"] == [str(battle.pk)]
    page = client.get(response["Location"])
    connection = client.get(page.context["save_url"])
    assert connection.context["scenario_dialog"]["battle"] == str(battle.pk)
    assert connection.context["scenario_dialog"]["revision"] == battle.revision


def test_an_invalid_battle_link_does_not_expose_another_battle(client, campaign):
    response = client.get(
        generator_url(),
        {
            "deployment": "1",
            "dialog": "save",
            "campaign": str(campaign.pk),
            "battle": "not-an-id",
        },
    )
    assert response.status_code == 200
    assert response.context["scenario_dialog"]["revision"] is None


def test_battle_creation_accepts_an_optional_name_and_generated_components(
    client, campaign
):
    from n26.core.models import Battle

    url = reverse("n26-campaign-add-battle", args=[campaign.pk])
    page = client.get(url)
    assert not page.context["form"].fields["scenario"].required
    assert page.context["form"].fields["scenario"].label == "Name"
    response = client.post(url, {"date": "2026-10-26", "deployment": "4", "crew": "2"})
    assert response.status_code == 302
    created = Battle.objects.get(campaign=campaign)
    assert created.scenario == "Battle #1"
    assert created.scenario_rolls == {"deployment": 4, "crew": 2}
    detail = client.get(response["Location"])
    assert 'aria-label="Share result"' not in detail.content.decode()
    assert "View scenario" in detail.content.decode()
    assert "Generate again" in detail.content.decode()


def test_a_battle_without_components_offers_generation(client, campaign, battle):
    response = client.get(reverse("n26-battle", args=[campaign.pk, battle.pk]))
    assert "Generate scenario" in response.content.decode()
    assert "battle=" + str(battle.pk) in response.context["scenario_generate_url"]


def test_saved_battle_supplies_the_inline_editor_only_to_its_arbitrator(
    client, campaign, battle, player
):
    url = reverse("n26-battle", args=[campaign.pk, battle.pk])
    assert client.get(url).context["battle_scenario"] is None
    client.force_login(campaign.owner)
    props = client.get(url).context["battle_scenario"]
    assert props["save"]["battle"] == str(battle.pk)
    assert props["save"]["revision"] == battle.revision


def test_inline_save_returns_the_battle_url_and_refuses_stale_changes(
    client, campaign, battle
):
    response = client.post(
        save_url(), {**connection_data(campaign, battle), "format": "json"}
    )
    assert response.status_code == 200
    assert response.json()["url"] == reverse(
        "n26-battle", args=[campaign.pk, battle.pk]
    )
    assert response.json()["revision"] == 1
    response = client.post(
        save_url(), {**connection_data(campaign, battle, crew="1"), "format": "json"}
    )
    assert response.status_code == 400
    assert "This battle changed." in response.json()["errors"][0]
    battle.refresh_from_db()
    assert battle.scenario_rolls == {"deployment": 6, "crew": 2}


def test_inline_generation_attaches_chosen_components_and_clears_old_values(
    client, campaign, battle
):
    data = {
        **connection_data(campaign, battle),
        "format": "json",
        "generate": "1",
        "deployment_pick": "leave",
        "objective_pick": "leave",
        "side_job_pick": "leave",
        "crew_pick": "3",
    }
    response = client.post(save_url(), data)
    assert response.status_code == 200
    assert response.json()["rolls"] == {"crew": 3}
    battle.refresh_from_db()
    assert battle.scenario_rolls == {"crew": 3}
    stale = client.post(save_url(), {**data, "crew_pick": "4"})
    assert stale.status_code == 400
    battle.refresh_from_db()
    assert battle.scenario_rolls == {"crew": 3}


@pytest.mark.parametrize("choice", ["9", "leave"])
def test_inline_generation_rejects_invalid_or_empty_choices(
    client, campaign, battle, choice
):
    response = client.post(
        save_url(),
        {
            **connection_data(campaign, battle),
            "format": "json",
            "generate": "1",
            "deployment_pick": "leave",
            "objective_pick": "leave",
            "side_job_pick": "leave",
            "crew_pick": choice,
        },
    )
    assert response.status_code == 400
    assert response.json()["errors"]
    battle.refresh_from_db()
    assert battle.scenario_rolls == {}


def test_archived_campaign_does_not_expose_a_battle_page(client, campaign, battle):
    campaign.archived = True
    campaign.save(update_fields=["archived"])
    response = client.get(reverse("n26-battle", args=[campaign.pk, battle.pk]))
    assert response.status_code == 404
