"""Golden-equivalence test for the printable list sheet page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_print_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.models import ListFighter

    lst = make_list("Iron Skulls", owner=user)
    make_list_fighter(lst, "Boss", owner=user)

    # Rebuild the fighters queryset the way the view's GET branch does for the
    # default (no print_config) case: annotate group keys, prefetch related data,
    # then filter to this list's live, non-dead fighters.
    fighters_qs = (
        ListFighter.objects.with_group_keys()
        .with_related_data(packs=[])
        .filter(list=lst, archived=False)
        .exclude(injury_state=ListFighter.DEAD)
    )

    request = _request(user, path=f"/list/{lst.id}/print")
    context = {
        "list": lst,
        "print_config": None,
        "fighters_with_groups": fighters_qs,
    }
    assert_equivalent("core/list_print.html", context, request)
