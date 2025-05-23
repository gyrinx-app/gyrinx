import pytest

from gyrinx.content.models import ContentEquipmentUpgrade
from gyrinx.core.models.list import (
    List,
    ListFighter,
    VirtualListFighterEquipmentAssignment,
)


@pytest.mark.django_db
def test_basic_list_clone(make_list, make_list_fighter, make_equipment):
    list_: List = make_list("Test List", narrative="This is a test list.")
    fighter: ListFighter = make_list_fighter(list_, "Test Fighter")
    spoon = make_equipment("Spoon")
    fighter.assign(spoon)

    list_clone: List = list_.clone(
        name="Test List (Clone)",
    )

    assert list_clone.name == "Test List (Clone)"
    assert list_clone.owner == list_.owner
    assert list_clone.content_house == list_.content_house
    assert list_clone.public == list_.public
    assert list_clone.narrative == "This is a test list."
    assert list_clone.fighters().count() == 1

    fighter_clone = list_clone.fighters().first()

    assert fighter_clone.name == "Test Fighter"
    assert fighter_clone.content_fighter == fighter.content_fighter
    assert fighter_clone.owner == fighter.owner
    assert fighter_clone.archived == fighter.archived

    assert fighter_clone.equipment.all().count() == 1
    assert fighter_clone.equipment.all().first().name == "Spoon"


@pytest.mark.django_db
def test_list_clone_with_mods(make_list, make_user):
    list_ = make_list("Test List")
    new_owner = make_user("new_owner", "password")

    list_clone: List = list_.clone(
        name="Test List (Clone)",
        owner=new_owner,
        public=False,
    )

    assert list_clone.public is False
    assert list_clone.owner == new_owner


@pytest.mark.django_db
def test_fighter_clone_with_mods(
    make_list,
    make_list_fighter,
    make_equipment,
    make_content_fighter,
    make_weapon_profile,
    make_weapon_accessory,
):
    list_ = make_list("Test List")
    fighter: ListFighter = make_list_fighter(list_, "Test Fighter")
    spoon = make_equipment("Spoon")
    spoon_spike = make_weapon_profile(spoon, name="Spoon Spike", cost=5)
    spoon_sight = make_weapon_accessory("Spoon Sight", cost=5)
    ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Alpha", cost=20, position=0
    )
    u2 = ContentEquipmentUpgrade.objects.create(
        equipment=spoon, name="Beta", cost=30, position=1
    )
    assign = fighter.assign(
        spoon, weapon_profiles=[spoon_spike], weapon_accessories=[spoon_sight]
    )
    assign.upgrades_field.add(u2)
    assign.save()

    new_fighter = fighter.clone(
        name="Test Fighter (Clone)",
        narrative="This is a clone.",
    )

    assert new_fighter.name == "Test Fighter (Clone)"
    assert new_fighter.owner == fighter.owner
    assert new_fighter.archived == fighter.archived
    assert new_fighter.narrative == "This is a clone."
    assert new_fighter.equipment.all().count() == 1

    cloned_assign: VirtualListFighterEquipmentAssignment = new_fighter.assignments()[0]
    assert "Spoon" in cloned_assign.name()
    weapon_profiles = cloned_assign.weapon_profiles()
    assert len(weapon_profiles) == 1
    assert weapon_profiles[0].name == "Spoon Spike"
    accessories = cloned_assign.weapon_accessories()
    assert len(accessories) == 1
    assert accessories[0].name == "Spoon Sight"
    assert cloned_assign.active_upgrades().count() == 1
    assert cloned_assign.active_upgrades().first().name == "Beta"

    assert cloned_assign.cost_int() == 60  # 5 + 5 + 20 + 30
