"""Golden-equivalence test for the campaign battles list page."""

from __future__ import annotations

import datetime

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.battle import Battle


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _context(campaign, show_archived=False):
    """Rebuild the view's GET-branch context for a given archived state."""
    battles = (
        campaign.battles.filter(archived=show_archived)
        .select_related("owner")
        .prefetch_related("participants", "winners")
        .order_by("-date", "-created")
    )
    return {
        "campaign": campaign,
        "battles": battles,
        "show_archived": show_archived,
        "archived_count": campaign.battles.filter(archived=True).count(),
    }


@pytest.mark.django_db
def test_campaign_battles_empty_matches_legacy(user, campaign):
    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_battles.html", _context(campaign), request
    )


@pytest.mark.django_db
def test_campaign_battles_with_battles_matches_legacy(user, campaign, make_list):
    gang_a = make_list("Iron Skulls", owner=user)
    gang_b = make_list("Rusty Nails", owner=user)
    battle = Battle.objects.create(
        campaign=campaign,
        owner=user,
        mission="Sabotage",
        date=datetime.date(2024, 3, 14),
    )
    battle.participants.set([gang_a, gang_b])
    battle.winners.set([gang_a])

    # An archived battle so the "View N archived →" toggle link renders.
    Battle.objects.create(
        campaign=campaign,
        owner=user,
        mission="Ambush",
        archived=True,
    )

    request = _request(user)
    assert_equivalent(
        "core/campaign/campaign_battles.html", _context(campaign), request
    )


@pytest.mark.django_db
def test_campaign_battles_archived_view_matches_legacy(user, campaign):
    Battle.objects.create(
        campaign=campaign,
        owner=user,
        mission="Ambush",
        archived=True,
    )
    request = _request(user, path="/?archived=1")
    assert_equivalent(
        "core/campaign/campaign_battles.html",
        _context(campaign, show_archived=True),
        request,
    )
