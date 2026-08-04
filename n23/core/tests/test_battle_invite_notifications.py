"""Tests for battle-invite notifications.

When a gang is added to a battle, its owner should hear about it in their inbox.
These cover the two entry points (creating and editing a battle) and the rules
in :func:`n23.core.handlers.battle.notify_battle_participants`: never notify
the acting user, one notification per owner, and only newly added gangs on edit.
"""

import pytest
from django.urls import reverse

from n23.core.models import Battle, Campaign
from n23.core.models.notification import Notification, NotificationType


def _campaign(make_campaign, owner):
    return make_campaign("Battle Camp", owner=owner, status=Campaign.IN_PROGRESS)


@pytest.mark.django_db
def test_new_battle_notifies_each_other_owner(
    client, make_user, make_campaign, make_list
):
    """An arbitrator (owning no gang) creates a battle between two players'
    gangs. Each player is notified exactly once; the arbitrator is not."""
    arbitrator = make_user("arbitrator", "password")
    owner_a = make_user("player_a", "password")
    owner_b = make_user("player_b", "password")

    campaign = _campaign(make_campaign, arbitrator)
    gang_a = make_list("Ratspike", owner=owner_a)
    gang_b = make_list("Cold Blooded", owner=owner_b)
    campaign.lists.add(gang_a, gang_b)

    client.force_login(arbitrator)
    response = client.post(
        reverse("core:battle-new", args=[campaign.id]),
        {
            "date": "2025-02-01",
            "mission": "Ambush",
            "participants": [str(gang_a.id), str(gang_b.id)],
        },
    )
    assert response.status_code == 302

    battle = Battle.objects.get()

    # The arbitrator acted, so gets nothing.
    assert Notification.objects.filter(owner=arbitrator).count() == 0

    for gang, owner in [(gang_a, owner_a), (gang_b, owner_b)]:
        notes = Notification.objects.filter(owner=owner)
        assert notes.count() == 1
        n = notes.get()
        assert n.notification_type == NotificationType.LIST
        assert n.sender == arbitrator
        assert n.related_list == gang
        assert n.related_campaign == campaign
        assert n.subject == "Your gang has been added to a battle"
        # Content names the gang, the battle mission and the campaign.
        assert gang.name in n.content
        assert battle.mission in n.content
        assert campaign.name in n.content


@pytest.mark.django_db
def test_new_battle_does_not_self_notify_actor(
    client, make_user, make_campaign, make_list
):
    """A player who owns a participating gang creates the battle: they are not
    notified about their own gang, but the other player still is."""
    owner_a = make_user("player_a", "password")
    owner_b = make_user("player_b", "password")

    # Campaign owned by someone else; owner_a has create permission via their gang.
    arbitrator = make_user("arbitrator", "password")
    campaign = _campaign(make_campaign, arbitrator)
    gang_a = make_list("Ratspike", owner=owner_a)
    gang_b = make_list("Cold Blooded", owner=owner_b)
    campaign.lists.add(gang_a, gang_b)

    client.force_login(owner_a)
    response = client.post(
        reverse("core:battle-new", args=[campaign.id]),
        {
            "mission": "Ambush",
            "participants": [str(gang_a.id), str(gang_b.id)],
        },
    )
    assert response.status_code == 302

    # The actor (owner_a) is never notified about their own action.
    assert Notification.objects.filter(owner=owner_a).count() == 0
    # The other player is notified once.
    assert Notification.objects.filter(owner=owner_b).count() == 1


@pytest.mark.django_db
def test_new_battle_one_owner_two_gangs_gets_single_notification(
    client, make_user, make_campaign, make_list
):
    """A player fielding two gangs in one battle gets a single notification that
    names both — one per owner, not one per gang."""
    arbitrator = make_user("arbitrator", "password")
    owner = make_user("player", "password")

    campaign = _campaign(make_campaign, arbitrator)
    gang_1 = make_list("Alpha Crew", owner=owner)
    gang_2 = make_list("Bravo Crew", owner=owner)
    campaign.lists.add(gang_1, gang_2)

    client.force_login(arbitrator)
    response = client.post(
        reverse("core:battle-new", args=[campaign.id]),
        {
            "mission": "Ambush",
            "participants": [str(gang_1.id), str(gang_2.id)],
        },
    )
    assert response.status_code == 302

    notes = Notification.objects.filter(owner=owner)
    assert notes.count() == 1
    n = notes.get()
    assert n.subject == "Your gangs have been added to a battle"
    assert gang_1.name in n.content
    assert gang_2.name in n.content
    # A multi-gang notification has no single gang to link to, so it falls back
    # to the campaign for its inbox link.
    assert n.related_list is None
    assert n.related_campaign == campaign


@pytest.mark.django_db
def test_edit_battle_notifies_only_newly_added(
    client, make_user, make_campaign, make_list
):
    """Editing a battle to add a third gang notifies only that gang's owner —
    existing participants are not re-notified."""
    arbitrator = make_user("arbitrator", "password")
    owner_a = make_user("player_a", "password")
    owner_b = make_user("player_b", "password")
    owner_c = make_user("player_c", "password")

    campaign = _campaign(make_campaign, arbitrator)
    gang_a = make_list("Ratspike", owner=owner_a)
    gang_b = make_list("Cold Blooded", owner=owner_b)
    gang_c = make_list("Iron Fangs", owner=owner_c)
    campaign.lists.add(gang_a, gang_b, gang_c)

    # Battle already has A and B; no notifications from this direct setup.
    battle = Battle.objects.create(campaign=campaign, mission="Raid", owner=arbitrator)
    battle.set_participants([gang_a, gang_b])
    assert Notification.objects.count() == 0

    client.force_login(arbitrator)
    response = client.post(
        reverse("core:battle-edit", args=[battle.id]),
        {
            "mission": "Raid",
            "participants": [str(gang_a.id), str(gang_b.id), str(gang_c.id)],
        },
    )
    assert response.status_code == 302

    # Only the newly added gang's owner is notified.
    assert Notification.objects.filter(owner=owner_c).count() == 1
    assert Notification.objects.filter(owner=owner_a).count() == 0
    assert Notification.objects.filter(owner=owner_b).count() == 0
    assert Notification.objects.filter(owner=arbitrator).count() == 0

    n = Notification.objects.get(owner=owner_c)
    assert n.related_list == gang_c
    assert n.notification_type == NotificationType.LIST


@pytest.mark.django_db
def test_edit_battle_no_new_participants_notifies_nobody(
    client, make_user, make_campaign, make_list
):
    """Editing a battle without adding anyone (e.g. changing the mission)
    produces no notifications."""
    arbitrator = make_user("arbitrator", "password")
    owner_a = make_user("player_a", "password")
    owner_b = make_user("player_b", "password")

    campaign = _campaign(make_campaign, arbitrator)
    gang_a = make_list("Ratspike", owner=owner_a)
    gang_b = make_list("Cold Blooded", owner=owner_b)
    campaign.lists.add(gang_a, gang_b)

    battle = Battle.objects.create(campaign=campaign, mission="Raid", owner=arbitrator)
    battle.set_participants([gang_a, gang_b])

    client.force_login(arbitrator)
    response = client.post(
        reverse("core:battle-edit", args=[battle.id]),
        {
            "mission": "Raid renamed",
            "participants": [str(gang_a.id), str(gang_b.id)],
        },
    )
    assert response.status_code == 302

    assert Notification.objects.count() == 0
