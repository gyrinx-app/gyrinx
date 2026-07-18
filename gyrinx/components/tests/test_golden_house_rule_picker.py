"""Golden-equivalence test for the add-house-rule target picker page."""

from __future__ import annotations

from django.core.paginator import Paginator

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.forms.pack import HOUSE_RULE_TARGET_CHOICES
from gyrinx.core.models.pack import CustomContentPack
from gyrinx.core.views.pack import _pack_url, _pack_weapon_picker_data


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_house_rule_picker_weapons_matches_legacy(user, make_weapon_with_profile):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)

    # A library weapon so the weapon-profile tab renders the populated
    # ``weapon_groups`` branch (bridged table + pagination + filter form).
    make_weapon_with_profile()

    request = _request(user)
    # Build the context exactly as the view's GET (weapon-profile) branch does.
    picker_data = _pack_weapon_picker_data(request, pack, include_pack_weapons=True)
    page = picker_data["page_obj"]
    context = {
        "pack": pack,
        "target_type": "weapon-profile",
        "target_label": "weapons",
        "target_choices": HOUSE_RULE_TARGET_CHOICES,
        "weapon_groups": picker_data["weapon_groups"],
        "fighter_groups": [],
        "categories": picker_data["categories"],
        "selected_cats": picker_data["selected_cats"],
        "cat_filter_active": picker_data["cat_filter_active"],
        "page_obj": page,
        "paginator": picker_data["paginator"],
        "is_paginated": page.has_other_pages(),
        "search_query": picker_data["search_query"],
        "back_url": _pack_url(pack, "house-rule"),
        "filter_hidden_inputs": [{"name": "target_type", "value": "weapon-profile"}],
        "table_hidden_inputs": [{"name": "target_type", "value": "weapon-profile"}],
    }
    assert_equivalent("core/pack/house_rule_picker.html", context, request)


@pytest.mark.django_db
def test_house_rule_picker_fighters_matches_legacy(user, content_fighter):
    pack = CustomContentPack.objects.create(name="My Pack", owner=user)

    request = _request(user)
    # A hand-built fighter group mirrors the plain-dict rows the view's fighter
    # branch produces, exercising the inline statline table (first_of_group
    # borders, the "-" default cell, and the house sub-label).
    columns = [
        {"name": "M", "field_name": "movement", "first_of_group": False},
        {"name": "WS", "field_name": "weapon_skill", "first_of_group": True},
    ]
    cells = [
        {"value": "5", "first_of_group": False},
        {"value": "", "first_of_group": True},
    ]
    fighter_groups = [
        {
            "category": "Juve",
            "statline_groups": [
                {
                    "columns": columns,
                    "rows": [
                        {
                            "fighter": content_fighter,
                            "rule_view": {"entries": [], "html": ""},
                            "cells": cells,
                        }
                    ],
                }
            ],
        }
    ]
    paginator = Paginator([content_fighter], 25)
    page = paginator.get_page(1)
    context = {
        "pack": pack,
        "target_type": "fighter",
        "target_label": "fighters & vehicles",
        "target_choices": HOUSE_RULE_TARGET_CHOICES,
        "weapon_groups": [],
        "fighter_groups": fighter_groups,
        "categories": [],
        "selected_cats": set(),
        "cat_filter_active": False,
        "page_obj": page,
        "paginator": paginator,
        "is_paginated": False,
        "search_query": "",
        "back_url": _pack_url(pack, "house-rule"),
        "filter_hidden_inputs": [{"name": "target_type", "value": "fighter"}],
        "table_hidden_inputs": [{"name": "target_type", "value": "fighter"}],
    }
    assert_equivalent("core/pack/house_rule_picker.html", context, request)
