"""Golden-equivalence test: campaign_attribute_type_new matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_attribute_type_new_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignAttributeTypeForm

    campaign = make_campaign("Underhive Wars")
    form = CampaignAttributeTypeForm()
    request = _request(user)
    context = {"form": form, "campaign": campaign}
    assert_equivalent(
        "core/campaign/campaign_attribute_type_new.html", context, request
    )
