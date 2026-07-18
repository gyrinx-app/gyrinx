"""Golden-equivalence test for the pack activity page component."""

from __future__ import annotations

import pytest
from django.core.paginator import Paginator
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import _get_pack_activity


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_activity_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Content Pack", owner=user)

    all_activity = _get_pack_activity(pack)
    paginator = Paginator(all_activity, 50)
    page_obj = paginator.get_page(None)

    request = _request(user)
    context = {
        "pack": pack,
        "activities": page_obj,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "is_owner": True,
        "can_edit": pack.can_edit(user),
    }
    assert_equivalent("core/pack/pack_activity.html", context, request)
