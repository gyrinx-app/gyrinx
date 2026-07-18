"""Golden-equivalence test: pack_lists component matches its legacy template."""

from __future__ import annotations

import pytest
from django.core.paginator import Paginator
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models.house import ContentHouse
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_pack_lists_matches_legacy(user, make_list, list_with_campaign):
    pack = CustomContentPack.objects.create(owner=user, name="Cool Pack")

    # One subscribed list (shown in its own section).
    subscribed = make_list("Subscribed Gang", owner=user)
    subscribed.packs.add(pack)

    # An available list in list-building mode, plus list_with_campaign (a
    # CAMPAIGN_MODE list owned by ``user``) to exercise both badge branches.
    make_list("Available Gang", owner=user)

    # Replicate the view's GET-branch querysets/context exactly.
    available_qs = (
        List.objects.filter(owner=user, archived=False)
        .exclude(pk__in=[subscribed.pk])
        .select_related("content_house", "campaign")
        .order_by("name", "id")
    )
    paginator = Paginator(available_qs, 10)
    page_obj = paginator.get_page(1)

    subscribed_qs = (
        List.objects.filter(owner=user, archived=False, packs=pack)
        .select_related("content_house", "campaign")
        .order_by("name", "id")
    )

    house_ids = available_qs.order_by().values_list("content_house_id", flat=True)
    houses = (
        ContentHouse.objects.all_content().filter(id__in=house_ids).order_by("name")
    )

    request = _request(user)
    context = {
        "pack": pack,
        "lists": page_obj.object_list,
        "subscribed_lists": subscribed_qs,
        "houses": houses,
        "current_tab": "all",
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "paginator": paginator,
        "object_list": page_obj.object_list,
        "is_owner": True,
        "can_edit": True,
    }
    assert_equivalent("core/pack/pack_lists.html", context, request)
