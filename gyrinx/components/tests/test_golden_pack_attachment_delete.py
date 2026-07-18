"""Golden-equivalence test for the pack attachment delete page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackAttachment


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_attachment_delete_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="Underhive Extras", owner=user)
    attachment = CustomContentPackAttachment(
        pack=pack,
        original_filename="scenario.pdf",
        title="Scenario Rules",
    )
    request = _request(user)
    context = {"pack": pack, "attachment": attachment}
    assert_equivalent("core/pack/pack_attachment_delete.html", context, request)
