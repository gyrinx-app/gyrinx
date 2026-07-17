"""Golden-equivalence test: campaign_resource_type_new page matches legacy."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_campaign_resource_type_new_matches_legacy(user, make_campaign):
    from gyrinx.core.forms.campaign import CampaignResourceTypeForm

    campaign = make_campaign("Underhive Wars")
    form = CampaignResourceTypeForm()
    request = _request(user)
    context = {"form": form, "campaign": campaign}
    assert_equivalent("core/campaign/campaign_resource_type_new.html", context, request)
