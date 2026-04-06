"""Tests for private campaign visibility to invited/participating players."""

import pytest
from django.test import Client

from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_private_campaign_visible_to_participant(
    user, make_user, make_campaign, content_house
):
    """A participant in a private campaign can see it in the 'all campaigns' view."""
    other_user = make_user("other", "password")

    # Create a private campaign owned by other_user
    private_campaign = make_campaign(
        "Private Campaign",
        owner=other_user,
        public=False,
        status=Campaign.IN_PROGRESS,
    )

    # Create a list owned by 'user' and add it to the private campaign
    lst = List.objects.create(
        name="My List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
        campaign=private_campaign,
    )
    private_campaign.lists.add(lst)

    client = Client()
    client.force_login(user)

    # Browse "all campaigns" (my=0)
    response = client.get("/campaigns/?my=0")
    assert response.status_code == 200
    assert private_campaign in response.context["campaigns"]


@pytest.mark.django_db
def test_private_campaign_not_visible_to_non_participant(
    user, make_user, make_campaign
):
    """A non-participant cannot see a private campaign in the 'all campaigns' view."""
    other_user = make_user("other", "password")

    private_campaign = make_campaign(
        "Private Campaign",
        owner=other_user,
        public=False,
        status=Campaign.IN_PROGRESS,
    )

    client = Client()
    client.force_login(user)

    response = client.get("/campaigns/?my=0")
    assert response.status_code == 200
    assert private_campaign not in response.context["campaigns"]


@pytest.mark.django_db
def test_private_campaign_visible_with_participating_filter(
    user, make_user, make_campaign, content_house
):
    """The participating filter works for private campaigns the user is in."""
    other_user = make_user("other", "password")

    private_campaign = make_campaign(
        "Private Campaign",
        owner=other_user,
        public=False,
        status=Campaign.IN_PROGRESS,
    )

    # Also create a public campaign user is NOT in
    public_campaign = make_campaign(
        "Public Campaign",
        owner=other_user,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="My List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
        campaign=private_campaign,
    )
    private_campaign.lists.add(lst)

    client = Client()
    client.force_login(user)

    # Browse all + participating
    response = client.get("/campaigns/?my=0&participating=1")
    assert response.status_code == 200
    campaigns = list(response.context["campaigns"])
    assert private_campaign in campaigns
    assert public_campaign not in campaigns


@pytest.mark.django_db
def test_public_campaigns_still_visible_when_browsing_all(
    user, make_user, make_campaign
):
    """Public campaigns remain visible in the 'all campaigns' view."""
    other_user = make_user("other", "password")

    public_campaign = make_campaign(
        "Public Campaign",
        owner=other_user,
        public=True,
        status=Campaign.IN_PROGRESS,
    )

    client = Client()
    client.force_login(user)

    response = client.get("/campaigns/?my=0")
    assert response.status_code == 200
    assert public_campaign in response.context["campaigns"]
