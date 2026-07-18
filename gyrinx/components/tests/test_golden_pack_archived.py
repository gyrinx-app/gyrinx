"""Golden-equivalence test for the pack archived-items listing page."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.metadata import ContentRule
from gyrinx.content.models.skill import ContentSkill, ContentSkillCategory
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _pack_item(pack, content_object, user):
    ct = ContentType.objects.get_for_model(type(content_object))
    item = CustomContentPackItem(
        pack=pack, content_type=ct, object_id=content_object.pk, owner=user
    )
    item.save_with_user(user=user)
    return item


@pytest.mark.django_db
def test_pack_archived_table_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="Iron Pack", owner=user)
    rule = ContentRule.objects.all_content().create(
        name="Test Rule", description="A test rule description"
    )
    item = _pack_item(pack, rule, user)

    request = _request(user)
    context = {
        "pack": pack,
        "archived_items": [{"pack_item": item, "content_object": rule}],
        "section_label": "Special Rules",
        "slug": "rule",
    }
    assert_equivalent("core/pack/pack_archived.html", context, request)


@pytest.mark.django_db
def test_pack_archived_skill_groups_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="Iron Pack", owner=user)
    category = ContentSkillCategory.objects.all_content().create(name="Ferocity")
    skill = ContentSkill.objects.all_content().create(
        name="Berserker", category=category
    )
    item = _pack_item(pack, skill, user)

    request = _request(user)
    context = {
        "pack": pack,
        "archived_items": [{"pack_item": item, "content_object": skill}],
        "skill_groups": [
            {
                "category": category,
                "skills": [{"pack_item": item, "content_object": skill}],
            }
        ],
        "section_label": "Skills",
        "slug": "skill",
    }
    assert_equivalent("core/pack/pack_archived.html", context, request)


@pytest.mark.django_db
def test_pack_archived_empty_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="Iron Pack", owner=user)
    request = _request(user)
    context = {
        "pack": pack,
        "archived_items": [],
        "section_label": "Special Rules",
        "slug": "rule",
    }
    assert_equivalent("core/pack/pack_archived.html", context, request)
