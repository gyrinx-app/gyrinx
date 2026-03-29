"""Tests for the invitation pack setup flow."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from gyrinx.core.models.invitation import CampaignInvitation
from gyrinx.core.models.pack import CustomContentPack


@pytest.fixture
def custom_content_group():
    group, _ = Group.objects.get_or_create(name="Custom Content")
    return group


@pytest.fixture
def cc_user(user, custom_content_group):
    """User in the Custom Content group."""
    user.groups.add(custom_content_group)
    return user


@pytest.mark.django_db
def test_accept_redirects_to_pack_setup_when_campaign_has_unsubscribed_packs(
    client, cc_user, make_campaign, make_list
):
    """Accepting an invitation redirects to pack setup when campaign has packs the list doesn't."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")
    pack = CustomContentPack.objects.create(
        name="Campaign Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)

    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=lst, owner=campaign.owner
    )

    client.force_login(cc_user)
    response = client.post(
        reverse("core:invitation-accept", args=[lst.id, invitation.id])
    )

    assert response.status_code == 302
    expected_url = reverse("core:invitation-pack-setup", args=[lst.id, campaign.id])
    assert response.url == expected_url


@pytest.mark.django_db
def test_accept_does_not_redirect_to_pack_setup_when_no_packs(
    client, cc_user, make_campaign, make_list
):
    """Accepting an invitation does not redirect to pack setup when campaign has no packs."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")

    invitation = CampaignInvitation.objects.create(
        campaign=campaign, list=lst, owner=campaign.owner
    )

    client.force_login(cc_user)
    response = client.post(
        reverse("core:invitation-accept", args=[lst.id, invitation.id])
    )

    assert response.status_code == 302
    assert (
        "campaign" not in response.url
    )  # Should redirect to invitations, not pack setup


@pytest.mark.django_db
def test_pack_setup_subscribes_packs(client, cc_user, make_campaign, make_list):
    """POSTing pack selections subscribes the list to those packs."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")
    pack = CustomContentPack.objects.create(
        name="Campaign Pack", owner=cc_user, listed=True
    )
    campaign.packs.add(pack)
    campaign.lists.add(lst)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:invitation-pack-setup", args=[lst.id, campaign.id]),
        {"pack_ids": [str(pack.id)]},
    )

    assert response.status_code == 302
    assert pack in lst.packs.all()


@pytest.mark.django_db
def test_pack_setup_requires_custom_content_group(
    client, user, make_campaign, make_list
):
    """Pack setup page requires Custom Content group membership."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")
    campaign.lists.add(lst)

    client.force_login(user)
    response = client.get(
        reverse("core:invitation-pack-setup", args=[lst.id, campaign.id])
    )

    assert response.status_code == 404


@pytest.mark.django_db
def test_accept_only_considers_packs_from_accepted_campaign(
    client, cc_user, make_campaign, make_list
):
    """Redirect only happens when the specific campaign has unsubscribed packs."""
    campaign_with_packs = make_campaign("Campaign With Packs")
    campaign_without_packs = make_campaign("Campaign Without Packs")
    lst = make_list("Test List")

    pack = CustomContentPack.objects.create(
        name="Some Pack", owner=cc_user, listed=True
    )
    campaign_with_packs.packs.add(pack)
    # List is already in campaign_with_packs
    campaign_with_packs.lists.add(lst)

    # Accept invitation for the campaign WITHOUT packs
    invitation = CampaignInvitation.objects.create(
        campaign=campaign_without_packs, list=lst, owner=campaign_without_packs.owner
    )

    client.force_login(cc_user)
    response = client.post(
        reverse("core:invitation-accept", args=[lst.id, invitation.id])
    )

    assert response.status_code == 302
    # Should NOT redirect to pack setup — the accepted campaign has no packs
    assert (
        "campaign" not in response.url
    )  # Should redirect to invitations, not pack setup


@pytest.mark.django_db
def test_pack_setup_allows_unlisted_campaign_packs(
    client, cc_user, make_campaign, make_list
):
    """Users can subscribe to unlisted packs when recommended by a campaign."""
    campaign = make_campaign("Test Campaign")
    lst = make_list("Test List")
    unlisted_pack = CustomContentPack.objects.create(
        name="Unlisted Pack", owner=cc_user, listed=False
    )
    campaign.packs.add(unlisted_pack)
    campaign.lists.add(lst)

    client.force_login(cc_user)
    response = client.post(
        reverse("core:invitation-pack-setup", args=[lst.id, campaign.id]),
        {"pack_ids": [str(unlisted_pack.id)]},
    )

    assert response.status_code == 302
    assert unlisted_pack in lst.packs.all()
