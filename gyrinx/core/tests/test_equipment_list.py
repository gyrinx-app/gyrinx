import uuid

import pytest

from gyrinx.core.models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipment,
)


@pytest.mark.django_db
def test_equipment():
    # Create some equipment, a equipment list, and a fighter and
    # write a query to get the equipment list for the fighter

    # Create some equipment
    category = ContentEquipmentCategory.objects.create(
        uuid=uuid.uuid4(),
        name=ContentEquipmentCategory.Choices.BASIC_WEAPONS,
    )
    equipment = ContentEquipment.objects.create(
        uuid=uuid.uuid4(), name="Wooden Spoon", category=category
    )
    category.save()
    equipment.save()

    # Create a fighter
    fighter = ContentFighter.objects.create(
        uuid=uuid.uuid4(),
        type="Charter Master",
        category=ContentCategory.objects.create(
            uuid=uuid.uuid4(), name=ContentCategory.Choices.LEADER
        ),
    )
    fighter.save()

    # Create a equipment list
    fighter_equip = ContentFighterEquipment(
        uuid=uuid.uuid4(), fighter=fighter, equipment=equipment
    )
    fighter_equip.save()

    # Query to get the equipment list for the fighter
    fe = ContentFighterEquipment.objects.get(fighter=fighter)
    assert fe.equipment.name == "Wooden Spoon"
    assert fe.fighter.type == "Charter Master"
