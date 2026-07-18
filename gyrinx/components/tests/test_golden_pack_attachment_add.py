"""Golden-equivalence test for the pack attachment (file) upload page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_attachment_add_matches_legacy(user):
    from gyrinx.core.forms.pack import PackAttachmentForm
    from gyrinx.core.models.pack import (
        PACK_ATTACHMENT_MAX_PER_PACK,
        CustomContentPack,
    )

    pack = CustomContentPack.objects.create(name="My Content Pack", owner=user)
    form = PackAttachmentForm()
    request = _request(user)
    context = {
        "pack": pack,
        "form": form,
        "pack_full": False,
        "attachment_count": 0,
        "max_attachments": PACK_ATTACHMENT_MAX_PER_PACK,
    }
    assert_equivalent("core/pack/pack_attachment_add.html", context, request)
