"""Golden-equivalence test for the roll-flow confirm page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import (
    ContentCounter,
    ContentModStat,
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
)


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_roll_flow_confirm_matches_legacy(
    user, make_list, make_list_fighter
):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    counter = ContentCounter.objects.create(name="Boost Points")
    counter.restricted_to_fighters.add(fighter.content_fighter)

    table = ContentRollTable.objects.create(
        name="Power Boost Table", dice=ContentRollTable.DICE_D6
    )
    row = ContentRollTableRow.objects.create(
        table=table,
        roll_value="4",
        name="Enhanced Reflexes",
        description="Gain +1 Initiative.",
        rating_increase=15,
        sort_order=1,
    )
    mod = ContentModStat.objects.create(stat="strength", mode="improve", value="1")
    row.modifiers.add(mod)

    flow = ContentRollFlow.objects.create(
        name="Power Boost", counter=counter, cost=2, roll_table=table
    )

    # Rebuild the confirm-step state the way the view's GET branch derives it.
    dice = [4]
    rolled_value = table.roll_value_from_dice(dice)
    matched_row = table.row_for_roll(rolled_value)
    roll_url = reverse(
        "core:list-fighter-roll-flow", args=(lst.id, fighter.id, flow.id)
    )

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "flow": flow,
        "table": table,
        "dice": dice,
        "rolled_value": rolled_value,
        "row": matched_row,
        "modifiers": list(matched_row.modifiers.all()),
        "roll_url": roll_url,
    }
    assert_equivalent("core/list_fighter_roll_flow_confirm.html", context, request)
