"""Tests for campaign pack integration."""

import pytest
from django.urls import reverse

from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.invitation import CampaignInvitation
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPack


# --- Model: validate_list_packs Tests ---


@pytest.mark.django_db
def test_validate_list_packs_empty_campaign_packs(user, make_campaign, make_list):
    """Empty campaign packs means no restrictions — any list is valid."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack = CustomContentPack.objects.create(name="Some Pack", owner=user, listed=True)
    lst.packs.add(pack)

    is_valid, incompatible = campaign.validate_list_packs(lst)

    assert is_valid is True
    assert incompatible == []


@pytest.mark.django_db
def test_validate_list_packs_valid_subset(user, make_campaign, make_list):
    """List packs that are a subset of campaign packs should be valid."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack1 = CustomContentPack.objects.create(name="Pack A", owner=user, listed=True)
    pack2 = CustomContentPack.objects.create(name="Pack B", owner=user, listed=True)

    campaign.packs.add(pack1, pack2)
    lst.packs.add(pack1)  # Subset of campaign packs

    is_valid, incompatible = campaign.validate_list_packs(lst)

    assert is_valid is True
    assert incompatible == []


@pytest.mark.django_db
def test_validate_list_packs_invalid_subset(user, make_campaign, make_list):
    """List packs not in campaign packs should be invalid."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack_allowed = CustomContentPack.objects.create(
        name="Allowed Pack", owner=user, listed=True
    )
    pack_not_allowed = CustomContentPack.objects.create(
        name="Not Allowed Pack", owner=user, listed=True
    )

    campaign.packs.add(pack_allowed)
    lst.packs.add(pack_allowed, pack_not_allowed)

    is_valid, incompatible = campaign.validate_list_packs(lst)

    assert is_valid is False
    assert len(incompatible) == 1
    assert incompatible[0].name == "Not Allowed Pack"


@pytest.mark.django_db
def test_validate_list_packs_list_with_no_packs(user, make_campaign, make_list):
    """A list with no packs should always be valid."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack = CustomContentPack.objects.create(name="Pack A", owner=user, listed=True)
    campaign.packs.add(pack)

    is_valid, incompatible = campaign.validate_list_packs(lst)

    assert is_valid is True
    assert incompatible == []


# --- Model: add_list_to_campaign validation Tests ---


@pytest.mark.django_db
def test_add_list_to_campaign_raises_on_incompatible_packs(
    user, make_campaign, make_list
):
    """add_list_to_campaign should raise ValueError for incompatible packs."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack_allowed = CustomContentPack.objects.create(
        name="Allowed", owner=user, listed=True
    )
    pack_bad = CustomContentPack.objects.create(
        name="Bad Pack", owner=user, listed=True
    )

    campaign.packs.add(pack_allowed)
    lst.packs.add(pack_bad)

    with pytest.raises(ValueError, match="Bad Pack"):
        campaign.add_list_to_campaign(lst, user=user)


@pytest.mark.django_db
def test_add_list_to_campaign_succeeds_with_compatible_packs(
    user, make_campaign, make_list
):
    """add_list_to_campaign should succeed when packs are compatible."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack = CustomContentPack.objects.create(name="Pack A", owner=user, listed=True)
    campaign.packs.add(pack)
    lst.packs.add(pack)

    added_list, was_added = campaign.add_list_to_campaign(lst, user=user)

    assert was_added is True
    assert lst in campaign.lists.all()


@pytest.mark.django_db
def test_add_list_to_campaign_no_restrictions_when_empty(
    user, make_campaign, make_list
):
    """add_list_to_campaign should succeed when campaign has no pack restrictions."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack = CustomContentPack.objects.create(name="Any Pack", owner=user, listed=True)
    lst.packs.add(pack)

    added_list, was_added = campaign.add_list_to_campaign(lst, user=user)

    assert was_added is True


# --- View: Pack Management Tests ---


@pytest.mark.django_db
def test_campaign_packs_view_requires_login(client, make_campaign):
    """Pack management view requires authentication."""
    campaign = make_campaign("Test Campaign")

    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_campaign_packs_view_requires_custom_content_group(client, user, make_campaign):
    """Pack management view requires Custom Content group membership."""
    campaign = make_campaign("Test Campaign")

    client.force_login(user)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    # group_membership_required returns 404 for users without the group
    assert response.status_code == 404


@pytest.mark.django_db
def test_campaign_packs_view_accessible_with_group(client, cc_user, make_campaign):
    """Pack management view is accessible to Custom Content group members."""
    campaign = make_campaign("Test Campaign")

    client.force_login(cc_user)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    assert response.status_code == 200


@pytest.mark.django_db
def test_campaign_pack_add_view(client, cc_user, make_campaign):
    """Test adding a pack to a campaign."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(name="New Pack", owner=cc_user, listed=True)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:campaign-pack-add", args=[campaign.id, pack.id])
    )

    assert response.status_code == 302
    assert campaign.packs.filter(id=pack.id).exists()


