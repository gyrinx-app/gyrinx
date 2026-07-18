"""Golden-equivalence test for the fighter counter edit page component."""

from __future__ import annotations

import pytest
from django.test import RequestFactory

from gyrinx.components.testing import assert_equivalent
from gyrinx.content.models import ContentCounter, ContentRollFlow, ContentRollTable
from gyrinx.core.forms.list import EditCounterForm, SpendCounterForm
from gyrinx.core.models.list import ListFighterCounter, ListFighterCounterSpend


def _request(user, path="/"):
    request = RequestFactory().get(path)
    request.user = user
    return request


@pytest.mark.django_db
def test_list_fighter_counters_edit_matches_legacy(user, make_list, make_list_fighter):
    lst = make_list("Iron Skulls", owner=user)
    fighter = make_list_fighter(lst, "Boss", owner=user)

    counter = ContentCounter.objects.create(
        name="Kill Count",
        description="Track how many fighters this one has taken out.",
    )

    # A stored value so can_spend is true and the spend form renders.
    ListFighterCounter.objects.create(
        fighter=fighter, counter=counter, value=3, owner=user
    )

    # A recorded free-form spend to exercise the "Recorded spends" section.
    ListFighterCounterSpend.objects.create(
        fighter=fighter,
        counter=counter,
        amount=2,
        reason="Traded for favours",
        owner=user,
    )

    # A roll flow (affordable) to exercise the "Spend on a roll" section.
    table = ContentRollTable.objects.create(
        name="Suit Evolution", dice=ContentRollTable.DICE_D6
    )
    ContentRollFlow.objects.create(
        name="Evolve Suit",
        description="Spend kills to evolve the suit.",
        counter=counter,
        cost=1,
        roll_table=table,
    )

    # Replicate the view's GET-branch object/context construction.
    existing = (
        fighter.counters.filter(counter=counter).select_related("counter").first()
    )
    current_value = existing.value if existing else 0

    form = EditCounterForm(counter=counter, current_value=current_value)
    spend_form = SpendCounterForm(counter=counter, current_value=current_value)

    flows = [
        {"flow": flow, "affordable": current_value >= flow.cost}
        for flow in counter.flows.select_related("roll_table").all()
    ]
    spends = fighter.counter_spends.filter(
        counter=counter, archived=False
    ).select_related("campaign_action")

    context = {
        "list": lst,
        "fighter": fighter,
        "counter": counter,
        "form": form,
        "spend_form": spend_form,
        "flows": flows,
        "spends": spends,
        "can_spend": current_value > 0 and not fighter.is_stash,
    }

    request = _request(user)
    assert_equivalent("core/list_fighter_counters_edit.html", context, request)
