"""Golden-equivalence test for the list performance debug page
(``core/list_performance.html``)."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_performance_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.models.list import List
    from gyrinx.core.models.pack import CustomContentPack
    from gyrinx.core.views.list.common import get_clean_list_or_404

    lst = make_list("Iron Skulls", owner=user)
    make_list_fighter(lst, "Boss", owner=user)

    # Replicate ListPerformanceView.get_object(): resolve the clean list with
    # fighters + pack-aware prefetches, exactly as the view's GET branch does.
    packs = CustomContentPack.objects.filter(subscribed_lists__id=lst.id)
    list_obj = get_clean_list_or_404(
        List.objects.with_related_data(with_fighters=True, packs=packs),
        id=lst.id,
    )

    request = _request(user, path=f"/list/{lst.id}/performance")
    context = {"list": list_obj}
    # The template extends foundation.html directly and owns the whole <body>
    # via {% block base %} (nav/footer-free, no #content wrapper), so the golden
    # comparison is at page scope rather than the #content subtree.
    assert_equivalent("core/list_performance.html", context, request, scope="page")