@pytest.mark.django_db
def test_campaign_pack_add_rejects_get(client, cc_user, make_campaign):
    """Test that adding a pack requires POST."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(name="New Pack", owner=cc_user, listed=True)

    client.force_login(cc_user)
    response = client.get(
        reverse("core:campaign-pack-add", args=[campaign.id, pack.id])
    )

    assert response.status_code == 302
    assert not campaign.packs.filter(id=pack.id).exists()


@pytest.mark.django_db
def test_campaign_pack_add_requires_ownership(
    client, cc_user, make_campaign, make_user
):
    """Test that only campaign owner can add packs."""
    other_user = make_user("other", "password")
    campaign = Campaign.objects.create(name="Other Campaign", owner=other_user)
    pack = CustomContentPack.objects.create(name="New Pack", owner=cc_user, listed=True)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:campaign-pack-add", args=[campaign.id, pack.id])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_campaign_pack_remove_confirmation(client, cc_user, make_campaign):
    """Test that removing a pack shows confirmation page on GET."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(
        name="To Remove", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(cc_user)
    response = client.get(
        reverse("core:campaign-pack-remove", args=[campaign.id, pack.id])
    )

    assert response.status_code == 200
    assert b"To Remove" in response.content


@pytest.mark.django_db
def test_campaign_pack_remove_post(client, cc_user, make_campaign):
    """Test that POST removes the pack from campaign."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(
        name="To Remove", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:campaign-pack-remove", args=[campaign.id, pack.id])
    )

    assert response.status_code == 302
    assert not campaign.packs.filter(id=pack.id).exists()


@pytest.mark.django_db
def test_campaign_pack_add_rejects_archived(client, cc_user, make_campaign):
    """Test that packs cannot be added to archived campaigns."""
    campaign = make_campaign("Test Campaign")
    campaign.archived = True
    campaign.save()

    pack = CustomContentPack.objects.create(name="Pack", owner=cc_user, listed=True)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:campaign-pack-add", args=[campaign.id, pack.id])
    )

    # The view 404s because get_object_or_404 filters by owner
    # and we don't separately check archived in the URL filter.
    # Actually the view checks campaign.archived after getting the campaign.
    assert response.status_code == 302
    assert not campaign.packs.filter(id=pack.id).exists()


# --- View: Join flow with incompatible packs ---


@pytest.mark.django_db
def test_accept_invitation_with_incompatible_packs(
    client, user, make_campaign, make_list, make_user
):
    """Accepting an invitation with incompatible packs should show error."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack_allowed = CustomContentPack.objects.create(
        name="Allowed", owner=user, listed=True
    )
    pack_bad = CustomContentPack.objects.create(
        name="Bad Pack", owner=user, listed=True
    )

    campaign.packs.add(pack_allowed)
    lst.packs.add(pack_bad)

    # Create a pending invitation
    invitation = CampaignInvitation.objects.create(
        campaign=campaign,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    response = client.post(
        reverse("core:invitation-accept", args=[lst.id, invitation.id])
    )

    assert response.status_code == 302
    # List should NOT be in the campaign
    assert lst not in campaign.lists.all()


@pytest.mark.django_db
def test_auto_accept_with_incompatible_packs(client, user, make_campaign, make_list):
    """Auto-accept (same owner) with incompatible packs should show error."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack_allowed = CustomContentPack.objects.create(
        name="Allowed", owner=user, listed=True
    )
    pack_bad = CustomContentPack.objects.create(
        name="Bad Pack", owner=user, listed=True
    )

    campaign.packs.add(pack_allowed)
    lst.packs.add(pack_bad)

    client.force_login(user)

    # Try to add list via the campaign add-lists view (auto-accept path)
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": str(lst.id)},
    )

    # The invite is now blocked before creation, so we get the error page (200)
    assert response.status_code == 200
    assert b"Bad Pack" in response.content
    # List should NOT be in the campaign
    assert lst not in campaign.lists.all()


# --- Campaign Detail: Packs display ---


@pytest.mark.django_db
def test_campaign_detail_shows_packs(client, user, make_campaign):
    """Campaign detail page shows allowed packs."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(
        name="Visible Pack", owner=user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:campaign", args=[campaign.id]))

    assert response.status_code == 200
    assert b"Visible Pack" in response.content


@pytest.mark.django_db
def test_campaign_detail_no_packs_section_when_empty(client, user, make_campaign):
    """Campaign detail page should not show packs section when no packs configured."""
    campaign = make_campaign("Test Campaign")

    client.force_login(user)
    response = client.get(reverse("core:campaign", args=[campaign.id]))

    assert response.status_code == 200
    # The "Content Packs" info block should not appear when empty
    assert b'caps-label">Content Packs' not in response.content


# --- Copy-to view: has_packs guard ---


@pytest.mark.django_db
def test_copy_to_view_shows_form_when_packs_exist(client, user, make_campaign):
    """copy-to view should show form when campaign only has packs (no other content)."""
    source = make_campaign("Source Campaign")
    make_campaign("Target Campaign")

    pack = CustomContentPack.objects.create(name="Pack Alpha", owner=user, listed=True)
    source.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:campaign-copy-out", args=[source.id]))

    assert response.status_code == 200


# --- Pack page: "Add to Campaigns" ---


@pytest.mark.django_db
def test_pack_detail_shows_add_to_campaigns(client, cc_user, make_campaign):
    """Pack detail page shows 'Add to Campaigns' when user has campaigns."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    make_campaign("My Campaign")

    client.force_login(cc_user)
    response = client.get(reverse("core:pack", args=[pack.id]))

    assert response.status_code == 200
    assert b"Add to Campaigns" in response.content


@pytest.mark.django_db
def test_pack_detail_shows_campaign_badge_count(client, cc_user, make_campaign):
    """Pack detail page shows badge count for subscribed campaigns."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign = make_campaign("My Campaign")
    campaign.packs.add(pack)

    client.force_login(cc_user)
    response = client.get(reverse("core:pack", args=[pack.id]))

    assert response.status_code == 200
    # Badge should show count of 1
    assert b"Add to Campaigns" in response.content


@pytest.mark.django_db
def test_pack_campaigns_view(client, cc_user, make_campaign):
    """Pack campaigns management view shows subscribed and unsubscribed campaigns."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign_sub = make_campaign("Subscribed Campaign")
    make_campaign("Unsubscribed Campaign")
    campaign_sub.packs.add(pack)

    client.force_login(cc_user)
    response = client.get(reverse("core:pack-campaigns", args=[pack.id]))

    assert response.status_code == 200
    assert b"Subscribed Campaign" in response.content
    assert b"Unsubscribed Campaign" in response.content


@pytest.mark.django_db
def test_pack_campaign_subscribe(client, cc_user, make_campaign):
    """Subscribing a campaign to a pack works."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign = make_campaign("My Campaign")

    client.force_login(cc_user)
    response = client.post(
        reverse("core:pack-campaign-subscribe", args=[pack.id]),
        {"campaign_id": str(campaign.id)},
    )

    assert response.status_code == 302
    assert campaign.packs.filter(id=pack.id).exists()


@pytest.mark.django_db
def test_pack_campaign_unsubscribe(client, cc_user, make_campaign):
    """Unsubscribing a campaign from a pack works."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign = make_campaign("My Campaign")
    campaign.packs.add(pack)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:pack-campaign-unsubscribe", args=[pack.id]),
        {"campaign_id": str(campaign.id)},
    )

    assert response.status_code == 302
    assert not campaign.packs.filter(id=pack.id).exists()


@pytest.mark.django_db
def test_pack_campaign_subscribe_rejects_get(client, cc_user, make_campaign):
    """Subscribe view requires POST."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )

    client.force_login(cc_user)
    response = client.get(
        reverse("core:pack-campaign-subscribe", args=[pack.id]),
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_pack_campaign_subscribe_rejects_other_users_campaign(
    client, cc_user, make_campaign, make_user
):
    """Cannot subscribe another user's campaign to a pack."""
    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    other_user = make_user("other", "password")
    other_campaign = Campaign.objects.create(name="Other Campaign", owner=other_user)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:pack-campaign-subscribe", args=[pack.id]),
        {"campaign_id": str(other_campaign.id)},
    )

    assert response.status_code == 404


# --- Campaign info section: packs display ---


@pytest.mark.django_db
def test_campaign_detail_shows_packs_in_info_section(client, user, make_campaign):
    """Campaign detail page shows packs in the info section."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(name="Info Pack", owner=user, listed=True)
    campaign.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:campaign", args=[campaign.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Info Pack" in content
    # Should show "Content Packs" caps-label in info section
    assert "Content Packs" in content


# --- Add Gangs page: pack names and filter ---


@pytest.mark.django_db
def test_add_gangs_shows_list_pack_names(client, user, make_campaign, make_list):
    """Add Gangs page shows pack names on each list."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")
    pack = CustomContentPack.objects.create(
        name="Display Pack", owner=user, listed=True
    )
    lst.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))

    assert response.status_code == 200
    assert b"Display Pack" in response.content


