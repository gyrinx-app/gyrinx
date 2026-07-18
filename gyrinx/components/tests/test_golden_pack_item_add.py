"""Golden-equivalence tests for the pack "add content item" form page.

The one legacy template drives several variants via context flags, so we
exercise the representative branches: a plain form (rule), the gear "add
modifiers later" hint, the weapon-accessory mod picker, the fighter two-step
next-step hint, and the single-profile weapon stat inputs.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.weapon import ContentWeaponTrait
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import (
    _CONTENT_TYPE_BY_SLUG,
    _build_weapon_stat_context,
    _form_kwargs,
    _pack_url,
    _singularize_label,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _base_context(slug, pack):
    """Replicate the view's GET-branch context for a content-type slug."""
    entry = _CONTENT_TYPE_BY_SLUG[slug]
    form = entry.form_class(**_form_kwargs(entry, pack))
    return {
        "form": form,
        "pack": pack,
        "label": _singularize_label(entry),
        "icon": entry.icon,
        "slug": entry.slug,
        "back_url": _pack_url(pack, entry.slug),
    }


@pytest.mark.django_db
def test_pack_item_add_rule_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    request = _request(user)
    context = _base_context("rule", pack)
    assert_equivalent("core/pack/pack_item_add.html", context, request)


@pytest.mark.django_db
def test_pack_item_add_gear_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    request = _request(user)
    context = _base_context("gear", pack)
    assert_equivalent("core/pack/pack_item_add.html", context, request)


@pytest.mark.django_db
def test_pack_item_add_weapon_accessory_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    request = _request(user)
    context = _base_context("weapon-accessory", pack)
    assert_equivalent("core/pack/pack_item_add.html", context, request)


@pytest.mark.django_db
def test_pack_item_add_fighter_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    request = _request(user)
    context = _base_context("fighter", pack)
    context["next_step_hint"] = (
        "You can configure the Fighter statline on the next screen. "
        "Skill trees and Psyker disciplines can be set after you create "
        "this Fighter — open it from the pack and use Edit."
    )
    context["next_step_button"] = "Next →"
    assert_equivalent("core/pack/pack_item_add.html", context, request)


@pytest.mark.django_db
def test_pack_item_add_weapon_single_matches_legacy(user):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)
    # A base-library trait so the include's trait picker loop is exercised.
    ContentWeaponTrait.objects.create(name="Plasma")
    request = _request(user)
    context = _base_context("weapon", pack)
    context["profile_mode"] = "single"
    context["weapon_traits"] = ContentWeaponTrait.objects.with_packs([pack])
    context["weapon_stat_fields"] = _build_weapon_stat_context(request)
    context["selected_trait_ids"] = set()
    assert_equivalent("core/pack/pack_item_add.html", context, request)
