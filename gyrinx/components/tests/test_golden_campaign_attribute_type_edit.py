"""Golden-equivalence test: campaign_attribute_type_edit page matches legacy."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_attribute_type_edit_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignAttributeTypeForm
    from gyrinx.core.models.campaign import CampaignAttributeType

    campaign = make_campaign("Underhive Wars")
    attribute_type = CampaignAttributeType.objects.create(
        campaign=campaign,
        name="Faction",
        description="Which faction the gang belongs to",
        owner=user,
    )
    form = CampaignAttributeTypeForm(instance=attribute_type)
    request = _request(user)
    context = {
        "form": form,
        "campaign": campaign,
        "attribute_type": attribute_type,
    }
    assert_equivalent(
        "core/campaign/campaign_attribute_type_edit.html", context, request
    )