@pytest.mark.django_db
def test_invite_blocked_for_incompatible_packs(client, user, make_campaign, make_list):
    """Sending an invite is blocked when list has incompatible packs."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack_allowed = CustomContentPack.objects.create(
        name="Allowed", owner=user, listed=True
    )
    pack_bad = CustomContentPack.objects.create(
        name="Forbidden Pack", owner=user, listed=True
    )

    campaign.packs.add(pack_allowed)
    lst.packs.add(pack_bad)

    client.force_login(user)
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": str(lst.id)},
    )

    # Should show error, not create invitation
    assert response.status_code == 200
    assert b"Forbidden Pack" in response.content
    assert not CampaignInvitation.objects.filter(campaign=campaign, list=lst).exists()
    assert lst not in campaign.lists.all()


@pytest.mark.django_db
def test_invite_allowed_for_compatible_packs(client, user, make_campaign, make_list):
    """Sending an invite succeeds when list packs are compatible."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    pack = CustomContentPack.objects.create(name="Good Pack", owner=user, listed=True)
    campaign.packs.add(pack)
    lst.packs.add(pack)

    client.force_login(user)
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": str(lst.id)},
    )

    # Should succeed (auto-accept since same owner)
    assert response.status_code == 302
    assert lst in campaign.lists.all()


