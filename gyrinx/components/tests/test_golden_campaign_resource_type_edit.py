"""Golden-equivalence test for the campaign resource-type edit page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_resource_type_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignResourceTypeForm
    from gyrinx.core.models.campaign import CampaignResourceType

    campaign = make_campaign("Underhive Wars")
    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Meat",
        description="Rations for the gang",
        default_amount=5,
        owner=user,
    )
    form = CampaignResourceTypeForm(instance=resource_type)
    request = _request(user)
    context = {
        "form": form,
        "campaign": campaign,
        "resource_type": resource_type,
    }
    assert_equivalent(
        "core/campaign/campaign_resource_type_edit.html", context, request
    )
