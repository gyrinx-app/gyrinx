"""Golden-equivalence test for the content-pack detail page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import PackDetailView


def _request(user, path="/pack/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _build_context(pack, request):
    """Replicate the PackDetailView GET branch to produce the page context."""
    view = PackDetailView()
    view.kwargs = {"id": pack.id}
    view.request = request
    view.object = view.get_object()
    return view.get_context_data(object=view.object)


@pytest.mark.django_db
def test_pack_detail_matches_legacy(user):
    # An owned, listed pack with rich-text summary + description and no items:
    # exercises the header (Public badge, owner Edit/permissions nav), the
    # summary/description block, every empty content section (editors see them
    # all, with Add buttons + quick-add sidebar), the empty house-rules and
    # files sections, and the activity list (the pack-create history record).
    pack = CustomContentPack.objects.create(
        owner=user,
        name="Ash Wastes Pack",
        summary="<p>Extra <b>wasteland</b> gear.</p>",
        description="<p>Reference notes.</p>",
        listed=True,
    )
    request = _request(user, f"/pack/{pack.id}")
    context = _build_context(pack, request)
    assert_equivalent("core/pack/pack.html", context, request)
