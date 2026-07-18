"""Golden-equivalence test for the roll-flow roll page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import (
    ContentCounter,
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
)
from gyrinx.core.forms.list import RollFlowDiceForm
from gyrinx.core.models.list import ListFighterCounter


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_roll_flow_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    counter = ContentCounter.objects.create(name="Boost Points")
    counter.restricted_to_fighters.add(fighter.content_fighter)

    table = ContentRollTable.objects.create(
        name="Power Boost Table",
        description="Roll to boost your fighter.",
        dice=ContentRollTable.DICE_D6,
    )
    ContentRollTableRow.objects.create(
        table=table,
        roll_value="1-3",
        name="Enhanced Reflexes",
        description="Gain +1 Initiative.",
        rating_increase=15,
        sort_order=1,
    )
    ContentRollTableRow.objects.create(
        table=table,
        roll_value="4-6",
        name="Iron Jaw",
        rating_increase=5,
        sort_order=2,
    )

    flow = ContentRollFlow.objects.create(
        name="Power Boost",
        description="Spend points to improve your fighter.",
        counter=counter,
        cost=2,
        roll_table=table,
    )

    # Give the fighter enough counter points that the flow is affordable.
    ListFighterCounter.objects.create(
        fighter=fighter, counter=counter, value=3, owner=user
    )

    # Rebuild the GET-branch context exactly as the view does.
    existing = fighter.counters.filter(counter=flow.counter).first()
    counter_value = existing.value if existing else 0
    affordable = counter_value >= flow.cost
    counter_url = reverse(
        "core:list-fighter-counter-edit", args=(lst.id, fighter.id, flow.counter.id)
    )
    form = RollFlowDiceForm(dice_count=table.dice_count)

    request = _request(user)
    context = {
        "list": lst,
        "fighter": fighter,
        "flow": flow,
        "table": table,
        "rows": table.rows.all(),
        "form": form,
        "counter_value": counter_value,
        "affordable": affordable,
        "counter_url": counter_url,
        "in_campaign": bool(lst.campaign),
    }
    assert_equivalent("core/list_fighter_roll_flow.html", context, request)
