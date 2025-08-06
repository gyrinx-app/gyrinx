import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
)
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_clone_linked_fighter_with_additional_equipment(
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
    vehicle_lf = vehicle_assignment.linked_fighter
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
    cloned_vehicle = cloned_vehicle_assignment.linked_fighter
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
