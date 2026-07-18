"""Golden-equivalence test for the add/edit house-rule form page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse
from django.utils.safestring import mark_safe

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.pack import ContentHouseRuleForm
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import _kind_picker_entries, _statline_field_names


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_house_rule_form_matches_legacy(user, content_fighter):
    """Fighter-target add flow, mirroring ``add_house_rule`` GET (is_new=True)."""
    pack = CustomContentPack.objects.create(name="Ash Wastes Rules", owner=user)
    target = content_fighter
    target_type = "fighter"
    mod_kind = "stat"

    initial = {"target_type": target_type, "target_id": str(target.id)}
    form = ContentHouseRuleForm(
        initial=initial,
        mod_kind=mod_kind,
        target_type=target_type,
        available_stat_field_names=_statline_field_names(target),
        pack=pack,
    )

    kind_picker = _kind_picker_entries(
        pack,
        target_type,
        target.id,
        current_kind=mod_kind,
        base_url=reverse("core:pack-house-rule-add", args=(pack.id,)),
    )

    # A rule_view with entries exercises the trailing "added/removed" row and
    # the pack_mod_view_line include.
    rule_view = {
        "entries": [{"name": "Fearsome", "status": "added"}],
        "html": mark_safe('<span class="tooltipped">Fearsome</span>'),
    }

    request = _request(user)
    context = {
        "pack": pack,
        "form": form,
        "target": target,
        "target_label": str(target),
        "target_type": target_type,
        "trait_view": None,
        "rule_view": rule_view,
        "mod_kind": mod_kind,
        "kind_picker": kind_picker,
        "is_new": True,
        "back_url": reverse("core:pack-house-rule-picker", args=(pack.id,))
        + f"?target_type={target_type}",
    }
    assert_equivalent("core/pack/house_rule_form.html", context, request)
