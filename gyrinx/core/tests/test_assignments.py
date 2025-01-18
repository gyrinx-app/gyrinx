import pytest

from gyrinx.content.models import (
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
)
from gyrinx.models import EquipmentCategoryChoices


@pytest.mark.django_db
def test_fighter_with_default_spoon_weapon_assignment(
    content_fighter, make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    assert len(fighter.assignments()) == 1
    assert fighter.assignments()[0].content_equipment == spoon
    # Spoon is default and therefore free
    assert fighter.cost_int() == content_fighter.cost_int()


@pytest.mark.django_db
def test_assign_accessory(
    make_list, make_list_fighter, make_equipment, make_weapon_profile
):
    spoon = make_equipment("Spoon")
    spoon_profile = make_weapon_profile(spoon)
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")
    lf_assignment = fighter.assign(
        spoon, weapon_profiles=[spoon_profile], weapon_accessories=[spoon_scope]
    )

    assert lf_assignment.content_equipment == spoon
    assert lf_assignment.weapon_profiles()[0] == spoon_profile
    assert lf_assignment.weapon_accessories()[0] == spoon_scope
    assert lf_assignment.cost_int() == 10

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 10

    assert fighter.cost_int() == 110


@pytest.mark.django_db
def test_fighter_with_default_spoon_scope_assignment(
    content_fighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)
    content_fighter_equip.weapon_accessories_field.add(spoon_scope)

    assert content_fighter_equip.cost_int() == 0

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 0
    # Spoon and scope are default and therefore free
    assert fighter.cost_int() == content_fighter.cost_int()


@pytest.mark.django_db
def test_fighter_with_equipment_list_accessory(
    content_fighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    spoon = make_equipment(
        "Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    spoon_profile = make_weapon_profile(spoon)
    spoon_scope, _ = ContentWeaponAccessory.objects.get_or_create(
        name="Spoon Scope", cost=10
    )

    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")

    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter.content_fighter, weapon_accessory=spoon_scope, cost=5
    )

    # With the scope, the spoon is 10 + 0 + 10 = 20
    # With an equipment list entry for the scope, the price is 10 + 0 + 5 = 15
    lf_assign = fighter.assign(
        spoon, weapon_profiles=[spoon_profile], weapon_accessories=[spoon_scope]
    )

    assert lf_assign.cost_int() == 15

    # Reminder: assignments() returns List[VirtuaListFighterEquipmentAssignment]
    assert len(fighter.assignments()) == 1
    assignment = fighter.assignments()[0]
    assert assignment.content_equipment == spoon
    assert assignment.weapon_profiles()[0] == spoon_profile
    assert assignment.weapon_accessories()[0] == spoon_scope
    assert assignment.cost_int() == 15
    assert fighter.cost_int() == 115
