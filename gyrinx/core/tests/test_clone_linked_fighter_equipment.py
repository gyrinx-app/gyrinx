import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
)
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_clone_child_fighter_with_additional_equipment(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """
    Test that when cloning a list, equipment assigned to linked fighters
    (like vehicles or exotic beasts) is also cloned.

    This test verifies the scenario where:
    1. Fighter A has equipment that generates another fighter (B)
    2. Fighter B is given additional equipment
    3. When the list is cloned, the cloned Fighter B should have the equipment
    """
    # Setup
    house = make_content_house("Test House")

    # Create the main fighter (e.g., a gang member)
    gang_member_cf = make_content_fighter(
        type="Gang Member",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create a vehicle fighter that will be auto-generated
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=200,  # This cost is ignored when linked
    )

    # Create equipment that generates the vehicle fighter
    vehicle_equipment = make_equipment(
        "Vehicle Key",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=150,
    )

    # Link the vehicle fighter to the equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_cf,
    )

    # Create some additional equipment for the vehicle
    vehicle_armor = make_equipment(
        "Vehicle Armor",
        category=ContentEquipmentCategory.objects.get(name="Armor"),
        cost=50,
    )

    # Create the list and add the gang member
    original_list = make_list("Original List", content_house=house, owner=user)
    gang_member_lf = make_list_fighter(
        original_list, "Gang Member", content_fighter=gang_member_cf, owner=user
    )

    # Assign the vehicle equipment to the gang member
    # This will auto-create the vehicle fighter
    vehicle_assignment = ListFighterEquipmentAssignment(
        list_fighter=gang_member_lf,
        content_equipment=vehicle_equipment,
    )
    vehicle_assignment.save()

    # Verify the vehicle was created
    assert original_list.fighters().count() == 2
    vehicle_lf = vehicle_assignment.child_fighter
    assert vehicle_lf is not None
    assert vehicle_lf.name == "Vehicle"

    # Now add equipment to the vehicle itself
    armor_assignment = ListFighterEquipmentAssignment(
        list_fighter=vehicle_lf,
        content_equipment=vehicle_armor,
    )
    armor_assignment.save()

    # Verify the vehicle has the armor
    vehicle_equipment_count = vehicle_lf.equipment.all().count()
    assert vehicle_equipment_count == 1
    assert vehicle_lf.equipment.all().first().name == "Vehicle Armor"

    # Clone the list
    cloned_list = original_list.clone(name="Cloned List")

    # Verify the clone has the same number of fighters
    assert cloned_list.fighters().count() == 2

    # Find the cloned gang member and vehicle
    cloned_gang_member = (
        cloned_list.fighters().filter(content_fighter=gang_member_cf).first()
    )
    assert cloned_gang_member is not None

    # Find the cloned vehicle through the assignment
    cloned_vehicle_assignment = (
        cloned_gang_member._direct_assignments()
        .filter(content_equipment=vehicle_equipment)
        .first()
    )
    assert cloned_vehicle_assignment is not None
    cloned_vehicle = cloned_vehicle_assignment.child_fighter
    assert cloned_vehicle is not None

    # THIS IS THE KEY TEST: The cloned vehicle should have the armor equipment
    # This currently fails because the cloning process doesn't copy equipment
    # assigned to linked fighters
    cloned_vehicle_equipment = cloned_vehicle.equipment.all()
    assert cloned_vehicle_equipment.count() == 1, (
        f"Expected cloned vehicle to have 1 equipment item, "
        f"but found {cloned_vehicle_equipment.count()}"
    )
    assert cloned_vehicle_equipment.first().name == "Vehicle Armor", (
        "Expected cloned vehicle to have 'Vehicle Armor' equipment"
    )


