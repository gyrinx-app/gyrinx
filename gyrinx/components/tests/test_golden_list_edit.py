"""Golden-equivalence test: the list_edit page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_edit_matches_legacy(user, make_list):
    from gyrinx.core.forms.list import EditListForm

    lst = make_list("Iron Skulls", owner=user)
    form = EditListForm(instance=lst)
    request = _request(user)
    context = {
        "form": form,
        "error_message": None,
        "return_url": "/lists/",
    }
    assert_equivalent("core/list_edit.html", context, request)
