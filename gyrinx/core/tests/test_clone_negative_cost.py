"""
Tests for cloning lists with negative cost equipment and upgrades.

These tests verify that negative costs are properly preserved when cloning
a list for a campaign. This is a regression test for issue #1334.

Bug: When a gang with negative-costed items or item upgrades is cloned,
the negative costs are not carried across into the rating of the campaign gang.

The root cause is that rating_current is stored in a PositiveIntegerField,
and the facts_from_db() method clamps the value to max(0, rating) to avoid
database constraint violations. This causes negative costs to be lost.

Note: These tests demonstrate the bug by comparing cost_int() (the calculated
value which can be negative) with rating_current (the stored/cached value
which is clamped to 0). The tests will fail until the bug is fixed.
"""

import pytest

from gyrinx.content.models import ContentEquipment, ContentEquipmentUpgrade
from gyrinx.core.models.list import List, ListFighter


@pytest.mark.django_db
def test_clone_list_with_negative_cost_equipment(
    make_list,
    make_list_fighter,
    content_equipment_categories,
):
    """
    Test that equipment with a negative cost is properly reflected in the
    cloned list's rating.

    Scenario: A fighter has a piece of equipment that costs -40 credits.
    When the list is cloned, the negative cost should still affect the rating.

    This is test case 1 from issue #1334: Equipment with negative cost.

    The bug: The cloned list's rating_current is calculated using facts_from_db(),
    which clamps the value to max(0, rating) because rating_current is a
    PositiveIntegerField. This causes negative equipment costs to be lost.
    """
    # Create a list
    list_: List = make_list("Test List with Negative Cost Equipment")

    # Create a fighter with base cost 100
    fighter: ListFighter = make_list_fighter(list_, "Fighter with Discount Item")

    # Create equipment with a negative cost (-40 credits)
    negative_cost_equipment = ContentEquipment.objects.create(
        name="Discount Item",
        cost="-40",  # Negative cost
        category=content_equipment_categories[0],
    )

    # Assign the negative cost equipment to the fighter
    fighter.assign(negative_cost_equipment)

    # Calculate expected costs
    # Fighter base cost: 100 (from content_fighter fixture)
    # Equipment cost: -40
    # Expected fighter total: 100 + (-40) = 60
    # Expected list rating: 60
    expected_fighter_cost = 60
    expected_list_rating = 60

    # Verify the fighter's cost_int() returns the correct value (this works correctly)
    fighter.refresh_from_db()
    assert fighter.cost_int() == expected_fighter_cost, (
        f"Fighter cost_int() should be {expected_fighter_cost}, got {fighter.cost_int()}"
    )

    # Clone the list (simulating adding to campaign)
    cloned_list: List = list_.clone(name="Cloned List")

    # Get the cloned fighter and verify its cost_int() is correct
    cloned_fighter = cloned_list.fighters().first()
    cloned_fighter_cost = cloned_fighter.cost_int()

    assert cloned_fighter_cost == expected_fighter_cost, (
        f"Cloned fighter cost_int() should be {expected_fighter_cost}, got {cloned_fighter_cost}"
    )

    # THE BUG: The cloned list's rating_current is clamped to 0 because
    # facts_from_db() uses max(0, rating) when storing to the PositiveIntegerField.
    # This causes the rating to be incorrect.
    cloned_list.refresh_from_db()
    cloned_rating = cloned_list.rating_current

    # This assertion demonstrates the bug - rating_current should match the
    # actual calculated rating (which includes negative equipment costs)
    assert cloned_rating == expected_list_rating, (
        f"Cloned list rating_current should be {expected_list_rating}, got {cloned_rating}. Negative cost effect was lost during cloning."
    )


@pytest.mark.django_db
def test_clone_list_for_campaign_with_negative_cost_equipment(
    make_list,
    make_list_fighter,
    make_campaign,
    content_equipment_categories,
):
    """
    Test that equipment with a negative cost is properly reflected when
    cloning a list for a campaign.

    This specifically tests the for_campaign parameter which is used when
    adding a list to a campaign.
    """
    # Create a list
    list_: List = make_list("Test List for Campaign")
    campaign = make_campaign("Test Campaign")

    # Create a fighter with base cost 100
    fighter: ListFighter = make_list_fighter(list_, "Fighter with Discount Item")

    # Create equipment with a negative cost (-40 credits)
    negative_cost_equipment = ContentEquipment.objects.create(
        name="Discount Item",
        cost="-40",  # Negative cost
        category=content_equipment_categories[0],
    )

    # Assign the negative cost equipment to the fighter
    fighter.assign(negative_cost_equipment)

    # Calculate expected costs
    expected_list_rating = 60  # 100 (fighter) + (-40) (equipment)

    # Verify the fighter's cost_int() returns the correct value
    fighter.refresh_from_db()
    assert fighter.cost_int() == expected_list_rating, (
        f"Fighter cost_int() should be {expected_list_rating}, got {fighter.cost_int()}"
    )

    # Clone the list for campaign
    cloned_list: List = list_.clone(for_campaign=campaign)

    # THE BUG: The cloned list's rating_current should reflect the actual
    # rating including negative equipment costs
    cloned_list.refresh_from_db()
    cloned_rating = cloned_list.rating_current

    assert cloned_rating == expected_list_rating, (
        f"Campaign list rating_current should be {expected_list_rating}, got {cloned_rating}. Negative cost effect was lost during cloning."
    )


