"""Golden-equivalence test for the pack fighter default-assignment remove page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.default_assignment import ContentFighterDefaultAssignment
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_fighter_default_assignment_remove_matches_legacy(
    user, content_fighter, make_equipment
):
    pack = CustomContentPack.objects.create(name="Test Pack", owner=user)
    fighter_ct = ContentType.objects.get_for_model(ContentFighter)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=fighter_ct,
        object_id=content_fighter.id,
        owner=user,
    )
    equipment = make_equipment("Lasgun", category="Basic Weapons")
    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=content_fighter,
        equipment=equipment,
    )
    request = _request(user)
    context = {
        "pack": pack,
        "pack_item": pack_item,
        "content_fighter": content_fighter,
        "assignment": assignment,
    }
    assert_equivalent(
        "core/pack/pack_fighter_default_assignment_remove.html", context, request
    )