@pytest.mark.django_db
def test_clone_child_fighter_equipment_rating_propagation(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    """
    Test that when cloning a list, the cloned vehicle's rating_current
    correctly includes its equipment costs.

    This is a regression test for #1215 where vehicle equipment costs
    were not reflected in rating_current after campaign start (which clones lists).
    """
    # Setup
    house = make_content_house("Test House")

    # Create the crew fighter
    crew_cf = make_content_fighter(
        type="Crew",
        category=FighterCategoryChoices.CREW,
        house=house,
        base_cost=50,
    )

    # Create a vehicle fighter that will be auto-generated
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=0,  # Vehicles typically have 0 base cost (cost is in the linking equipment)
    )

    # Create equipment that links crew to vehicle
    vehicle_link_equipment = make_equipment(
        "Vehicle Link",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=100,  # Cost of getting the vehicle
    )

    # Link the vehicle fighter to the equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_link_equipment,
        content_fighter=vehicle_cf,
    )

    # Create a weapon for the vehicle with a cost
    vehicle_weapon = make_equipment(
        "Vehicle Weapon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=75,
    )
    weapon_profile = make_weapon_profile(vehicle_weapon)

    # Create the list and add the crew fighter
    original_list = make_list("Original List", content_house=house, owner=user)
    crew_lf = make_list_fighter(
        original_list, "Crew Member", content_fighter=crew_cf, owner=user
    )

    # Assign the vehicle link equipment to the crew
    # This will auto-create the vehicle fighter
    vehicle_assignment = ListFighterEquipmentAssignment(
        list_fighter=crew_lf,
        content_equipment=vehicle_link_equipment,
    )
    vehicle_assignment.save()

    # Get the vehicle fighter
    vehicle_lf = vehicle_assignment.child_fighter
    assert vehicle_lf is not None

    # Add weapon to the vehicle
    weapon_assignment = ListFighterEquipmentAssignment(
        list_fighter=vehicle_lf,
        content_equipment=vehicle_weapon,
    )
    weapon_assignment.save()
    weapon_assignment.weapon_profiles_field.add(weapon_profile)

    # Verify original vehicle rating includes the weapon cost
    vehicle_lf.refresh_from_db()
    original_vehicle_cost = vehicle_lf.cost_int()
    assert original_vehicle_cost == 75, (
        f"Original vehicle cost should be 75 (weapon), got {original_vehicle_cost}"
    )

    # Update the original list's facts before cloning
    original_list.facts_from_db(update=True)

    # Clone the list (this is what happens during campaign start)
    cloned_list = original_list.clone(name="Cloned List")

    # Find the cloned vehicle
    cloned_crew = cloned_list.fighters().filter(content_fighter=crew_cf).first()
    cloned_vehicle_assignment = (
        cloned_crew._direct_assignments()
        .filter(content_equipment=vehicle_link_equipment)
        .first()
    )
    cloned_vehicle = cloned_vehicle_assignment.child_fighter
    assert cloned_vehicle is not None

    # Verify the cloned vehicle has the weapon
    cloned_vehicle_equipment = cloned_vehicle.equipment.all()
    assert cloned_vehicle_equipment.count() == 1, (
        f"Expected cloned vehicle to have 1 equipment item, "
        f"but found {cloned_vehicle_equipment.count()}"
    )

    # THE KEY TEST: The cloned vehicle's rating_current should include the weapon cost
    cloned_vehicle.refresh_from_db()
    cloned_vehicle_rating = cloned_vehicle.rating_current
    cloned_vehicle_cost = cloned_vehicle.cost_int()

    assert cloned_vehicle_rating == 75, (
        f"Cloned vehicle rating_current should be 75 (weapon cost), "
        f"but got {cloned_vehicle_rating}. "
        f"cost_int() returns {cloned_vehicle_cost}"
    )

    # Also verify the list's total rating reflects this
    cloned_list.refresh_from_db()
    # List rating should include: crew (50) + vehicle link (100) + vehicle weapon (75) = 225
    # But vehicle is a child fighter so it's counted separately
    # The crew cost includes the vehicle link equipment
    # The vehicle cost includes its weapon
    expected_list_rating = (
        crew_cf.base_cost + 100 + 75
    )  # crew + vehicle link + vehicle weapon
    assert cloned_list.rating_current == expected_list_rating, (
        f"Cloned list rating_current should be {expected_list_rating}, "
        f"but got {cloned_list.rating_current}"
    )