@pytest.mark.django_db
def test_clone_list_with_positive_equipment_and_negative_upgrade(
    make_list,
    make_list_fighter,
    content_equipment_categories,
):
    """
    Test that equipment with a positive cost but a negative upgrade cost
    is properly reflected in the cloned list's rating when the net cost
    is less than the equipment's base cost.

    Scenario: A fighter has equipment that costs 50 credits, with an upgrade
    that costs -30 credits. The net equipment cost is 20 credits.
    When the list is cloned, the negative upgrade cost should still affect the rating.

    This is test case 2 from issue #1334: Equipment with positive cost but
    upgrade with negative cost so that net cost is less than base cost.

    NOTE: This test currently passes because the net equipment cost (20) is
    positive, so the clamping doesn't affect the result. The bug only manifests
    when the overall rating goes negative.
    """
    # Create a list
    list_: List = make_list("Test List with Negative Upgrade")

    # Create a fighter with base cost 100
    fighter: ListFighter = make_list_fighter(list_, "Fighter with Upgraded Item")

    # Create equipment with a positive cost (50 credits)
    equipment = ContentEquipment.objects.create(
        name="Upgradeable Item",
        cost="50",  # Positive cost
        category=content_equipment_categories[0],
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,  # Allow multiple upgrades
    )

    # Create an upgrade with a negative cost (-30 credits)
    negative_upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Discount Upgrade",
        cost=-30,  # Negative cost
        position=0,
    )

    # Assign the equipment to the fighter and add the upgrade
    assignment = fighter.assign(equipment)
    assignment.upgrades_field.add(negative_upgrade)
    assignment.save()

    # Recalculate cached values after adding upgrade
    assignment.facts_from_db(update=True)
    fighter.facts_from_db(update=True)
    list_.facts_from_db(update=True)

    # Calculate expected costs
    # Fighter base cost: 100 (from content_fighter fixture)
    # Equipment cost: 50
    # Upgrade cost: -30
    # Expected equipment total: 50 + (-30) = 20
    # Expected fighter total: 100 + 20 = 120
    # Expected list rating: 120
    expected_equipment_cost = 20
    expected_fighter_cost = 120
    expected_list_rating = 120

    # Verify original equipment assignment has correct cost via cost_int()
    original_assignment = fighter.assignments()[0]
    original_assignment_cost = original_assignment.cost_int()

    assert original_assignment_cost == expected_equipment_cost, (
        f"Original assignment cost_int() should be {expected_equipment_cost}, got {original_assignment_cost}"
    )

    # Clone the list
    cloned_list: List = list_.clone(name="Cloned List")

    # Verify the cloned fighter has the correct cost via cost_int()
    cloned_fighter = cloned_list.fighters().first()
    cloned_fighter_cost = cloned_fighter.cost_int()

    assert cloned_fighter_cost == expected_fighter_cost, (
        f"Cloned fighter cost_int() should be {expected_fighter_cost}, got {cloned_fighter_cost}"
    )

    # Verify the cloned equipment assignment has the correct cost via cost_int()
    cloned_assignment = cloned_fighter.assignments()[0]
    cloned_assignment_cost = cloned_assignment.cost_int()

    assert cloned_assignment_cost == expected_equipment_cost, (
        f"Cloned assignment cost_int() should be {expected_equipment_cost}, got {cloned_assignment_cost}"
    )

    # Verify the cloned list's rating_current is correct
    # This test passes because the overall rating (120) is positive
    cloned_list.refresh_from_db()
    cloned_rating = cloned_list.rating_current

    assert cloned_rating == expected_list_rating, (
        f"Cloned list rating_current should be {expected_list_rating}, got {cloned_rating}"
    )


