"""Golden-equivalence test: packs (Customisation) list page matches legacy."""

from __future__ import annotations

import pytest
from django.core.paginator import Paginator
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/packs/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_packs_matches_legacy(user):
    # A listed pack with rich-text summary, an unlisted pack with no summary
    # (exercises the {% if not pack.listed %} and {% if pack.summary %} branches),
    # and a featured pack (exercises the featured column include).
    CustomContentPack.objects.create(
        owner=user,
        name="Ash Wastes Pack",
        summary="<p>Extra <b>wasteland</b> gear.</p>",
        listed=True,
    )
    CustomContentPack.objects.create(
        owner=user,
        name="Hidden Pack",
        summary="",
        listed=False,
    )
    featured_pack = CustomContentPack.objects.create(
        owner=user,
        name="Featured Pack",
        summary="Great stuff.",
        featured=True,
        listed=True,
        featured_description="<p>Editor's pick.</p>",
    )

    # Replicate the ListView's GET-branch queryset + pagination.
    queryset = (
        CustomContentPack.objects.filter(archived=False, owner=user)
        .select_related("owner", "owner__profile")
        .order_by("name")
    )
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(1)

    featured_packs = (
        CustomContentPack.objects.filter(id__in=[featured_pack.id])
        .select_related("owner")
        .order_by("-created")
    )

    request = _request(user)
    context = {
        "packs": page_obj.object_list,
        "featured_packs": featured_packs,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "paginator": paginator,
        "object_list": page_obj.object_list,
    }
    assert_equivalent("core/pack/packs.html", context, request)


@pytest.mark.django_db
def test_packs_empty_matches_legacy(user):
    # No packs and no featured column: exercises the {% empty %} branch and the
    # falsy {% if featured_packs %} path (still authenticated -> "Create" link).
    queryset = CustomContentPack.objects.none()
    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(1)

    request = _request(user)
    context = {
        "packs": page_obj.object_list,
        "page_obj": page_obj,
        "is_paginated": page_obj.has_other_pages(),
        "paginator": paginator,
        "object_list": page_obj.object_list,
    }
    assert_equivalent("core/pack/packs.html", context, request)