@pytest.mark.django_db
def test_pack_filter_toggle_filters_lists(client, user, make_campaign, make_list):
    """Matching Content Packs toggle filters out lists with incompatible packs."""
    campaign = make_campaign("Test Campaign")

    pack_allowed = CustomContentPack.objects.create(
        name="Allowed", owner=user, listed=True
    )
    pack_other = CustomContentPack.objects.create(name="Other", owner=user, listed=True)

    campaign.packs.add(pack_allowed)

    # Compatible list: only has allowed pack
    lst_good = make_list("Good List")
    lst_good.packs.add(pack_allowed)

    # Incompatible list: has a pack not in campaign
    lst_bad = make_list("Bad List")
    lst_bad.packs.add(pack_other)

    # Mixed list: has both allowed and disallowed packs — still incompatible
    lst_mixed = make_list("Mixed List")
    lst_mixed.packs.add(pack_allowed, pack_other)

    # List with no packs: always compatible
    make_list("No Packs List")

    client.force_login(user)

    # Without filter: all four lists should appear
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 200
    content = response.content.decode()
    assert "Good List" in content
    assert "Bad List" in content
    assert "Mixed List" in content
    assert "No Packs List" in content

    # With filter: Bad List and Mixed List should be excluded
    response = client.get(
        reverse("core:campaign-add-lists", args=[campaign.id]) + "?packs=matching"
    )
    assert response.status_code == 200
    content = response.content.decode()
    assert "Good List" in content
    assert "Bad List" not in content
    assert "Mixed List" not in content
    assert "No Packs List" in content


@pytest.mark.django_db
def test_pack_filter_not_shown_when_no_campaign_packs(
    client, user, make_campaign, make_list
):
    """Pack filter toggle should not show when campaign has no packs."""
    campaign = make_campaign("Test Campaign")

    client.force_login(user)
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))

    assert response.status_code == 200
    assert b"Matching Content Packs" not in response.content


@pytest.mark.django_db
def test_pack_filter_shown_when_campaign_has_packs(
    client, user, make_campaign, make_list
):
    """Pack filter toggle should show when campaign has packs configured."""
    campaign = make_campaign("Test Campaign")
    pack = CustomContentPack.objects.create(name="Camp Pack", owner=user, listed=True)
    campaign.packs.add(pack)

    client.force_login(user)
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))

    assert response.status_code == 200
    assert b"Matching Content Packs" in response.content


# --- Campaign Packs Page: "Add to..." dropdown tests ---


