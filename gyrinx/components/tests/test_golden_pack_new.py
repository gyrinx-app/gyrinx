"""Golden-equivalence test for the new-content-pack create page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_new_matches_legacy(user):
    from gyrinx.core.forms.pack import PackForm

    form = PackForm(initial={"name": ""})
    request = _request(user)
    context = {"form": form}
    assert_equivalent("core/pack/pack_new.html", context, request)
