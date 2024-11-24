import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentFighterEquipment,
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
    fighter_equip = ContentFighterEquipment(fighter=fighter, equipment=equipment)
    fighter_equip.save()

    # Query to get the equipment list for the fighter
    fe = ContentFighterEquipment.objects.get(fighter=fighter)
    assert fe.equipment.name == "Wooden Spoon"
    assert fe.fighter.type == "Charter Master"
