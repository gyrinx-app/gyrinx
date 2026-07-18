"""Golden-equivalence test: fighter roll-results edit page matches legacy."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


def _results(fighter):
    return fighter.roll_results.filter(archived=False).select_related(
        "row__table", "flow", "counter"
    )


@pytest.mark.django_db
def test_roll_results_edit_empty_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)
    request = _request(user)
    context = {"list": lst, "fighter": fighter, "results": _results(fighter)}
    assert_equivalent("core/list_fighter_roll_results_edit.html", context, request)


@pytest.mark.django_db
def test_roll_results_edit_populated_matches_legacy(user, make_list, make_list_fighter):
    from gyrinx.content.models import (
        ContentCounter,
        ContentRollTable,
        ContentRollTableRow,
    )
    from gyrinx.core.models.list import ListFighterRollResult

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    table = ContentRollTable.objects.create(
        name="Power Boost Table", dice=ContentRollTable.DICE_D6
    )
    row = ContentRollTableRow.objects.create(
        table=table,
        roll_value="6",
        sort_order=0,
        name="Strength Boost",
        description="Gain +1 Strength.",
        rating_increase=5,
    )
    counter = ContentCounter.objects.create(name="Glitches")

    # A full result: description, rating increase, counter cost + counter, notes.
    ListFighterRollResult.objects.create(
        fighter=fighter,
        row=row,
        counter=counter,
        counter_cost=3,
        rating_increase=5,
        notes="Rolled a natural six.",
    )
    # A minimal result exercising the absent-conditional branches (no
    # description, no rating increase, no counter, no notes).
    bare_row = ContentRollTableRow.objects.create(
        table=table,
        roll_value="1",
        sort_order=1,
        name="No Effect",
    )
    ListFighterRollResult.objects.create(fighter=fighter, row=bare_row)

    request = _request(user)
    context = {"list": lst, "fighter": fighter, "results": _results(fighter)}
    assert_equivalent("core/list_fighter_roll_results_edit.html", context, request)
