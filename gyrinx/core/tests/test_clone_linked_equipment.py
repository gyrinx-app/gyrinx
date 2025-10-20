import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
)
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_clone_list_with_child_fighter(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """Test that cloning a list with equipment that has linked fighters works correctly."""
    # Create house and fighters
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
        base_cost=20,  # This should be ignored when linked
    )

    # Create equipment that creates a linked fighter
    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    # Create list and owner fighter
    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)

    # Assign the beast equipment to the owner
    assign = ListFighterEquipmentAssignment(
        list_fighter=owner_lf, content_equipment=beast_ce
    )
    assign.save()

    # Verify setup
    assert lst.fighters().count() == 2
    assert assign.child_fighter is not None
    assert assign.child_fighter.name == "Beast"
    assert lst.cost_int() == 150  # 100 + 50, beast fighter cost ignored

    # Clone the list
    cloned_list = lst.clone(name="Cloned List")

    # Verify clone results
    assert cloned_list.fighters().count() == 2
    cloned_fighters = list(cloned_list.fighters())

    # Find the owner and beast fighters in the clone
    cloned_owner = next(f for f in cloned_fighters if f.name == "Owner")
    cloned_beast = next(f for f in cloned_fighters if f.name == "Beast")

    # Verify the equipment assignment was cloned correctly
    cloned_assignments = cloned_owner._direct_assignments()
    assert cloned_assignments.count() == 1
    cloned_assign = cloned_assignments.first()

    # This is the key test - the cloned assignment should have a child_fighter
    assert cloned_assign.child_fighter is not None
    assert cloned_assign.child_fighter == cloned_beast
    assert cloned_assign.child_fighter.name == "Beast"

    # Verify cost is correct
    assert cloned_list.cost_int() == 150


@pytest.mark.django_db
def test_clone_fighter_with_linked_equipment(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """Test that cloning a single fighter with linked equipment works correctly."""
    # Create house and fighter
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
        base_cost=20,
    )

    # Create equipment that creates a linked fighter
    beast_ce = make_equipment(
        "Beast",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Link the Beast Content Fighter to the Equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_ce, content_fighter=beast_cf
    )

    # Create list and owner fighter
    lst = make_list("Example List", content_house=house, owner=user)
    owner_lf = make_list_fighter(lst, "Owner", content_fighter=owner_cf, owner=user)

    # Assign the beast equipment to the owner
    assign = ListFighterEquipmentAssignment(
        list_fighter=owner_lf, content_equipment=beast_ce
    )
    assign.save()

    # Verify setup
    assert lst.fighters().count() == 2
    assert assign.child_fighter is not None

    # Clone just the fighter
    cloned_owner = owner_lf.clone(name="Cloned Owner")

    # The clone should also have created a linked fighter
    assert lst.fighters().count() == 4  # Original 2 + cloned 2

    # Check the cloned assignment
    cloned_assignments = cloned_owner._direct_assignments()
    assert cloned_assignments.count() == 1
    cloned_assign = cloned_assignments.first()

    # The cloned assignment should have its own linked fighter
    assert cloned_assign.child_fighter is not None
    assert cloned_assign.child_fighter != assign.child_fighter  # Different instances
    assert cloned_assign.child_fighter.name == "Beast"
    assert cloned_assign.child_fighter.list == lst


@pytest.mark.django_db
def test_clone_fighter_with_equipment_equipment_link(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """Test that cloning a fighter with equipment-equipment links doesn't duplicate equipment."""
    # Create house and fighter
    house = make_content_house("Example House")
    leader_cf = make_content_fighter(
        type="Leader",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=100,
    )

    # Create parent equipment (e.g., Dustback helamite (NTP))
    parent_equipment = make_equipment(
        "Dustback helamite (NTP)",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=50,
    )

    # Create linked equipment (e.g., Helamite claws)
    linked_equipment = make_equipment(
        "Helamite claws",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=0,  # Auto-assigned equipment is typically free
    )

    # Link the equipment
    ContentEquipmentEquipmentProfile.objects.create(
        equipment=parent_equipment,
        linked_equipment=linked_equipment,
    )

    # Create list and fighter
    lst = make_list("Example List", content_house=house, owner=user)
    leader_lf = make_list_fighter(lst, "Leader", content_fighter=leader_cf, owner=user)

    # Assign the parent equipment to the leader
    parent_assign = ListFighterEquipmentAssignment(
        list_fighter=leader_lf, content_equipment=parent_equipment
    )
    parent_assign.save()

    # Verify setup: should have 1 fighter with 2 equipment assignments (parent + linked)
    assert lst.fighters().count() == 1
    all_assignments = leader_lf._direct_assignments()
    assert all_assignments.count() == 2

    # Find the parent and linked assignments
    parent_assignment = all_assignments.get(content_equipment=parent_equipment)
    linked_assignment = all_assignments.get(content_equipment=linked_equipment)
    assert linked_assignment.linked_equipment_parent == parent_assignment

    # Clone the fighter
    cloned_leader = leader_lf.clone(name="Cloned Leader")

    # Verify clone results: should have 2 fighters total
    assert lst.fighters().count() == 2

    # Check the cloned fighter's assignments
    cloned_assignments = cloned_leader._direct_assignments()
    # BUG: This should be 2, but due to the bug it will be 4
    # (parent + linked from clone method, then another parent + linked from signal)
    assert cloned_assignments.count() == 2, (
        f"Expected 2 equipment assignments for cloned fighter, "
        f"got {cloned_assignments.count()}. "
        f"Assignments: {list(cloned_assignments.values_list('content_equipment__name', flat=True))}"
    )

    # Verify the cloned assignments are correct
    cloned_parent_assignment = cloned_assignments.get(
        content_equipment=parent_equipment
    )
    cloned_linked_assignment = cloned_assignments.get(
        content_equipment=linked_equipment
    )
    assert cloned_linked_assignment.linked_equipment_parent == cloned_parent_assignment