@pytest.mark.django_db
def test_clone_list_with_fully_negative_equipment_total(
    make_list,
    make_list_fighter,
    content_equipment_categories,
):
    """
    Test the edge case where equipment with a positive cost has an upgrade
    with a negative cost large enough to make the total equipment cost negative.

    Scenario: Equipment costs 30 credits, upgrade costs -50 credits.
    Net equipment cost: -20 credits.

    This test demonstrates the bug with negative upgrade costs - the cloned
    list's rating_current is clamped, losing the negative cost effect.
    """
    # Create a list
    list_: List = make_list("Test List with Fully Negative Equipment")

    # Create a fighter with base cost 100
    fighter: ListFighter = make_list_fighter(list_, "Fighter with Very Discounted Item")

    # Create equipment with a positive cost (30 credits)
    equipment = ContentEquipment.objects.create(
        name="Heavily Discounted Item",
        cost="30",  # Positive cost
        category=content_equipment_categories[0],
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,
    )

    # Create an upgrade with a large negative cost (-50 credits)
    large_negative_upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Major Discount Upgrade",
        cost=-50,  # Large negative cost
        position=0,
    )

    # Assign the equipment to the fighter and add the upgrade
    assignment = fighter.assign(equipment)
    assignment.upgrades_field.add(large_negative_upgrade)
    assignment.save()

    # Recalculate cached values
    assignment.facts_from_db(update=True)
    fighter.facts_from_db(update=True)
    list_.facts_from_db(update=True)

    # Calculate expected costs
    # Fighter base cost: 100
    # Equipment cost: 30
    # Upgrade cost: -50
    # Expected equipment total: 30 + (-50) = -20
    # Expected fighter total: 100 + (-20) = 80
    # Expected list rating: 80
    expected_equipment_cost = -20
    expected_fighter_cost = 80
    expected_list_rating = 80

    # Verify equipment assignment cost_int() returns the correct value
    original_assignment = fighter.assignments()[0]
    original_assignment_cost = original_assignment.cost_int()

    assert original_assignment_cost == expected_equipment_cost, (
        f"Original assignment cost_int() should be {expected_equipment_cost}, got {original_assignment_cost}"
    )

    # Verify fighter cost_int() returns the correct value
    fighter.refresh_from_db()
    assert fighter.cost_int() == expected_fighter_cost, (
        f"Fighter cost_int() should be {expected_fighter_cost}, got {fighter.cost_int()}"
    )

    # Clone the list
    cloned_list: List = list_.clone(name="Cloned List")

    # Verify the cloned fighter has the correct cost via cost_int()
    cloned_fighter = cloned_list.fighters().first()
    cloned_fighter_cost = cloned_fighter.cost_int()

    assert cloned_fighter_cost == expected_fighter_cost, (
        f"Cloned fighter cost_int() should be {expected_fighter_cost}, got {cloned_fighter_cost}"
    )

    # THE BUG: The cloned list's rating_current should be 80, but due to
    # facts_from_db() clamping at the assignment level (which has -20 cost),
    # the rating is incorrectly stored
    cloned_list.refresh_from_db()
    cloned_rating = cloned_list.rating_current

    assert cloned_rating == expected_list_rating, (
        f"Cloned list rating_current should be {expected_list_rating}, got {cloned_rating}. Negative upgrade cost effect was lost during cloning."
    )


@pytest.mark.django_db
def test_clone_list_with_multiple_negative_cost_items(
    make_list,
    make_list_fighter,
    content_equipment_categories,
):
    """
    Test that multiple pieces of equipment with negative costs are all
    properly reflected in the cloned list's rating.

    Scenario: A fighter has two items with negative costs.

    This test demonstrates that the bug affects lists with multiple
    negative cost items - the cloned list's rating_current is incorrect.
    """
    # Create a list
    list_: List = make_list("Test List with Multiple Negative Cost Items")

    # Create a fighter with base cost 100
    fighter: ListFighter = make_list_fighter(list_, "Fighter with Multiple Discounts")

    # Create first negative cost equipment (-20 credits)
    discount_item_1 = ContentEquipment.objects.create(
        name="Discount Item 1",
        cost="-20",
        category=content_equipment_categories[0],
    )

    # Create second negative cost equipment (-25 credits)
    discount_item_2 = ContentEquipment.objects.create(
        name="Discount Item 2",
        cost="-25",
        category=content_equipment_categories[0],
    )

    # Assign both items to the fighter
    fighter.assign(discount_item_1)
    fighter.assign(discount_item_2)

    # Calculate expected costs
    # Fighter base cost: 100
    # Equipment 1 cost: -20
    # Equipment 2 cost: -25
    # Expected fighter total: 100 + (-20) + (-25) = 55
    # Expected list rating: 55
    expected_fighter_cost = 55
    expected_list_rating = 55

    # Verify fighter cost_int() returns the correct value
    fighter.refresh_from_db()
    assert fighter.cost_int() == expected_fighter_cost, (
        f"Fighter cost_int() should be {expected_fighter_cost}, got {fighter.cost_int()}"
    )

    # Clone the list
    cloned_list: List = list_.clone(name="Cloned List")

    # Verify the cloned fighter has the correct cost via cost_int()
    cloned_fighter = cloned_list.fighters().first()
    cloned_fighter_cost = cloned_fighter.cost_int()

    assert cloned_fighter_cost == expected_fighter_cost, (
        f"Cloned fighter cost_int() should be {expected_fighter_cost}, got {cloned_fighter_cost}"
    )

    # THE BUG: The cloned list's rating_current should be 55, but due to
    # facts_from_db() clamping negative assignment costs to 0, the rating is incorrect
    cloned_list.refresh_from_db()
    cloned_rating = cloned_list.rating_current

    assert cloned_rating == expected_list_rating, (
        f"Cloned list rating_current should be {expected_list_rating}, got {cloned_rating}. Negative cost effects were lost during cloning."
    )
