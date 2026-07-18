"""Golden-equivalence test for core/pack/pack_item_edit.html."""

from __future__ import annotations

import pytest
from django.contrib.contenttypes.models import ContentType
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.metadata import ContentRule
from gyrinx.core.forms.pack import ContentRuleForm
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_item_edit_rule_matches_legacy(user):
    # Mirror the GET branch of edit_pack_item for a non-fighter, non-weapon
    # content type (a Special Rule), which renders the plain ``{{ form }}``
    # variant of the else branch.
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    rule = ContentRule.objects.create(
        name="My Custom Rule", description="Does a thing."
    )
    ct = ContentType.objects.get_for_model(ContentRule)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=rule.id, owner=user
    )

    form = ContentRuleForm(instance=rule)
    back_url = reverse("core:pack", args=(pack.id,)) + f"#item-{pack_item.id}"
    context = {
        "form": form,
        "pack": pack,
        "pack_item": pack_item,
        "content_obj": rule,
        "content_fighter": None,
        "label": "Special Rule",
        "icon": "bi-journal-text",
        "slug": "rule",
        "back_url": back_url,
        "is_fighter": False,
    }
    request = _request(user)
    assert_equivalent("core/pack/pack_item_edit.html", context, request)
