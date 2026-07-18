"""Golden-equivalence test for the roll-result remove confirmation page."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_roll_result_remove_matches_legacy(
    user, make_list, make_list_fighter
):
    from gyrinx.content.models import (
        ContentCounter,
        ContentRollTable,
        ContentRollTableRow,
    )
    from gyrinx.core.models.list import ListFighterRollResult

    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    table = ContentRollTable.objects.create(
        name="Power Boost Table",
        dice=ContentRollTable.DICE_D6,
    )
    row = ContentRollTableRow.objects.create(
        table=table,
        roll_value="1-3",
        name="Minor Boost",
        description="Improve Strength by 1.",
        rating_increase=10,
        sort_order=1,
    )
    counter = ContentCounter.objects.create(
        name="Kill Count",
        description="Tracks kills",
        display_order=0,
    )
    roll_result = ListFighterRollResult.objects.create(
        fighter=fighter,
        row=row,
        counter=counter,
        counter_cost=4,
        rating_increase=10,
        notes="Rolled a 2.",
        owner=user,
    )

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "roll_result": roll_result,
    }
    assert_equivalent("core/list_fighter_roll_result_remove.html", context, request)
