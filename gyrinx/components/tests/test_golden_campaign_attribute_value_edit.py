"""Golden-equivalence test for the campaign attribute-value edit page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_attribute_value_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignAttributeValueForm
    from gyrinx.core.models.campaign import (
        CampaignAttributeType,
        CampaignAttributeValue,
    )

    campaign = make_campaign("Underhive Wars")
    attribute_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        description="Which side of the war",
        owner=user,
    )
    attribute_value = CampaignAttributeValue.objects.create(
        attribute_type=attribute_type,
        name="Order",
        description="The lawful faction",
        colour="#FF5733",
        owner=user,
    )
    form = CampaignAttributeValueForm(instance=attribute_value)
    request = _request(user)
    context = {
        "form": form,
        "campaign": campaign,
        "attribute_value": attribute_value,
    }
    assert_equivalent(
        "core/campaign/campaign_attribute_value_edit.html", context, request
    )
