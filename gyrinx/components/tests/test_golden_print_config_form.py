"""Golden-equivalence test for the print-config create/edit form page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_print_config_form_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.core.forms.print_config import PrintConfigForm
    from gyrinx.core.models import List

    lst = make_list("Iron Skulls", owner=user)
    make_list_fighter(lst, "Boss", owner=user)
    # The view fetches the list via ``with_related_data`` (used by the header).
    list_obj = List.objects.with_related_data().get(id=lst.id)

    # Replicate the create view's GET branch exactly.
    initial = {
        "name": "Custom Configuration",
        "include_assets": True,
        "include_attributes": True,
        "include_stash": True,
        "include_actions": False,
        "include_dead_fighters": False,
    }
    form = PrintConfigForm(initial=initial, list_obj=list_obj)
    request = _request(user)
    context = {
        "form": form,
        "list": list_obj,
        "title": "Create Print Configuration",
    }
    assert_equivalent("core/print_config/form.html", context, request)
