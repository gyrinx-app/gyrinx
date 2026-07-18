"""Golden-equivalence test: invitation_pack_setup matches its legacy template."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_invitation_pack_setup_matches_legacy(user, make_list, make_campaign):
    from gyrinx.core.models.pack import CustomContentPack

    lst = make_list("Iron Skulls", owner=user)
    campaign = make_campaign("Underhive Wars")

    required_pack = CustomContentPack.objects.create(
        name="Required Rules",
        owner=user,
        summary="Adds <b>new</b> fighters and gear to the campaign.",
        listed=True,
    )
    optional_pack = CustomContentPack.objects.create(
        name="Optional Extras",
        owner=user,
        listed=True,
    )
    # The view annotates each pack with ``is_required`` before rendering.
    required_pack.is_required = True
    optional_pack.is_required = False
    suggested_packs = [required_pack, optional_pack]

    request = _request(user)
    context = {
        "list": lst,
        "campaign": campaign,
        "suggested_packs": suggested_packs,
    }
    assert_equivalent("core/list/invitation_pack_setup.html", context, request)


@pytest.mark.django_db
def test_invitation_pack_setup_empty_matches_legacy(user, make_list, make_campaign):
    lst = make_list("Iron Skulls", owner=user)
    campaign = make_campaign("Underhive Wars")

    request = _request(user)
    context = {
        "list": lst,
        "campaign": campaign,
        "suggested_packs": [],
    }
    assert_equivalent("core/list/invitation_pack_setup.html", context, request)
