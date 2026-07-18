"""Golden-equivalence test for the public user-profile page."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db.models import Count
from django.test import RequestFactory
from django.utils import timezone

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List
from gyrinx.core.models.pack import CustomContentPack


def _request(user, path="/user/testuser"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _build_context(profile_user, viewer, *, can_impersonate=False):
    """Mirror ``gyrinx.core.views.user.user``'s GET-branch context building."""
    is_own = viewer == profile_user

    public_lists = (
        List.objects.filter(
            owner=profile_user,
            status=List.LIST_BUILDING,
            archived=False,
            public=True,
        )
        .select_related("content_house", "owner")
        .annotate(star_count=Count("starred_by", distinct=True))
    )

    unlisted_lists = List.objects.none()
    if is_own:
        unlisted_lists = (
            List.objects.filter(
                owner=profile_user,
                status=List.LIST_BUILDING,
                archived=False,
                public=False,
            )
            .select_related("content_house", "owner")
            .annotate(star_count=Count("starred_by", distinct=True))
        )

    campaign_gangs_qs = List.objects.filter(
        owner=profile_user, status=List.CAMPAIGN_MODE, archived=False
    )
    if not is_own:
        campaign_gangs_qs = campaign_gangs_qs.filter(public=True)
    campaign_gangs = campaign_gangs_qs.select_related(
        "content_house", "owner", "campaign"
    ).annotate(star_count=Count("starred_by", distinct=True))

    campaigns_qs = Campaign.objects.filter(owner=profile_user, archived=False)
    if not is_own:
        campaigns_qs = campaigns_qs.filter(public=True)
    campaigns = campaigns_qs.annotate(star_count=Count("starred_by", distinct=True))

    packs_qs = CustomContentPack.objects.filter(owner=profile_user, archived=False)
    if not is_own:
        packs_qs = packs_qs.filter(listed=True)

    return {
        "profile_user": profile_user,
        "is_own_profile": is_own,
        "can_impersonate_user": can_impersonate,
        "public_lists": public_lists,
        "unlisted_lists": unlisted_lists,
        "campaign_gangs": campaign_gangs,
        "campaigns": campaigns,
        "packs": packs_qs,
        "show_packs": True,
    }


@pytest.mark.django_db
def test_user_profile_own_populated_matches_legacy(user, make_list, make_campaign):
    # A fixed, far-past join date keeps naturaltime stable across the two renders.
    user.date_joined = timezone.now() - timedelta(days=800)
    user.save(update_fields=["date_joined"])

    starred = make_list("Alpha", public=True)
    make_list("Beta", public=True)
    starred.starred_by.add(user)  # exercise the star-fill branch
    make_list("Hidden Gang", public=False)

    camp = make_campaign("Border War")
    make_list("Ash Wastes Crew", status=List.CAMPAIGN_MODE, campaign=camp)

    CustomContentPack.objects.create(name="Public Pack", owner=user, listed=True)
    CustomContentPack.objects.create(name="Private Pack", owner=user, listed=False)

    request = _request(user, f"/user/{user.username}")
    context = _build_context(user, user, can_impersonate=True)
    assert_equivalent("core/user.html", context, request)


@pytest.mark.django_db
def test_user_profile_own_empty_matches_legacy(user):
    request = _request(user, f"/user/{user.username}")
    context = _build_context(user, user, can_impersonate=False)
    assert_equivalent("core/user.html", context, request)


@pytest.mark.django_db
def test_user_profile_other_matches_legacy(user, make_user, make_list, make_campaign):
    other = make_user("otheruser", "password")
    other.date_joined = timezone.now() - timedelta(days=800)
    other.save(update_fields=["date_joined"])

    make_list("Solo List", owner=other, public=True)

    camp = make_campaign("Public War", owner=other, public=True)
    make_list(
        "Public Crew",
        owner=other,
        public=True,
        status=List.CAMPAIGN_MODE,
        campaign=camp,
    )

    CustomContentPack.objects.create(name="Listed Pack", owner=other, listed=True)

    request = _request(user, f"/user/{other.username}")
    context = _build_context(other, user, can_impersonate=False)
    assert_equivalent("core/user.html", context, request)
