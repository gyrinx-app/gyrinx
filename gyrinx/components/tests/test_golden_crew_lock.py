"""Golden-equivalence tests: crew_lock page matches its legacy template."""

from __future__ import annotations

from typing import Any

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.core.models.battle import Battle
from gyrinx.core.models.crew import Crew


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _make_crew(user, lst, **crew_kwargs) -> Crew:
    battle = Battle.objects.create(campaign=lst.campaign, mission="Ambush", owner=user)
    return Crew.objects.create(battle=battle, list=lst, owner=user, **crew_kwargs)


def _context(crew: Crew) -> dict[str, Any]:
    """Rebuild the context the GET branch of ``crew_lock`` renders with."""
    chosen_fighters = list(crew.chosen_fighters.all())
    return {
        "crew": crew,
        "battle": crew.battle,
        "chosen_fighters": chosen_fighters,
        "whole_gang": not chosen_fighters and not (crew.random_spec or "").strip(),
    }


@pytest.mark.django_db
def test_crew_lock_whole_gang_matches_legacy(user, list_with_campaign):
    # No picks, no random draw -> the whole eligible gang attends.
    crew = _make_crew(user, list_with_campaign)
    request = _request(user)
    assert_equivalent("core/crew/crew_lock.html", _context(crew), request)


@pytest.mark.django_db
def test_crew_lock_pending_roll_matches_legacy(
    user, list_with_campaign, make_list_fighter
):
    # Draft crew with a random spec -> pending_roll, and chosen fighters -> the
    # <strong> random-draw clause and the plural "fighters".
    crew = _make_crew(user, list_with_campaign, random_spec="D3+2")
    fighters = [make_list_fighter(list_with_campaign, f"Ganger {i}") for i in range(2)]
    crew.chosen_fighters.set(fighters)
    request = _request(user)
    assert_equivalent("core/crew/crew_lock.html", _context(crew), request)


@pytest.mark.django_db
def test_crew_lock_single_chosen_matches_legacy(
    user, list_with_campaign, make_list_fighter
):
    # One chosen fighter, no random spec -> "Confirm crew", singular "fighter".
    crew = _make_crew(user, list_with_campaign)
    crew.chosen_fighters.set([make_list_fighter(list_with_campaign, "Boss")])
    request = _request(user)
    assert_equivalent("core/crew/crew_lock.html", _context(crew), request)
