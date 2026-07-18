"""Golden-equivalence test for the campaign resource-modify page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_resource_modify_matches_legacy(user, make_campaign, make_list):
    from gyrinx.core.forms.campaign import ResourceModifyForm
    from gyrinx.core.models.campaign import (
        CampaignListResource,
        CampaignResourceType,
    )

    campaign = make_campaign("Underhive Wars")
    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        description="Rations for the gang",
        default_amount=5,
        owner=user,
    )
    lst = make_list("Goliath Gang")
    resource = CampaignListResource.objects.create(
        campaign=campaign,
        resource_type=resource_type,
        list=lst,
        amount=7,
        owner=user,
    )
    form = ResourceModifyForm(resource=resource)
    request = _request(user)
    return_url = reverse("core:campaign-resources", args=[campaign.id])
    context = {
        "form": form,
        "campaign": campaign,
        "resource": resource,
        "new_amount_preview": resource.amount,
        "return_url": return_url,
    }
    assert_equivalent("core/campaign/campaign_resource_modify.html", context, request)
