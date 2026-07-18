"""Golden-equivalence test for the list credits-edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_credits_edit_matches_legacy(user, make_list):
    from gyrinx.core.forms.list import EditListCreditsForm

    lst = make_list("Iron Skulls", owner=user)
    form = EditListCreditsForm(lst=lst)
    request = _request(user)
    context = {
        "form": form,
        "list": lst,
    }
    assert_equivalent("core/list_credits_edit.html", context, request)
