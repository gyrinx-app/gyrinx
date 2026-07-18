"""Golden-equivalence test for the campaign list-attribute assign page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.campaign import CampaignListAttributeAssignmentForm
from gyrinx.core.models.campaign import (
    CampaignAttributeType,
    CampaignAttributeValue,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_list_attribute_assign_matches_legacy(user, make_campaign, make_list):
    campaign = make_campaign("Underhive Wars", owner=user)
    lst = make_list("Iron Skulls", owner=user)
    attribute_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        owner=user,
    )
    for value_name in ("Chaos", "Order"):
        CampaignAttributeValue.objects.create(
            attribute_type=attribute_type,
            name=value_name,
            owner=user,
        )

    form = CampaignListAttributeAssignmentForm(
        campaign=campaign,
        list_obj=lst,
        attribute_type=attribute_type,
    )

    request = _request(user)
    return_url = reverse("core:campaign-attributes", args=(campaign.id,))
    context = {
        "form": form,
        "campaign": campaign,
        "list": lst,
        "attribute_type": attribute_type,
        "return_url": return_url,
    }
    assert_equivalent(
        "core/campaign/campaign_list_attribute_assign.html", context, request
    )
