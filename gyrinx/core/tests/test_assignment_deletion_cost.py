import pytest
from gyrinx.content.models import ContentEquipmentCategory
from gyrinx.core.models.list import ListFighter


@pytest.mark.django_db
def test_assignment_deletion_cost_recalculation(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    """Test that deleting an assignment correctly recalculates the list cost."""
    # Create equipment with a cost
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=50,  # Cost of the equipment
    )
    spoon_profile = make_weapon_profile(spoon)

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Initial cost should be just the fighter's base cost
    initial_fighter_cost = fighter.cost_int()
    initial_list_cost = lst.cost_int()

    # Assign the equipment to the fighter
    assignment = fighter.assign(
        spoon, weapon_profiles=[spoon_profile], weapon_accessories=[]
    )

    # Refresh from DB to get updated costs
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # Cost should now include the equipment
    cost_with_equipment = fighter.cost_int()
    list_cost_with_equipment = lst.cost_int()

    assert cost_with_equipment == initial_fighter_cost + 50
    assert list_cost_with_equipment == initial_list_cost + 50

    # Delete the assignment
    assignment.delete()

    # Refresh from DB to get updated costs
    fighter.refresh_from_db()
    lst.refresh_from_db()

    # Cost should be back to initial
    final_fighter_cost = fighter.cost_int()
    final_list_cost = lst.cost_int()

    assert final_fighter_cost == initial_fighter_cost, (
        f"Fighter cost after deletion ({final_fighter_cost}) != initial cost ({initial_fighter_cost})"
    )
    assert final_list_cost == initial_list_cost, (
        f"List cost after deletion ({final_list_cost}) != initial cost ({initial_list_cost})"
    )


@pytest.mark.django_db
def test_assignment_deletion_cached_cost_recalculation(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    """Test that deleting an assignment correctly recalculates the cached list cost."""
    from gyrinx.core.models.list import List

    # Create equipment with a cost
    spoon = make_equipment(
        "Wooden Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=50,  # Cost of the equipment
    )
    spoon_profile = make_weapon_profile(spoon)

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Initial cached cost
    initial_fighter_cost_cached = fighter.cost_int_cached
    initial_list_cost_cached = lst.cost_int_cached

    # Assign the equipment to the fighter
    assignment = fighter.assign(
        spoon, weapon_profiles=[spoon_profile], weapon_accessories=[]
    )

    # Get fresh instances to bypass cached properties
    fighter = ListFighter.objects.get(pk=fighter.pk)
    lst = List.objects.get(pk=lst.pk)

    # Cached cost should now include the equipment
    cost_with_equipment_cached = fighter.cost_int_cached
    list_cost_with_equipment_cached = lst.cost_int_cached

    assert cost_with_equipment_cached == initial_fighter_cost_cached + 50
    assert list_cost_with_equipment_cached == initial_list_cost_cached + 50

    # Delete the assignment
    assignment.delete()

    # Get fresh instances to bypass cached properties
    fighter = ListFighter.objects.get(pk=fighter.pk)
    lst = List.objects.get(pk=lst.pk)

    # Cached cost should be back to initial
    final_fighter_cost_cached = fighter.cost_int_cached
    final_list_cost_cached = lst.cost_int_cached

    assert final_fighter_cost_cached == initial_fighter_cost_cached, (
        f"Fighter cached cost after deletion ({final_fighter_cost_cached}) != initial cached cost ({initial_fighter_cost_cached})"
    )
    assert final_list_cost_cached == initial_list_cost_cached, (
        f"List cached cost after deletion ({final_list_cost_cached}) != initial cached cost ({initial_list_cost_cached})"
    )


@pytest.mark.django_db
def test_assignment_deletion_with_accessories_cost(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    """Test deletion of assignment with accessories correctly updates cost."""
    from gyrinx.content.models import ContentWeaponAccessory

    # Create equipment and accessory
    weapon = make_equipment(
        "Laser Gun",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=30,
    )
    weapon_profile = make_weapon_profile(weapon)

    scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Telescopic Sight", cost=20
    )

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    initial_cost = lst.cost_int()

    # Assign weapon with accessory (total cost = 30 + 20 = 50)
    assignment = fighter.assign(
        weapon, weapon_profiles=[weapon_profile], weapon_accessories=[scope]
    )

    # Refresh and check cost increased by 50
    lst.refresh_from_db()
    assert lst.cost_int() == initial_cost + 50

    # Delete assignment
    assignment.delete()

    # Refresh and check cost is back to initial
    lst.refresh_from_db()
    assert lst.cost_int() == initial_cost
