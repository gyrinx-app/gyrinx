"""Players who fought a battle record its outcome from the battle's page."""

from datetime import date

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.models import Battle, CampaignEvent
from n26.core.operations import Refusal
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


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
def battle(client, campaign, player, gang_type):
    ours = found_gang("Ashen Choir", gang_type, owner=player)
    theirs = found_gang("Rust Saints", gang_type, owner=campaign.owner)
    for gang in (ours, theirs):
        client.post(
            reverse("n26-campaign-add-gang", args=[campaign.pk]), {"gang": gang.pk}
        )
    with campaign_operation(campaign, actor=campaign.owner) as act:
        return act.record_battle(
            date(2026, 10, 6), [ours, theirs], scenario="Stand-off"
        )


def outcome_url(battle):
    return reverse("n26-campaign-battle-outcome", args=[battle.campaign_id, battle.pk])


def battle_url(battle):
    return reverse("n26-battle", args=[battle.campaign_id, battle.pk])


def test_a_player_who_fought_records_the_outcome(client, battle, player):
    client.force_login(player)
    page = client.get(battle_url(battle)).content.decode()
    assert outcome_url(battle) in page

    ours = battle.gangs.get(name="Ashen Choir")
    response = client.post(
        outcome_url(battle),
        {"result": "winners", "winners": [ours.pk], "revision": battle.revision},
    )
    assert response.status_code == 302
    battle.refresh_from_db()
    assert battle.result == Battle.Result.WINNERS
    assert list(battle.winners.all()) == [ours]
    assert battle.scenario == "Stand-off"
    assert (
        battle.campaign.events.filter(kind=CampaignEvent.Kind.BATTLE_EDITED).get().actor
        == player
    )


def test_a_draw_needs_no_winners(client, battle, player):
    client.force_login(player)
    client.post(outcome_url(battle), {"result": "draw", "revision": battle.revision})
    battle.refresh_from_db()
    assert battle.result == Battle.Result.DRAW


def test_winners_must_be_picked_for_a_win(client, battle, player):
    client.force_login(player)
    response = client.post(
        outcome_url(battle), {"result": "winners", "revision": battle.revision}
    )
    assert response.status_code == 200
    assert "Select at least one winning gang." in response.content.decode()
    battle.refresh_from_db()
    assert battle.result == Battle.Result.NOT_RECORDED


def test_not_recorded_is_not_an_outcome_to_record(client, battle, player):
    client.force_login(player)
    response = client.post(
        outcome_url(battle), {"result": "not_recorded", "revision": battle.revision}
    )
    assert response.status_code == 200
    battle.refresh_from_db()
    assert battle.result == Battle.Result.NOT_RECORDED


def test_once_recorded_only_the_arbitrator_changes_it(client, battle, player):
    client.force_login(player)
    client.post(outcome_url(battle), {"result": "draw", "revision": battle.revision})
    assert client.get(outcome_url(battle)).status_code == 404
    assert outcome_url(battle) not in client.get(battle_url(battle)).content.decode()


def test_a_player_whose_gang_did_not_fight_cannot_record_it(client, campaign, battle):
    client.force_login(accepted(campaign, "bystander"))
    assert client.get(outcome_url(battle)).status_code == 404
    assert outcome_url(battle) not in client.get(battle_url(battle)).content.decode()


def test_a_stranger_cannot_record_it(client, battle):
    client.force_login(User.objects.create_user("stranger"))
    assert client.get(outcome_url(battle)).status_code == 404


def test_the_arbitrator_keeps_the_full_edit(client, campaign, battle):
    client.force_login(campaign.owner)
    page = client.get(battle_url(battle)).content.decode()
    assert reverse("n26-campaign-edit-battle", args=[campaign.pk, battle.pk]) in page
    assert client.get(outcome_url(battle)).status_code == 200


def test_players_still_cannot_use_the_full_edit(client, battle, player):
    client.force_login(player)
    edit = reverse("n26-campaign-edit-battle", args=[battle.campaign_id, battle.pk])
    assert client.get(edit).status_code == 404


def test_the_outcome_page_uses_the_shared_form_and_only_offers_participants(
    client, battle, player
):
    client.force_login(player)
    response = client.get(outcome_url(battle))
    assert response.status_code == 200
    soup = BeautifulSoup(
        response.content, "html.parser", on_duplicate_attribute="ignore"
    )
    form = soup.select_one(f'form[action="{outcome_url(battle)}"]')
    assert {field["name"] for field in form.select("input, select")} == {
        "csrfmiddlewaretoken",
        "revision",
        "result",
        "winners",
    }
    assert {option["value"] for option in form.select("select option")} == {
        "draw",
        "winners",
    }
    assert {field["value"] for field in form.select('[name="winners"]')} == {
        str(gang.pk) for gang in battle.gangs.all()
    }
    assert "bg-green-700" in form.select_one('[type="submit"]')["class"]
    assert form.select_one(f'a[href="{battle_url(battle)}"]')


