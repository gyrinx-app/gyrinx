"""Tests for shared campaign admins ("Arbitrators", #988).

Covers the Campaign.is_admin helper, the admin-gated campaign views, the
arbitrator permission on fighter views, and the EditCampaignForm admins field.
"""

from types import SimpleNamespace

import pytest
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse

from gyrinx.core.forms.campaign import EditCampaignForm
from gyrinx.core.models.list import List
from gyrinx.core.views.fighter.permissions import Permission, get_user_permissions


@pytest.fixture
def shared_admin(make_user):
    return make_user("shared_admin", "password")


@pytest.fixture
def rando(make_user):
    return make_user("rando", "password")


@pytest.mark.django_db
def test_campaign_is_admin(user, shared_admin, rando, make_campaign):
    campaign = make_campaign("Admin Check Campaign")
    campaign.admins.add(shared_admin)

    assert campaign.is_admin(user) is True, "Owner should be an admin"
    assert campaign.is_admin(shared_admin) is True, "Shared admins should be admins"
    assert campaign.is_admin(rando) is False, "Random users should not be admins"
    assert campaign.is_admin(None) is False, "None should not be an admin"
    assert campaign.is_admin(AnonymousUser()) is False, (
        "Anonymous users should not be admins"
    )


@pytest.mark.django_db
def test_edit_campaign_view_allows_shared_admin(client, shared_admin, make_campaign):
    campaign = make_campaign("Editable Campaign")
    campaign.admins.add(shared_admin)
    client.force_login(shared_admin)

    url = reverse("core:campaign-edit", args=[campaign.id])
    response = client.get(url)
    assert response.status_code == 200

    response = client.post(
        url,
        {
            "name": "Renamed by Admin",
            "budget": campaign.budget,
            "public": "on",
            "admins": [str(shared_admin.id)],
        },
    )
    assert response.status_code == 302
    campaign.refresh_from_db()
    assert campaign.name == "Renamed by Admin"
    assert shared_admin in campaign.admins.all()


@pytest.mark.django_db
def test_edit_campaign_view_404_for_non_admin(client, rando, make_campaign):
    campaign = make_campaign("Locked Campaign")
    client.force_login(rando)

    response = client.get(reverse("core:campaign-edit", args=[campaign.id]))
    assert response.status_code == 404


@pytest.mark.django_db
def test_add_gangs_view_allows_shared_admin(client, shared_admin, rando, make_campaign):
    campaign = make_campaign("Recruiting Campaign")
    campaign.admins.add(shared_admin)

    url = reverse("core:campaign-add-lists", args=[campaign.id])

    client.force_login(shared_admin)
    assert client.get(url).status_code == 200

    client.force_login(rando)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_remove_list_allows_shared_admin(
    client, shared_admin, make_campaign, make_list
):
    campaign = make_campaign("Pruning Campaign")
    campaign.admins.add(shared_admin)
    lst = make_list("Doomed Gang")
    campaign.lists.add(lst)

    client.force_login(shared_admin)
    response = client.post(
        reverse("core:campaign-remove-list", args=[campaign.id, lst.id])
    )
    assert response.status_code == 302
    assert lst not in campaign.lists.all()


@pytest.mark.django_db
def test_shared_admin_gets_arbitrator_permission(
    shared_admin, rando, campaign, list_with_campaign
):
    campaign.admins.add(shared_admin)

    perms = get_user_permissions(SimpleNamespace(user=shared_admin), list_with_campaign)
    assert Permission.ARBITRATOR in perms
    assert Permission.OWNER not in perms

    assert get_user_permissions(SimpleNamespace(user=rando), list_with_campaign) == (
        set()
    )


@pytest.mark.django_db
def test_shared_admin_can_open_fighter_injuries_page(
    client, shared_admin, rando, campaign, list_with_campaign, make_list_fighter
):
    campaign.admins.add(shared_admin)
    fighter = make_list_fighter(list_with_campaign, "Wounded Fighter")

    url = reverse(
        "core:list-fighter-injuries-edit", args=[list_with_campaign.id, fighter.id]
    )

    client.force_login(shared_admin)
    assert client.get(url).status_code == 200

    client.force_login(rando)
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_edit_form_admins_choices_limited_to_participants(
    user, make_user, make_campaign, make_list
):
    campaign = make_campaign("Choosy Campaign")
    participant = make_user("participant", "password")
    stranger = make_user("stranger", "password")
    legacy_admin = make_user("legacy_admin", "password")

    lst = make_list("Participant Gang", owner=participant)
    campaign.lists.add(lst)
    # An admin who no longer has a gang in the campaign must stay selectable,
    # otherwise saving the form would silently drop them.
    campaign.admins.add(legacy_admin)

    form = EditCampaignForm(instance=campaign)
    choice_ids = set(form.fields["admins"].queryset.values_list("id", flat=True))

    assert choice_ids == {participant.id, legacy_admin.id}
    assert user.id not in choice_ids, "The owner is always an admin — not a choice"
    assert stranger.id not in choice_ids


@pytest.mark.django_db
def test_campaign_page_shows_admin_controls_to_shared_admin(
    client, shared_admin, rando, make_campaign, make_list
):
    campaign = make_campaign("Visible Campaign")
    campaign.admins.add(shared_admin)
    lst = make_list("Some Gang", status=List.LIST_BUILDING)
    campaign.lists.add(lst)

    url = reverse("core:campaign", args=[campaign.id])

    client.force_login(shared_admin)
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Add Gangs" in content
    assert "Arbitrators" in content
    assert "shared_admin" in content, "Shared admins are listed as arbitrators"

    client.force_login(rando)
    content = client.get(url).content.decode()
    assert "Add Gangs" not in content
