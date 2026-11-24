"""Players in a battle change its scenario on the battle's page until the
day of the battle, and the campaign log records each change and who made
it. The arbitrator may change it at any time."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from n26.core.campaign_permissions import may_change_battle_scenario
from n26.core.campaigns import campaign_operation
from n26.core.history import campaign_history
from n26.core.models import Battle, CampaignEvent
from n26.core.operations import Refusal
from n26.core.scenarios import read_change_note
from n26.library.scenario_tables import side_job_set, table
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("scenario_content")]


@pytest.fixture
def campaign(client, campaign_type):
    owner = User.objects.create_user("arb")
    client.force_login(owner)
    return found_campaign("Dust Falls", campaign_type, owner=owner)


def accepted(campaign, username):
    player = User.objects.create_user(username)
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.invite(player)
    with campaign_operation(campaign, actor=player) as act:
        act.answer_invitation(player, accepted=True)
    return player


@pytest.fixture
def player(campaign):
    return accepted(campaign, "player")


@pytest.fixture
def opponent(campaign):
    return accepted(campaign, "opponent")


@pytest.fixture
def onlooker(campaign):
    """An accepted player whose gang is not in the battle."""
    return accepted(campaign, "onlooker")


def battle_on(client, campaign, gang_type, day, *owners):
    gangs = []
    for number, owner in enumerate(owners):
        gang = found_gang(f"Gang {number}", gang_type, owner=owner)
        client.force_login(owner)
        client.post(
            reverse("n26-campaign-add-gang", args=[campaign.pk]), {"gang": gang.pk}
        )
        gangs.append(gang)
    with campaign_operation(campaign, actor=campaign.owner) as act:
        return act.record_battle(
            day,
            gangs,
            scenario="Stand-off",
            scenario_rolls={"deployment": 6, "crew": 2},
        )


def today():
    return timezone.localdate()


@pytest.fixture
def upcoming(client, campaign, gang_type, player, opponent):
    return battle_on(
        client, campaign, gang_type, today() + timedelta(days=3), player, opponent
    )


def battle_url(battle):
    return reverse("n26-battle", args=[battle.campaign_id, battle.pk])


def change(client, battle, **rolls):
    """Save a scenario as the battle page's editor does."""
    return client.post(
        reverse("n26-generate-scenario-save"),
        {
            "format": "json",
            "campaign": str(battle.campaign_id),
            "battle": str(battle.pk),
            "revision": battle.revision,
            **rolls,
        },
    )


def changes(battle):
    return CampaignEvent.objects.filter(
        battle=battle, kind=CampaignEvent.Kind.SCENARIO_CHANGED
    )


class TestWhoMayChangeIt:
    def test_a_player_in_the_battle_may_before_its_day(self, upcoming, player):
        assert may_change_battle_scenario(upcoming, player)

    def test_a_player_in_the_battle_may_on_its_day(self, upcoming, player):
        assert may_change_battle_scenario(upcoming, player, today=upcoming.date)

    def test_a_player_may_not_after_its_day(self, upcoming, player):
        later = upcoming.date + timedelta(days=1)
        assert not may_change_battle_scenario(upcoming, player, today=later)

    def test_the_arbitrator_may_after_its_day(self, upcoming, campaign):
        later = upcoming.date + timedelta(days=1)
        assert may_change_battle_scenario(upcoming, campaign.owner, today=later)

    def test_a_player_whose_gang_is_not_in_it_may_not(self, upcoming, onlooker):
        assert not may_change_battle_scenario(upcoming, onlooker)

    def test_nobody_may_once_it_is_archived(self, upcoming, campaign, player):
        upcoming.archived = True
        assert not may_change_battle_scenario(upcoming, player)
        assert not may_change_battle_scenario(upcoming, campaign.owner)

    def test_a_player_may_not_once_the_outcome_is_recorded(self, upcoming, player):
        upcoming.result = Battle.Result.DRAW
        assert not may_change_battle_scenario(upcoming, player)


