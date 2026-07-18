"""Golden-equivalence test for the pack permissions page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import (
    CustomContentPack,
    CustomContentPackPermission,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_permissions_matches_legacy(user, make_user):
    editor = make_user("editor", "password")
    pack = CustomContentPack.objects.create(name="Underhive Extras", owner=user)
    CustomContentPackPermission.objects.create(
        pack=pack, user=editor, role="editor", owner=user
    )

    editors = pack.permissions.select_related("user").all()
    request = _request(user)
    context = {"pack": pack, "editors": editors, "error": None}
    assert_equivalent("core/pack/pack_permissions.html", context, request)
