import pytest

from gyrinx.content.models import ContentEquipmentFighterProfile
from gyrinx.core.models import ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import EquipmentCategoryChoices, FighterCategoryChoices


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
        base_cost=0,
    )

    beast_ce = make_equipment(
        "Beast", category=EquipmentCategoryChoices.STATUS_ITEMS, cost=50
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
    assert lst.cost_int() == 150
    assert lst.fighters().count() == 2
    assert assign.linked_fighter.name == beast_cf.type

    linked_lf = ListFighter.objects.get(pk=assign.linked_fighter.pk)
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
        "Beast", category=EquipmentCategoryChoices.STATUS_ITEMS, cost=50
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
        "Beast", category=EquipmentCategoryChoices.STATUS_ITEMS, cost=50
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
        "Beast", category=EquipmentCategoryChoices.STATUS_ITEMS, cost=50
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
