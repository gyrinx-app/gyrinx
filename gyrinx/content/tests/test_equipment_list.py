import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterEquipmentListItem,
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
        ValidationError, match="Weapon profile must be for the same equipment."
    ):
        fighter_equip.clean()
