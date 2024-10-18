import uuid

import pytest

from gyrinx.core.models import (
    Category,
    Equipment,
    EquipmentCategory,
    Fighter,
    FighterEquipment,
)


@pytest.mark.django_db
def test_equipment():
    # Create some equipment, a equipment list, and a fighter and
    # write a query to get the equipment list for the fighter

    # Create some equipment
    category = EquipmentCategory.objects.create(
        uuid=uuid.uuid4(),
        name=EquipmentCategory.EquipmentCategoryNameChoices.BASIC_WEAPONS,
    )
    equipment = Equipment.objects.create(
        uuid=uuid.uuid4(), name="Wooden Spoon", category=category
    )
    category.save()
    equipment.save()

    # Create a fighter
    fighter = Fighter.objects.create(
        uuid=uuid.uuid4(),
        type="Charter Master",
        category=Category.objects.create(
            uuid=uuid.uuid4(), name=Category.CategoryNameChoices.LEADER
        ),
    )
    fighter.save()

    # Create a equipment list
    fighter_equip = FighterEquipment(
        uuid=uuid.uuid4(), fighter=fighter, equipment=equipment
    )
    fighter_equip.save()

    # Query to get the equipment list for the fighter
    fe = FighterEquipment.objects.get(fighter=fighter)
    assert fe.equipment.name == "Wooden Spoon"
    assert fe.fighter.type == "Charter Master"
