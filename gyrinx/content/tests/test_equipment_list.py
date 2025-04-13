import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_equipment():
    # Create some equipment, a equipment list, and a fighter and
    # write a query to get the equipment list for the fighter

    # Create some equipment
    equipment = ContentEquipment.objects.create(
        name="Wooden Spoon",
        category_obj=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
    )
    equipment.save()

    # Create a fighter
    fighter = ContentFighter.objects.create(
        type="Charter Master",
        category=FighterCategoryChoices.LEADER,
    )
    fighter.save()

    # Create a equipment list
    fighter_equip = ContentFighterEquipmentListItem(
        fighter=fighter, equipment=equipment
    )
    fighter_equip.save()

    # Query to get the equipment list for the fighter
    fe = ContentFighterEquipmentListItem.objects.get(fighter=fighter)
    assert fe.equipment.name == "Wooden Spoon"
    assert fe.fighter.type == "Charter Master"


@pytest.mark.django_db
def test_equipment_weapon_profile_mismatch():
    # Create some equipment
    equipment1 = ContentEquipment.objects.create(
        name="Wooden Spoon",
        category_obj=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
    )
    equipment1.save()

    equipment2 = ContentEquipment.objects.create(
        name="Fork",
        category_obj=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
    )
    equipment2.save()

    # Create a fighter
    fighter = ContentFighter.objects.create(
        type="Charter Master",
        category=FighterCategoryChoices.LEADER,
    )
    fighter.save()

    # Create a weapon profile for different equipment
    weapon_profile = ContentWeaponProfile.objects.create(
        name="Sword Profile", equipment=equipment2
    )
    weapon_profile.save()

    # Create a equipment list with mismatched weapon profile
    fighter_equip = ContentFighterEquipmentListItem(
        fighter=fighter, equipment=equipment1, weapon_profile=weapon_profile
    )

    with pytest.raises(
        ValidationError, match="Weapon profile must match the equipment selected."
    ):
        fighter_equip.clean()


@pytest.mark.django_db
def test_content_equipment_manager():
    # Create some equipment
    spoon = ContentEquipment.objects.create(
        name="Wooden Spoon",
        category_obj=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost="5",
    )

    fork = ContentEquipment.objects.create(
        name="Fork",
        category_obj=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost="10",
    )

    knife = ContentEquipment.objects.create(
        name="Knife",
        category_obj=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost="15",
    )

    fighter = ContentFighter.objects.create(
        type="Charter Master",
        category=FighterCategoryChoices.LEADER,
    )

    ContentWeaponProfile.objects.create(name="", equipment=spoon)
    ContentWeaponProfile.objects.create(name="", equipment=knife)
    knife_profile_upgraded = ContentWeaponProfile.objects.create(
        name="sharpened", equipment=knife, cost=10
    )

    # Free spoons!
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=spoon, cost=0
    )

    # Cheap sharpening!
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=knife, weapon_profile=knife_profile_upgraded, cost=5
    )

    assert ContentEquipment.objects.get(pk=spoon.pk).has_weapon_profiles
    assert not ContentEquipment.objects.get(pk=fork.pk).has_weapon_profiles
    assert ContentEquipment.objects.get(pk=knife.pk).cost_cast_int == 15

    assert ContentEquipment.objects.weapons().contains(spoon)
    assert ContentEquipment.objects.weapons().contains(knife)
    assert ContentEquipment.objects.non_weapons().contains(fork)

    assert (
        ContentEquipment.objects.with_cost_for_fighter(fighter)
        .get(pk=spoon.pk)
        .cost_for_fighter_int()
        == 0
    )
    assert (
        ContentWeaponProfile.objects.with_cost_for_fighter(fighter)
        .get(pk=knife_profile_upgraded.pk)
        .cost_for_fighter_int()
        == 5
    )


@pytest.mark.django_db
def test_equipment_list_weapon_accessory():
    spoon_sight = ContentWeaponAccessory.objects.create(name="Spoon Sight", cost=10)

    fighter = ContentFighter.objects.create(
        type="Charter Master",
        category=FighterCategoryChoices.LEADER,
    )

    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter, weapon_accessory=spoon_sight, cost=5
    )

    assert (
        ContentWeaponAccessory.objects.with_cost_for_fighter(fighter)
        .get(pk=spoon_sight.pk)
        .cost_for_fighter_int()
        == 5
    )


@pytest.mark.django_db
def test_copy_to_house(
    content_fighter,
    make_content_house,
    make_equipment,
    make_weapon_profile,
    make_weapon_accessory,
):
    spoon = make_equipment("Wooden Spoon", cost=10)
    spoon_spike = make_weapon_profile(spoon, name="Spoon Spike", cost=5)
    spoon_sight = make_weapon_accessory("Spoon Sight", cost=5)
    fork = make_equipment("Fork", cost=15)
    fork_double_prong = make_weapon_profile(fork, name="Double Prong", cost=10)
    fork_sight = make_weapon_accessory("Fork Sight", cost=10)

    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=spoon, cost=0
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=content_fighter, equipment=spoon, weapon_profile=spoon_spike, cost=0
    )
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=content_fighter, weapon_accessory=spoon_sight, cost=0
    )
    fork_assign = ContentFighterDefaultAssignment.objects.create(
        fighter=content_fighter, equipment=fork
    )
    fork_assign.weapon_profiles_field.add(fork_double_prong)
    fork_assign.weapon_accessories_field.add(fork_sight)

    fork_assign.save()

    spoon_house = make_content_house("House of Spoons")

    new_content_fighter = content_fighter.copy_to_house(spoon_house)

    assert new_content_fighter.house == spoon_house
    assert ContentFighterEquipmentListItem.objects.filter(
        fighter=new_content_fighter, equipment=spoon, cost=0
    ).exists()
    assert ContentFighterEquipmentListItem.objects.filter(
        fighter=new_content_fighter, equipment=spoon, weapon_profile=spoon_spike, cost=0
    ).exists()
    assert ContentFighterEquipmentListWeaponAccessory.objects.filter(
        fighter=new_content_fighter, weapon_accessory=spoon_sight, cost=0
    ).exists()
    new_fork_assign = ContentFighterDefaultAssignment.objects.get(
        fighter=new_content_fighter, equipment=fork
    )
    assert fork_double_prong in new_fork_assign.weapon_profiles_field.all()
    assert fork_sight in new_fork_assign.weapon_accessories_field.all()
