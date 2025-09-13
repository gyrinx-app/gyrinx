import pytest
from django.forms import ValidationError

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
)
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_basic_fighter_link(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    beast_cf = make_content_fighter(
        type="Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        # Note: The fighter base cost is 20, and the equipment also has a cost.
        #       The fighter base cost should be ignored when linked: it's the equipment
        #       that matters.
        base_cost=20,
    )

    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)

    # Assign this equipment to the owner
    assign = ListFighterEquipmentAssignment(
        list_fighter=owner_lf, content_equipment=beast_ce
    )

    # This needs to be affirmatively saved so that related objects are created
    assign.save()

    assert assign.cost_int() == 50
    # i.e. the cost of the fighter plus equipment only
    assert lst.cost_int() == 150
    assert lst.fighters().count() == 2
    assert assign.child_fighter.name == beast_cf.type

    linked_lf = ListFighter.objects.get(pk=assign.child_fighter.pk)
    assert linked_lf._is_linked

    assign.delete()

    assert lst.cost_int() == 100
    assert lst.fighters().count() == 1


@pytest.mark.django_db
def test_list_ordering_with_link(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    another_cf = make_content_fighter(
        type="Juve",
        category=FighterCategoryChoices.JUVE,
        house=house,
        base_cost=50,
    )
    beast_cf = make_content_fighter(
        type="Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        base_cost=0,
    )

    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)
    make_list_fighter(lst, "Another", content_fighter=another_cf, owner=user)

    # Assign this equipment to the owner
    assign = ListFighterEquipmentAssignment(
        list_fighter=owner_lf, content_equipment=beast_ce
    )

    # This needs to be affirmatively saved so that related objects are created
    assign.save()

    assert lst.cost_int() == 200
    assert lst.fighters().count() == 3

    assert [f.name for f in lst.fighters()] == [
        "Owner",
        "Beast",
        "Another",
    ]