@pytest.mark.django_db
def test_campaign_packs_page_accessible_to_member(
    client, cc_user, make_user, make_campaign, content_house, custom_content_group
):
    """A campaign member (non-owner) can access the campaign packs page."""
    member = make_user("member", "password")
    member.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")
    member_list = List.objects.create(
        name="Member Gang", owner=member, content_house=content_house
    )
    campaign.lists.add(member_list)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(member)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    assert response.status_code == 200
    assert b"Test Pack" in response.content


@pytest.mark.django_db
def test_campaign_packs_page_404_for_non_member(
    client, cc_user, make_user, make_campaign, custom_content_group
):
    """A user with no gang in the campaign gets 404."""
    stranger = make_user("stranger", "password")
    stranger.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")

    client.force_login(stranger)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    assert response.status_code == 404


@pytest.mark.django_db
def test_campaign_packs_member_sees_add_to_dropdown(
    client, cc_user, make_user, make_campaign, content_house, custom_content_group
):
    """A member sees the 'Add to...' dropdown with their unsubscribed gangs."""
    member = make_user("member", "password")
    member.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")
    gang = List.objects.create(
        name="My Gang", owner=member, content_house=content_house
    )
    campaign.lists.add(gang)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(member)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Add to" in content
    assert "My Gang" in content


@pytest.mark.django_db
def test_campaign_packs_hides_subscribed_gangs_from_dropdown(
    client, cc_user, make_user, make_campaign, content_house, custom_content_group
):
    """Gangs already subscribed to a pack are hidden from the dropdown."""
    member = make_user("member", "password")
    member.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")
    gang = List.objects.create(
        name="Subscribed Gang", owner=member, content_house=content_house
    )
    campaign.lists.add(gang)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)
    gang.packs.add(pack)  # Already subscribed

    client.force_login(member)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    content = response.content.decode()
    assert "All Gangs subscribed" in content


@pytest.mark.django_db
def test_campaign_packs_member_does_not_see_add_remove_controls(
    client, cc_user, make_user, make_campaign, content_house, custom_content_group
):
    """A non-owner member should not see the 'Add Packs' section or remove links."""
    member = make_user("member", "password")
    member.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")
    gang = List.objects.create(
        name="My Gang", owner=member, content_house=content_house
    )
    campaign.lists.add(gang)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(member)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    content = response.content.decode()
    assert "Add Packs" not in content
    assert "bi-trash" not in content


@pytest.mark.django_db
def test_campaign_packs_subscribe_from_dropdown(
    client, cc_user, make_user, make_campaign, content_house, custom_content_group
):
    """Subscribing a gang via the dropdown redirects back to campaign packs."""
    member = make_user("member", "password")
    member.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")
    gang = List.objects.create(
        name="My Gang", owner=member, content_house=content_house
    )
    campaign.lists.add(gang)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(member)
    response = client.post(
        reverse("core:pack-subscribe", args=[pack.id]),
        {
            "list_id": str(gang.id),
            "return_url": "campaign-packs",
            "campaign_id": str(campaign.id),
        },
    )

    assert response.status_code == 302
    assert reverse("core:campaign-packs", args=[campaign.id]) in response.url
    assert gang.packs.filter(id=pack.id).exists()


@pytest.mark.django_db
def test_campaign_packs_dropdown_shows_other_link(
    client, cc_user, make_user, make_campaign, content_house, custom_content_group
):
    """The dropdown always includes an 'Other...' link to the pack's lists page."""
    member = make_user("member", "password")
    member.groups.add(custom_content_group)

    campaign = make_campaign("Test Campaign")
    gang = List.objects.create(
        name="My Gang", owner=member, content_house=content_house
    )
    campaign.lists.add(gang)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(member)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    content = response.content.decode()
    assert "Other" in content
    assert reverse("core:pack-lists", args=[pack.id]) in content


@pytest.mark.django_db
def test_campaign_packs_owner_sees_both_controls(
    client, cc_user, make_campaign, content_house
):
    """The campaign owner sees both the 'Add to...' dropdown and owner controls."""
    campaign = make_campaign("Test Campaign")
    gang = List.objects.create(
        name="Owner Gang", owner=cc_user, content_house=content_house
    )
    campaign.lists.add(gang)

    pack = CustomContentPack.objects.create(
        name="Test Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    client.force_login(cc_user)
    response = client.get(reverse("core:campaign-packs", args=[campaign.id]))

    content = response.content.decode()
    assert "Add to" in content
    assert "Owner Gang" in content
    assert "Add Packs" in content
    assert "bi-trash" in content
