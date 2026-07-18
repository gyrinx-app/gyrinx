"""Golden-equivalence test: pack edit page matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_edit_matches_legacy(user):
    from gyrinx.core.forms.pack import PackForm
    from gyrinx.core.models.pack import CustomContentPack

    pack = CustomContentPack.objects.create(name="Kustom Pack", owner=user)
    form = PackForm(instance=pack)
    request = _request(user)
    context = {"form": form, "pack": pack}
    assert_equivalent("core/pack/pack_edit.html", context, request)
