"""Phase 5 of the cost-pinning programme (#1826): resolution honours amounts.

Every amount in production is null, so these branches are a no-op on deploy —
the whole existing suite proves that side. These tests hand-write amounts to
prove the branches are live and the precedence holds:

    user override → structural zeros → pinned amount → live fallback

including the signature demonstration: pinned gear moved between holders
whose price lists disagree does not change price.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipmentUpgrade,
    ContentFighterEquipmentListItem,
    ContentWeaponAccessory,
)
from gyrinx.core.handlers.equipment.reassignment import handle_equipment_reassignment
from gyrinx.core.models.list import (
    ListFighterEquipmentAssignment,
    PinState,
)
from gyrinx.core.tests.test_balance_sheet import (
    assert_reconciles,
    buy_equipment,
    fresh,
    hire_fighter,
)


@pytest.fixture
def weapon_assignment(user, make_list, make_list_fighter, make_equipment):
    lst = make_list("Pin Gang")
    fighter = make_list_fighter(lst, "Bob")
    equipment = make_equipment("Lasgun", cost=15)
    return ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )


def pin_base(assignment, amount, state=PinState.SOURCE):
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=amount, pinned_base_state=state
    )
    return fresh(assignment)


# --- The pinned amount is the price -----------------------------------------


@pytest.mark.django_db
def test_pinned_base_amount_is_the_price(weapon_assignment):
    assert weapon_assignment.base_cost_int() == 15  # live catalog before pinning
    pinned = pin_base(weapon_assignment, 5)
    assert pinned.base_cost_int() == 5
    assert pinned.cost_int() == 5


@pytest.mark.django_db
def test_pinned_base_amount_beats_equipment_list_discount(weapon_assignment):
    """The pin outranks the holder's live equipment-list price."""
    ContentFighterEquipmentListItem.objects.create(
        fighter=weapon_assignment.list_fighter.content_fighter,
        equipment=weapon_assignment.content_equipment,
        cost=8,
    )
    assert fresh(weapon_assignment).base_cost_int() == 8  # live discount applies
    pinned = pin_base(weapon_assignment, 5)
    assert pinned.base_cost_int() == 5  # pin wins over the discount


@pytest.mark.django_db
def test_pinned_base_amount_beats_annotation_shortcut(weapon_assignment):
    """A picker-annotated content instance must not outrank the pin."""
    pinned = pin_base(weapon_assignment, 5)
    # Simulate the with_cost_for_fighter() annotation the pickers add.
    pinned.content_equipment.cost_for_fighter = 99
    assert pinned.base_cost_int() == 5


@pytest.mark.django_db
def test_cost_override_beats_pinned_amount(weapon_assignment):
    """The user's manual base override stays top of the precedence."""
    pinned = pin_base(weapon_assignment, 5)
    ListFighterEquipmentAssignment.objects.filter(pk=pinned.pk).update(cost_override=3)
    assert fresh(pinned).base_cost_int() == 3


@pytest.mark.django_db
def test_pinned_component_amounts_are_the_prices(
    weapon_assignment, make_weapon_profile
):
    profile = make_weapon_profile(
        weapon_assignment.content_equipment, name="Hotshot", cost=10
    )
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    upgrade = ContentEquipmentUpgrade.objects.create(
        name="Mag", equipment=weapon_assignment.content_equipment, cost=12
    )
    weapon_assignment.weapon_profiles_field.add(profile)
    weapon_assignment.weapon_accessories_field.add(accessory)
    weapon_assignment.upgrades_field.add(upgrade)

    assert fresh(weapon_assignment).cost_int() == 15 + 10 + 8 + 12  # all live

    weapon_assignment.profile_rows.update(pinned_amount=4, pin_state=PinState.SOURCE)
    weapon_assignment.accessory_rows.update(pinned_amount=3, pin_state=PinState.SOURCE)
    weapon_assignment.upgrade_rows.update(pinned_amount=2, pin_state=PinState.DERIVED)
    assert fresh(weapon_assignment).cost_int() == 15 + 4 + 3 + 2


@pytest.mark.django_db
def test_pinned_derived_amount_beats_live_expression(weapon_assignment):
    """Expression accessories read their DERIVED amount, never re-evaluate."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Percent Scope", cost=0, cost_expression="ceil(cost_int * 0.5 / 5) * 5"
    )
    weapon_assignment.weapon_accessories_field.add(accessory)
    live = fresh(weapon_assignment).accessory_cost_int(accessory)
    assert live > 0  # expression evaluates against the 15 base

    weapon_assignment.accessory_rows.update(pinned_amount=1, pin_state=PinState.DERIVED)
    assert fresh(weapon_assignment).accessory_cost_int(accessory) == 1


# --- The signature demonstration ---------------------------------------------


@pytest.mark.django_db
def test_pinned_gear_does_not_reprice_when_moved(
    user,
    make_list,
    make_content_fighter,
    content_house,
    content_fighter,
    make_equipment,
    campaign,
):
    """Move fully-pinned gear between holders whose price lists disagree:
    the price must not move, and the books must reconcile.

    This is the behaviour the death-transfer fix (Phase 9) is built on,
    proven end-to-end before any real pin is ever written.
    """
    from gyrinx.core.models.action import ListActionType
    from gyrinx.core.models.list import List

    lst = make_list("Move Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        description="Stake",
        credits_delta=1000,
        update_credits=True,
    )

    cf_a = make_content_fighter(
        type="Scavvy", category="GANGER", house=content_house, base_cost=50
    )
    fighter_a = hire_fighter(user, lst, cf_a, name="Alfa")
    fighter_b = hire_fighter(user, lst, content_fighter, name="Bravo")

    equipment = make_equipment("Lasgun", cost=15)
    # A's list discounts the weapon to 5; B has no discount (would price 15).
    ContentFighterEquipmentListItem.objects.create(
        fighter=cf_a, equipment=equipment, cost=5
    )
    assignment = buy_equipment(user, lst, fighter_a, equipment)
    assert fresh(assignment).cost_int() == 5
    assert_reconciles(lst)

    # Hand-pin at the acquisition price (what Phase 7's choke point will do).
    ListFighterEquipmentAssignment.objects.filter(pk=assignment.pk).update(
        pinned_base_amount=5,
        pinned_base_state=PinState.SOURCE,
    )

    handle_equipment_reassignment(
        user=user,
        lst=fresh(lst),
        from_fighter=fresh(fighter_a),
        to_fighter=fresh(fighter_b),
        assignment=fresh(assignment),
    )

    # Unpinned, this gear re-prices to 15 on Bravo (the P6 repricing case);
    # pinned, the amount travels with the row and nothing moves.
    assert fresh(assignment).cost_int() == 5
    assert fresh(fighter_b).cost_int() == 100 + 5
    assert_reconciles(lst)


# --- Deploy safety ------------------------------------------------------------


@pytest.mark.django_db
def test_unpinned_rows_resolve_live_exactly_as_before(weapon_assignment):
    """UNPINNED (null amount) rows take the legacy path untouched."""
    assert weapon_assignment.pinned_base_state == PinState.UNPINNED
    assert weapon_assignment.base_cost_int() == 15
    ContentFighterEquipmentListItem.objects.create(
        fighter=weapon_assignment.list_fighter.content_fighter,
        equipment=weapon_assignment.content_equipment,
        cost=8,
    )
    assert fresh(weapon_assignment).base_cost_int() == 8  # live lookup still rules
