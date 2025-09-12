import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
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
