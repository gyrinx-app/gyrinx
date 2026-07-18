"""Golden-equivalence test for the print-config delete page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_print_config_delete_matches_legacy(user, make_list):
    from gyrinx.core.models import PrintConfig

    list_obj = make_list("My Gang")
    print_config = PrintConfig.objects.create(
        list=list_obj,
        name="Tournament Cards",
        owner=user,
    )
    request = _request(user)
    context = {
        "list": list_obj,
        "print_config": print_config,
    }
    assert_equivalent("core/print_config/delete.html", context, request)
