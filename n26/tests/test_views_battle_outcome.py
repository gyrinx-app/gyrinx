"""Players who fought a battle record its outcome from the battle's page."""

from datetime import date

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import Battle, CampaignEvent
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(client, campaign_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
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
