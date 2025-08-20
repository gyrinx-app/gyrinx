import pytest
from gyrinx.content.models import ContentEquipmentCategory
from gyrinx.core.models.list import ListFighter


@pytest.mark.django_db
def test_assignment_deletion_cost_recalculation(
    content_fighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
    content_equipment_categories,
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
@pytest.mark.with_cost_cache
def test_assignment_deletion_cached_cost_recalculation(
    content_fighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
    content_equipment_categories,
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


@pytest.mark.django_db
def test_assignment_deletion_immediate_cached_property_update(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    """Test that cached properties are updated immediately after deletion without refetch_from_db."""
    # Create equipment with a cost
    weapon = make_equipment(
        "Test Weapon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=100,
    )
    weapon_profile = make_weapon_profile(weapon)

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Get initial costs using cached properties
    initial_fighter_cost_cached = fighter.cost_int_cached
    initial_list_cost_cached = lst.cost_int_cached

    # Assign the equipment
    assignment = fighter.assign(
        weapon, weapon_profiles=[weapon_profile], weapon_accessories=[]
    )

    # IMPORTANT: Access the cached properties to populate them in memory
    # This simulates the real-world scenario where these might have been accessed
    _ = fighter.cost_int_cached
    _ = lst.cost_int_cached

    # Delete the assignment
    assignment.delete()

    # Now check that the cached properties return the correct value WITHOUT refetch_from_db
    # This tests that the in-memory cached properties are properly invalidated
    assert fighter.cost_int_cached == initial_fighter_cost_cached, (
        f"Fighter cached cost immediately after deletion ({fighter.cost_int_cached}) "
        f"!= initial cost ({initial_fighter_cost_cached})"
    )
    assert lst.cost_int_cached == initial_list_cost_cached, (
        f"List cached cost immediately after deletion ({lst.cost_int_cached}) "
        f"!= initial cost ({initial_list_cost_cached})"
    )


@pytest.mark.django_db
@pytest.mark.with_cost_cache
def test_assignment_deletion_cached_property_with_multiple_assignments(
    content_fighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
    content_equipment_categories,
):
    """Test cached property updates when deleting one of multiple assignments."""
    # Create multiple equipment items
    weapon1 = make_equipment(
        "Weapon 1",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=50,
    )
    weapon1_profile = make_weapon_profile(weapon1)

    weapon2 = make_equipment(
        "Weapon 2",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=75,
    )
    weapon2_profile = make_weapon_profile(weapon2)

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    initial_cost = lst.cost_int_cached

    # Assign both weapons
    assignment1 = fighter.assign(
        weapon1, weapon_profiles=[weapon1_profile], weapon_accessories=[]
    )
    # We need assignment2 to ensure the cost properly reflects remaining equipment after deletion
    assignment2 = fighter.assign(  # noqa: F841
        weapon2, weapon_profiles=[weapon2_profile], weapon_accessories=[]
    )

    # Access cached properties to populate them
    _ = fighter.cost_int_cached
    _ = lst.cost_int_cached

    # Delete first assignment
    assignment1.delete()

    # Check that cached cost now reflects only the second weapon
    expected_cost = initial_cost + 75  # Only weapon2's cost remains
    assert lst.cost_int_cached == expected_cost, (
        f"List cached cost after deleting first assignment ({lst.cost_int_cached}) "
        f"!= expected cost ({expected_cost})"
    )
