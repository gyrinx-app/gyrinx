"""Golden-equivalence test for the campaign resources page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_resources_matches_legacy(user, make_campaign, make_list):
    from gyrinx.core.models.campaign import (
        Campaign,
        CampaignListResource,
        CampaignResourceType,
    )
    from gyrinx.core.views.campaign.common import (
        get_campaign_resource_types_with_resources,
    )

    campaign = make_campaign("Underhive Wars", status=Campaign.IN_PROGRESS)
    lst = make_list("Iron Skulls", owner=user)
    campaign.lists.add(lst)

    # A resource type with a description and an allocated gang resource — exercises
    # the header admin links, per-type edit/remove links, the description, and the
    # resource table with its Modify link.
    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        description="Rations for the gang.",
        default_amount=5,
        owner=user,
    )
    CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=lst,
        amount=5,
        owner=user,
    )

    request = _request(user)
    context = {
        "campaign": campaign,
        "resource_types": get_campaign_resource_types_with_resources(campaign),
        "is_admin": campaign.is_admin(user),
        "user_lists": campaign.lists.filter(owner=user),
    }
    assert_equivalent("core/campaign/campaign_resources.html", context, request)


@pytest.mark.django_db
def test_campaign_resources_empty_matches_legacy(user, make_campaign):
    from gyrinx.core.views.campaign.common import (
        get_campaign_resource_types_with_resources,
    )

    # No resource types defined — exercises the {% empty %} branch (admin variant).
    campaign = make_campaign("Underhive Wars")

    request = _request(user)
    context = {
        "campaign": campaign,
        "resource_types": get_campaign_resource_types_with_resources(campaign),
        "is_admin": campaign.is_admin(user),
        "user_lists": campaign.lists.filter(owner=user),
    }
    assert_equivalent("core/campaign/campaign_resources.html", context, request)