@pytest.mark.django_db
def test_comprehensive_sorting_with_vehicles_and_beasts(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """Test all sorting scenarios for fighters linked to vehicles and beasts."""
    house = make_content_house("Example House")

    # Create content fighters
    fighter_cf = make_content_fighter(
        type="Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=200,
    )
    beast_cf = make_content_fighter(
        type="Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        base_cost=50,
    )

    # Create equipment
    vehicle_ce = make_equipment(
        "Vehicle Equipment",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=200,
    )
    beast_ce = make_equipment(
        "Beast Equipment",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link equipment to content fighters
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_ce, content_fighter=vehicle_cf
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    lst = make_list("Example List", content_house=house, owner=user)

    # Scenario 1: Fighter linked to Beast should sort: Fighter, Beast
    fighter1_lf = make_list_fighter(
        lst, "Fighter1", content_fighter=fighter_cf, owner=user
    )
    assign1 = ListFighterEquipmentAssignment(
        list_fighter=fighter1_lf, content_equipment=beast_ce
    )
    assign1.save()

    # Scenario 2: Fighter linked to Vehicle should sort: Vehicle, Fighter
    fighter2_lf = make_list_fighter(
        lst, "Fighter2", content_fighter=fighter_cf, owner=user
    )
    assign2 = ListFighterEquipmentAssignment(
        list_fighter=fighter2_lf, content_equipment=vehicle_ce
    )
    assign2.save()

    # The vehicle is created automatically when we assign vehicle equipment

    # Scenario 3: Fighter linked to Vehicle, where Fighter is also linked to Beast
    # should sort: Vehicle, Fighter, Fighter's Beast
    fighter3_lf = make_list_fighter(
        lst, "Fighter3", content_fighter=fighter_cf, owner=user
    )
    assign3_vehicle = ListFighterEquipmentAssignment(
        list_fighter=fighter3_lf, content_equipment=vehicle_ce
    )
    assign3_vehicle.save()
    assign3_beast = ListFighterEquipmentAssignment(
        list_fighter=fighter3_lf, content_equipment=beast_ce
    )
    assign3_beast.save()

    # Scenario 4: Fighter linked to Vehicle, where Vehicle is also linked to Beast
    # should sort: Vehicle, Fighter, Vehicle's Beast
    fighter4_lf = make_list_fighter(
        lst, "Fighter4", content_fighter=fighter_cf, owner=user
    )
    assign4 = ListFighterEquipmentAssignment(
        list_fighter=fighter4_lf, content_equipment=vehicle_ce
    )
    assign4.save()

    # Get the vehicle for fighter4
    vehicle4_lf = ListFighter.objects.get(
        list=lst,
        content_fighter__category=FighterCategoryChoices.VEHICLE,
        source_assignment__list_fighter=fighter4_lf,
    )

    # Add beast to the vehicle
    assign_vehicle_beast = ListFighterEquipmentAssignment(
        list_fighter=vehicle4_lf, content_equipment=beast_ce
    )
    assign_vehicle_beast.save()

    # Update names to be unique for better debugging
    beast1 = ListFighter.objects.get(
        list=lst,
        content_fighter__category=FighterCategoryChoices.EXOTIC_BEAST,
        source_assignment__list_fighter=fighter1_lf,
    )
    beast1.name = "Beast1"
    beast1.save()

    vehicle2 = ListFighter.objects.get(
        list=lst,
        content_fighter__category=FighterCategoryChoices.VEHICLE,
        source_assignment__list_fighter=fighter2_lf,
    )
    vehicle2.name = "Vehicle2"
    vehicle2.save()

    vehicle3 = ListFighter.objects.get(
        list=lst,
        content_fighter__category=FighterCategoryChoices.VEHICLE,
        source_assignment__list_fighter=fighter3_lf,
    )
    vehicle3.name = "Vehicle3"
    vehicle3.save()

    beast3 = ListFighter.objects.get(
        list=lst,
        content_fighter__category=FighterCategoryChoices.EXOTIC_BEAST,
        source_assignment__list_fighter=fighter3_lf,
    )
    beast3.name = "Beast3"
    beast3.save()

    vehicle4_lf.name = "Vehicle4"
    vehicle4_lf.save()

    beast4 = ListFighter.objects.get(
        list=lst,
        content_fighter__category=FighterCategoryChoices.EXOTIC_BEAST,
        source_assignment__list_fighter=vehicle4_lf,
    )
    beast4.name = "Beast4"
    beast4.save()

    # Check the sorting
    fighters = lst.fighters()
    fighter_names = [f.name for f in fighters]

    expected_order = [
        # Scenario 1: Fighter, Beast
        "Fighter1",
        "Beast1",  # Fighter1's Beast
        # Scenario 2: Vehicle, Fighter
        "Vehicle2",  # Fighter2's Vehicle
        "Fighter2",
        # Scenario 3: Vehicle, Fighter, Fighter's Beast
        "Vehicle3",  # Fighter3's Vehicle
        "Fighter3",
        "Beast3",  # Fighter3's Beast
        # Scenario 4: Vehicle, Fighter, Vehicle's Beast
        "Vehicle4",  # Fighter4's Vehicle
        "Fighter4",
        "Beast4",  # Vehicle4's Beast
    ]

    # Print for debugging
    print(f"Actual order: {fighter_names}")
    print(f"Expected order: {expected_order}")

    assert fighter_names == expected_order


@pytest.mark.django_db
def test_fighter_link_archive(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    beast_cf = make_content_fighter(
        type="Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        base_cost=0,
    )

    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)

    # Assign this equipment to the owner
    assign = ListFighterEquipmentAssignment(
        list_fighter=owner_lf, content_equipment=beast_ce
    )

    # This needs to be affirmatively saved so that related objects are created
    assign.save()

    assert lst.fighters().count() == 2

    owner_lf.archive()

    assert lst.fighters().count() == 0

    owner_lf.unarchive()

    assert lst.fighters().count() == 2


@pytest.mark.django_db
def test_fighter_link_default_assignment(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    beast_cf = make_content_fighter(
        type="Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        base_cost=0,
    )

    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    # Assign the equipment to the fighter by default
    default_assign = owner_cf.default_assignments.create(equipment=beast_ce)

    lst = make_list("Example List", content_house=house, owner=user)

    # List Fighter creation triggers the default assignment to be disabled, and the linked
    # fighter to be created.
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)

    assert lst.fighters().count() == 2
    # The cost for the equipment should be 0
    assert lst.cost_int() == 100

    # Check that further saves etc don't mess things up
    owner_lf.name = "Owner Renamed"
    owner_lf.save()

    assert lst.fighters().count() == 2

    # Unassign the equipment -> delete the linked fighter
    owner_lf._direct_assignments().delete()
    owner_lf.save()

    assert lst.fighters().count() == 1

    # Once unassigned and un-disabled, the linked fighter should be recreated
    owner_lf.toggle_default_assignment(default_assign, enable=True)

    assert lst.fighters().count() == 2


@pytest.mark.django_db
def test_fighter_link_default_assignment_duplicated(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    beast_cf = make_content_fighter(
        type="Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        base_cost=0,
    )

    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    # Assign the equipment to the fighter by default twice
    default_assign = owner_cf.default_assignments.create(equipment=beast_ce)
    default_assign_2 = owner_cf.default_assignments.create(equipment=beast_ce)

    lst = make_list("Example List", content_house=house, owner=user)

    # List Fighter creation triggers the default assignment to be disabled, and the linked
    # fighter to be created.
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)

    assert lst.fighters().count() == 3
    # The cost for the equipment should be 0
    assert lst.cost_int() == 100

    # Check that further saves etc don't mess things up
    owner_lf.name = "Owner Renamed"
    owner_lf.save()

    assert lst.fighters().count() == 3

    # Unassign the equipment -> delete the linked fighter
    owner_lf._direct_assignments().delete()
    owner_lf.save()

    assert lst.fighters().count() == 1

    # Once unassigned and un-disabled, the linked fighter should be recreated
    owner_lf.toggle_default_assignment(default_assign, enable=True)
    owner_lf.toggle_default_assignment(default_assign_2, enable=True)

    assert lst.fighters().count() == 3


@pytest.mark.django_db
def test_fighter_link_default_assignment_self_fails(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )

    # Obviously can't assign a fighter to itself, but let's make that happen
    owner_ce = make_equipment(
        "Owner",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    ContentEquipmentFighterProfile.objects.create(
        equipment=owner_ce, content_fighter=owner_cf
    )

    # Assign the equipment to the fighter by default
    owner_cf.default_assignments.create(equipment=owner_ce)

    lst = make_list("Example List", content_house=house, owner=user)

    # This needs to error becuase otherwise... infinite loop
    with pytest.raises(ValueError):
        make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)


@pytest.mark.django_db
def test_basic_equipment_link(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    magic_lamp = make_equipment(
        "Magic Lamp",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    genie = make_equipment(
        "Genie",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the second equipment to the first
    ContentEquipmentEquipmentProfile.objects.create(
        equipment=magic_lamp, linked_equipment=genie
    )

    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf: ListFighter = make_list_fighter(
        lst, "Owner", content_fighter=owner_cf, owner=user
    )

    # Assign this equipment to the owner
    assign = owner_lf.assign(magic_lamp)

    # Ca-ching
    owner_lf = ListFighter.objects.get(pk=owner_lf.pk)

    assert assign.cost_int() == 50
    # i.e. the cost of the fighter plus equipment only
    assert lst.cost_int() == 150
    assert lst.fighters().count() == 1
    assignments = owner_lf.assignments()
    assert len(assignments) == 2

    assign.delete()
    owner_lf = ListFighter.objects.get(pk=owner_lf.pk)
    lst = List.objects.get(pk=lst.pk)

    assignments = owner_lf.assignments()
    assert len(assignments) == 0
    assert lst.cost_int() == 100
    assert lst.fighters().count() == 1


@pytest.mark.django_db
def test_equipment_self_link(
    make_equipment,
):
    magic_lamp = make_equipment(
        "Magic Lamp",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # No bueno
    with pytest.raises(ValidationError):
        ContentEquipmentEquipmentProfile.objects.create(
            equipment=magic_lamp, linked_equipment=magic_lamp
        ).full_clean()


@pytest.mark.django_db
def test_default_equipment_link(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    house = make_content_house("Example House")
    owner_cf = make_content_fighter(
        type="Owner",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )
    magic_lamp = make_equipment(
        "Magic Lamp",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    genie = make_equipment(
        "Genie",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the second equipment to the first
    ContentEquipmentEquipmentProfile.objects.create(
        equipment=magic_lamp, linked_equipment=genie
    )

    # Assign the equipment to the fighter by default
    owner_cf.default_assignments.create(equipment=magic_lamp)

    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf: ListFighter = make_list_fighter(
        lst, "Owner", content_fighter=owner_cf, owner=user
    )

    # i.e. the cost of the fighter plus equipment only — which is
    # zero due to the default assignment
    assert lst.cost_int() == 100
    assignments = owner_lf.assignments()
    assert len(assignments) == 2

    # Delete the assignment -> delete the linked assignment
    owner_lf._direct_assignments().delete()
    owner_lf.save()

    owner_lf = ListFighter.objects.get(pk=owner_lf.pk)
    lst = List.objects.get(pk=lst.pk)

    assignments = owner_lf.assignments()
    assert len(assignments) == 0
    assert lst.cost_int() == 100