class TestTheBattlePage:
    def test_a_player_in_an_upcoming_battle_gets_the_scenario_editor(
        self, client, upcoming, player
    ):
        client.force_login(player)
        page = client.get(battle_url(upcoming))
        editor = page.context["battle_scenario"]
        assert editor["save"]["battle"] == str(upcoming.pk)
        assert 'data-react-name="battle-scenario"' in page.content.decode()

    def test_a_player_in_a_past_battle_only_sees_the_scenario(
        self, client, campaign, gang_type, player, opponent
    ):
        past = battle_on(
            client, campaign, gang_type, today() - timedelta(days=1), player, opponent
        )
        client.force_login(player)
        page = client.get(battle_url(past))
        assert page.context["battle_scenario"] is None
        assert len(page.context["scenario_results"]) == 2

    def test_a_player_not_in_the_battle_only_sees_the_scenario(
        self, client, upcoming, onlooker
    ):
        client.force_login(onlooker)
        assert client.get(battle_url(upcoming)).context["battle_scenario"] is None


class TestChanging:
    def test_a_player_in_the_battle_changes_its_scenario(
        self, client, upcoming, player
    ):
        client.force_login(player)
        response = change(client, upcoming, deployment="3", objective="1")
        assert response.status_code == 200
        upcoming.refresh_from_db()
        assert upcoming.scenario_rolls == {"deployment": 3, "objective": 1}
        assert response.json()["revision"] == upcoming.revision
        event = changes(upcoming).get()
        assert event.actor == player
        assert read_change_note(event.note) == (
            {"deployment": "6", "crew": "2"},
            {"deployment": "3", "objective": "1"},
        )

    def test_the_other_player_changes_it_too(self, client, upcoming, opponent):
        client.force_login(opponent)
        assert change(client, upcoming, crew="5").status_code == 200
        assert changes(upcoming).get().actor == opponent

    def test_a_player_is_refused_after_the_day_of_the_battle(
        self, client, campaign, gang_type, player, opponent
    ):
        past = battle_on(
            client, campaign, gang_type, today() - timedelta(days=1), player, opponent
        )
        client.force_login(player)
        response = change(client, past, deployment="3")
        assert response.status_code == 400
        assert "Only the arbitrator can change" in response.json()["errors"][0]
        past.refresh_from_db()
        assert past.scenario_rolls == {"deployment": 6, "crew": 2}
        assert not changes(past).exists()

    def test_the_arbitrator_changes_a_past_battle(
        self, client, campaign, gang_type, player, opponent
    ):
        past = battle_on(
            client, campaign, gang_type, today() - timedelta(days=1), player, opponent
        )
        client.force_login(campaign.owner)
        assert change(client, past, deployment="3").status_code == 200
        assert changes(past).get().actor == campaign.owner

    def test_a_player_not_in_the_battle_is_refused(self, client, upcoming, onlooker):
        client.force_login(onlooker)
        assert change(client, upcoming, deployment="3").status_code == 400
        assert not changes(upcoming).exists()

    def test_a_stranger_is_refused(self, client, upcoming):
        client.force_login(User.objects.create_user("stranger"))
        assert change(client, upcoming, deployment="3").status_code == 400
        upcoming.refresh_from_db()
        assert upcoming.scenario_rolls == {"deployment": 6, "crew": 2}

    def test_the_operation_refuses_a_player_after_the_outcome(
        self, campaign, upcoming, player
    ):
        with campaign_operation(campaign, actor=player) as act:
            act.record_outcome(
                upcoming, result=Battle.Result.DRAW, winners=[], revision=0
            )
        upcoming.refresh_from_db()
        with pytest.raises(Refusal, match="Only the arbitrator"):
            with campaign_operation(campaign, actor=player) as act:
                act.connect_scenario(upcoming, {"crew": 5}, revision=upcoming.revision)

    def test_saving_the_same_scenario_adds_no_log_entry(self, client, upcoming, player):
        client.force_login(player)
        change(client, upcoming, deployment="6", crew="2")
        assert not changes(upcoming).exists()


class TestTheLog:
    def test_the_log_names_who_changed_what_from_old_to_new(
        self, client, campaign, upcoming, player
    ):
        client.force_login(player)
        change(client, upcoming, deployment="3", side_job="orlock-5")

        acts = campaign_history(campaign, viewer=player)
        line = "".join(span.text for span in acts[-1].spans)
        deployment = table("deployment")
        orlock = side_job_set("orlock")
        assert line == (
            "changed the scenario of Stand-off: "
            f"Deployment: {deployment.entry(6).label} → {deployment.entry(3).label}; "
            f"Crew: removed {table('crew').entry(2).label}; "
            f"Side job 1: added {orlock.entry(5).label} (Orlock)"
        )
        assert acts[-1].spans[0].href == battle_url(upcoming)
        assert acts[-1].actor_pk == player.pk
