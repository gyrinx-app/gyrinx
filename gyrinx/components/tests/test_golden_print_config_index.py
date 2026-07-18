"""Golden-equivalence test: print-config index matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models import PrintConfig


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_print_config_index_matches_legacy(user, make_list):
    lst = make_list("Iron Skulls", owner=user)

    PrintConfig.objects.create(list=lst, owner=user, name="Battle Sheet")
    PrintConfig.objects.create(
        list=lst,
        owner=user,
        name="Classic Cards",
        card_style=PrintConfig.CLASSIC,
        include_actions=True,
        blank_fighter_cards=2,
    )

    # Reproduce the view's GET-branch context exactly.
    print_configs = PrintConfig.objects.filter(list=lst, archived=False).order_by(
        "name"
    )
    request = _request(user, path=f"/list/{lst.id}/print-configs")
    context = {
        "list": lst,
        "print_configs": print_configs,
        "is_owner": user == lst.owner,
    }
    assert_equivalent("core/print_config/index.html", context, request)
