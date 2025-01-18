import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListWeaponAccessory,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.models import EquipmentCategoryChoices, FighterCategoryChoices


@pytest.mark.django_db
def test_equipment():
    # Create some equipment, a equipment list, and a fighter and
    # write a query to get the equipment list for the fighter

    # Create some equipment
    equipment = ContentEquipment.objects.create(
        name="Wooden Spoon", category=EquipmentCategoryChoices.BASIC_WEAPONS
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
def test_equipment_cost_negative():
    # Create some equipment
    equipment = ContentEquipment.objects.create(
        name="Wooden Spoon", category=EquipmentCategoryChoices.BASIC_WEAPONS
    )
    equipment.save()

    # Create a fighter
    fighter = ContentFighter.objects.create(
        type="Charter Master",
        category=FighterCategoryChoices.LEADER,
    )
    fighter.save()

    # Create a equipment list with negative cost
    fighter_equip = ContentFighterEquipmentListItem(
        fighter=fighter, equipment=equipment, cost=-10
    )

    with pytest.raises(ValidationError, match="Cost cannot be negative."):
        fighter_equip.clean()


@pytest.mark.django_db
def test_equipment_weapon_profile_mismatch():
    # Create some equipment
    equipment1 = ContentEquipment.objects.create(
        name="Wooden Spoon", category=EquipmentCategoryChoices.BASIC_WEAPONS
    )
    equipment1.save()

    equipment2 = ContentEquipment.objects.create(
        name="Fork", category=EquipmentCategoryChoices.BASIC_WEAPONS
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
        name="Wooden Spoon", category=EquipmentCategoryChoices.BASIC_WEAPONS, cost="5"
    )

    fork = ContentEquipment.objects.create(
        name="Fork", category=EquipmentCategoryChoices.BASIC_WEAPONS, cost="10"
    )

    knife = ContentEquipment.objects.create(
        name="Knife", category=EquipmentCategoryChoices.BASIC_WEAPONS, cost="15"
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
