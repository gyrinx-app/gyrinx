"""Golden-equivalence test for the new-list create form page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_new_matches_legacy(user):
    from gyrinx.content.models import ContentHouse
    from gyrinx.core.forms.list import NewListForm

    # Mirror the new-list view GET branch with no packs selected.
    form = NewListForm(initial={"name": ""}, pack_ids=[])
    request = _request(user)
    context = {
        "form": form,
        "houses": ContentHouse.objects.all(),
        "selected_packs": [],
        "pack_ids": [],
        "change_packs_url": reverse("core:lists-new-packs"),
    }
    assert_equivalent("core/list_new.html", context, request)