@pytest.mark.parametrize("actor", ["player", "arbitrator"])
def test_archived_battles_offer_no_outcome_action(client, battle, player, actor):
    with campaign_operation(battle.campaign, actor=battle.campaign.owner) as act:
        act.remove_battle(battle, revision=battle.revision)
    client.force_login(player if actor == "player" else battle.campaign.owner)
    assert client.get(outcome_url(battle)).status_code == 404
    assert (
        client.post(outcome_url(battle), {"result": "draw", "revision": 0}).status_code
        == 404
    )
    assert outcome_url(battle) not in client.get(battle_url(battle)).content.decode()


def test_stale_outcome_forms_cannot_overwrite_an_arbitrator_edit(
    client, battle, player
):
    with campaign_operation(battle.campaign, actor=battle.campaign.owner) as act:
        act.edit_battle(
            battle,
            scenario="Ambush",
            date=battle.date,
            gangs=battle.gangs.all(),
            result="not_recorded",
            winners=[],
            revision=battle.revision,
        )
    client.force_login(player)
    response = client.post(outcome_url(battle), {"result": "draw", "revision": 0})
    assert response.status_code == 200
    assert "This battle changed. Reload it" in response.content.decode()
    battle.refresh_from_db()
    assert battle.scenario == "Ambush"
    assert battle.result == Battle.Result.NOT_RECORDED


def test_posted_metadata_is_ignored_when_recording_an_outcome(client, battle, player):
    before_date = battle.date
    before_gangs = set(battle.gangs.all())
    client.force_login(player)
    response = client.post(
        outcome_url(battle),
        {
            "result": "draw",
            "revision": battle.revision,
            "scenario": "Changed",
            "date": "2020-01-01",
            "gangs": [],
            "stake": "",
            "stake_awarded_to": "",
        },
    )
    assert response.status_code == 302
    battle.refresh_from_db()
    assert battle.scenario == "Stand-off"
    assert battle.date == before_date
    assert set(battle.gangs.all()) == before_gangs


def test_the_operation_rechecks_membership_after_the_form_was_opened(battle, player):
    with campaign_operation(battle.campaign, actor=battle.campaign.owner) as act:
        act.remove_player(battle.campaign.participants.get(user=player))
    with pytest.raises(Refusal, match="not yours"):
        with campaign_operation(battle.campaign, actor=player) as act:
            act.record_outcome(battle, result="draw", winners=[], revision=0)
    battle.refresh_from_db()
    assert battle.result == Battle.Result.NOT_RECORDED


def test_a_second_recording_is_refused_under_the_operation_lock(battle, player):
    with campaign_operation(battle.campaign, actor=player) as act:
        act.record_outcome(battle, result="draw", winners=[], revision=0)
    with pytest.raises(Refusal, match="already recorded"):
        with campaign_operation(battle.campaign, actor=player) as act:
            act.record_outcome(
                battle, result="winners", winners=battle.gangs.all(), revision=0
            )
    battle.refresh_from_db()
    assert battle.result == Battle.Result.DRAW
    assert (
        battle.campaign.events.filter(kind=CampaignEvent.Kind.BATTLE_EDITED).count()
        == 1
    )


def test_the_operation_requires_a_recorded_outcome(battle, player):
    with pytest.raises(Refusal, match="Select an outcome"):
        with campaign_operation(battle.campaign, actor=player) as act:
            act.record_outcome(battle, result="not_recorded", winners=[], revision=0)


def test_more_winning_gang_choices_add_no_queries(client, battle, player, gang_type):
    client.force_login(player)

    def query_count():
        with CaptureQueriesContext(connection) as queries:
            response = client.get(outcome_url(battle))
        assert response.status_code == 200
        return len(queries)

    query_count()
    before = query_count()
    for index in range(5):
        gang = found_gang(f"Participant {index}", gang_type, owner=player)
        battle.gangs.add(gang)
    query_count()
    assert query_count() == before


def test_a_legacy_battle_can_record_its_outcome_without_a_scenario(
    client, battle, player
):
    Battle.objects.filter(pk=battle.pk).update(scenario="")
    client.force_login(player)
    response = client.post(outcome_url(battle), {"result": "draw", "revision": 0})
    assert response.status_code == 302
    battle.refresh_from_db()
    assert battle.scenario == ""
    assert battle.result == Battle.Result.DRAW
    assert battle.revision == 1
    assert (
        battle.campaign.events.filter(kind=CampaignEvent.Kind.BATTLE_EDITED).count()
        == 1
    )


def test_the_operation_validates_winners_from_the_battle_participants(
    battle, player, gang_type
):
    outsider = found_gang("Bystanders", gang_type, owner=player)
    with pytest.raises(Refusal, match="Every winner must be a participant"):
        with campaign_operation(battle.campaign, actor=player) as act:
            act.record_outcome(battle, result="winners", winners=[outsider], revision=0)
    battle.refresh_from_db()
    assert battle.result == Battle.Result.NOT_RECORDED


def test_new_battles_still_require_a_scenario(campaign, player):
    with pytest.raises(Refusal, match="Enter a scenario name"):
        with campaign_operation(campaign, actor=player) as act:
            act.record_battle(date(2026, 10, 25), [], scenario="")
