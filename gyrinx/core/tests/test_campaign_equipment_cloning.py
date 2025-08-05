import pytest
from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentHouse,
    ContentEquipment,
    ContentFighter,
    ContentEquipmentEquipmentProfile,
    FighterCategoryChoices,
)
from gyrinx.core.models import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    Campaign,
)


@pytest.mark.django_db
def test_vehicle_equipment_with_restrictions_cloned_to_campaign(user):
    """Test that vehicle equipment with category restrictions is properly cloned when starting a campaign."""
    # Create a house
    house = ContentHouse.objects.create(name="Test House")

    # Create a vehicle fighter
    vehicle_fighter = ContentFighter.objects.create(
        type="Test Vehicle",
        house=house,
        category=FighterCategoryChoices.VEHICLE,
        base_cost=100,
    )

    # Create a restricted equipment category for vehicle upgrades
    vehicle_category = ContentEquipmentCategory.objects.create(
        name="Vehicle Upgrades", group="gear"
    )

    # Add fighter category restriction (VEHICLE only)
    ContentEquipmentCategoryFighterRestriction.objects.create(
        equipment_category=vehicle_category,
        fighter_category=FighterCategoryChoices.VEHICLE,
    )

    # Create a vehicle body upgrade (parent equipment)
    vehicle_body = ContentEquipment.objects.create(
        name="Body",
        category=vehicle_category,
        cost="50",
    )

    # Create a linked equipment that the body provides (e.g., armor)
    vehicle_armor = ContentEquipment.objects.create(
        name="Armor",
        category=vehicle_category,
        cost="0",  # Cost comes from parent
    )

    # Create equipment profile linking body to armor
    ContentEquipmentEquipmentProfile.objects.create(
        equipment=vehicle_body,
        linked_equipment=vehicle_armor,
    )

    # Create a list with the vehicle
    list = List.objects.create(
        name="Test Gang",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,
    )

    # Add the vehicle to the list
    list_vehicle = ListFighter.objects.create(
        name="My Vehicle",
        content_fighter=vehicle_fighter,
        list=list,
        owner=user,
    )

    # Assign the body upgrade to the vehicle
    body_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_vehicle,
        content_equipment=vehicle_body,
    )

    # The post_save signal should have created the linked armor assignment
    # Check that the linked equipment was created
    armor_assignments = ListFighterEquipmentAssignment.objects.filter(
        list_fighter=list_vehicle,
        content_equipment=vehicle_armor,
        linked_equipment_parent=body_assignment,
    )
    assert armor_assignments.exists(), "Linked armor equipment should be created"

    # Create a campaign and add the list
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
    )
    campaign.lists.add(list)

    # Start the campaign (this clones the lists)
    campaign.start_campaign()

    # Get the cloned list
    cloned_list = List.objects.get(
        original_list=list,
        campaign=campaign,
    )

    # Get the cloned vehicle
    cloned_vehicle = cloned_list.fighters().get(name="My Vehicle")

    # Check that the body assignment was cloned
    cloned_body_assignments = ListFighterEquipmentAssignment.objects.filter(
        list_fighter=cloned_vehicle,
        content_equipment=vehicle_body,
    )
    assert cloned_body_assignments.exists(), "Body equipment should be cloned"
    cloned_body_assignment = cloned_body_assignments.first()

    # Check that the linked armor assignment was cloned with proper parent reference
    cloned_armor_assignments = ListFighterEquipmentAssignment.objects.filter(
        list_fighter=cloned_vehicle,
        content_equipment=vehicle_armor,
    )
    assert cloned_armor_assignments.exists(), "Linked armor equipment should be cloned"
    cloned_armor_assignment = cloned_armor_assignments.first()

    # This is the critical check - the linked_equipment_parent should be set
    assert cloned_armor_assignment.linked_equipment_parent == cloned_body_assignment, (
        "Cloned armor equipment should maintain parent link to cloned body equipment"
    )

    # Verify the cost is still 0 for linked equipment
    assert cloned_armor_assignment.cost_int() == 0, (
        "Linked equipment should have 0 cost"
    )
