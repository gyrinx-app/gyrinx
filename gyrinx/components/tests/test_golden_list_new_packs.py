"""Golden-equivalence test for the new-list pack-selection interstitial."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/lists/new/packs"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_new_packs_matches_legacy(user):
    from gyrinx.core.models.pack import CustomContentPack

    # Mirror the view GET branch: a list of packs, each with a ``content_preview``
    # attribute attached (as the view does after evaluating the queryset).
    pack_a = CustomContentPack.objects.create(
        owner=user,
        name="Ash Wastes Pack",
        summary="<p>Extra <b>wasteland</b> gear.</p>",
        listed=True,
    )
    pack_a.content_preview = [
        {"label": "2 fighters", "names": ["Nomad", "Wastelander"], "suffix": " +3"},
        {"label": "1 item", "names": ["Cutter"], "suffix": ""},
    ]
    pack_b = CustomContentPack.objects.create(
        owner=user,
        name="Empty Pack",
        summary="",
        listed=True,
    )
    pack_b.content_preview = []

    request = _request(user)
    context = {
        "available_packs": [pack_a, pack_b],
        "search_query": "",
        "preselected_pack_ids": {str(pack_a.id)},
        "name": "Iron Gang",
    }
    assert_equivalent("core/list_new_packs.html", context, request)


@pytest.mark.django_db
def test_list_new_packs_empty_matches_legacy(user):
    # No packs, no carried name — exercises the ``{% empty %}`` branch and the
    # falsy ``{% if name %}`` paths.
    request = _request(user)
    context = {
        "available_packs": [],
        "search_query": "",
        "preselected_pack_ids": set(),
        "name": "",
    }
    assert_equivalent("core/list_new_packs.html", context, request)
