"""Golden-equivalence test for the pack item archive confirmation page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.metadata import ContentRule
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem
from gyrinx.core.views.pack import (
    _get_entry_for_pack_item,
    _pack_url,
    _singularize_label,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_item_delete_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="Iron Pack", owner=user)
    rule = ContentRule.objects.all_content().create(
        name="Test Rule", description="A test rule description"
    )
    ct = ContentType.objects.get_for_model(ContentRule)
    pack_item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=rule.pk, owner=user
    )
    pack_item.save_with_user(user=user)

    content_obj = pack_item.content_object
    entry = _get_entry_for_pack_item(pack_item)
    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_obj": content_obj,
        "label": _singularize_label(entry),
        "icon": entry.icon,
        "slug": entry.slug,
        "back_url": _pack_url(pack, f"item-{pack_item.id}"),
    }
    assert_equivalent("core/pack/pack_item_delete.html", context, request)
