import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentHouse,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_basic_default_assignment(content_equipment_categories):
    house, _ = ContentHouse.objects.get_or_create(
        name="Spoonlickers",
    )
    fighter, _ = ContentFighter.objects.get_or_create(
        type="Sporker", category=FighterCategoryChoices.JUVE, house=house
    )
    holster, _ = ContentEquipment.objects.get_or_create(
        name="Holster",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    fighter_equip = fighter.default_assignments.create(equipment=holster)

    assert fighter.default_assignments.count() == 1
    assert fighter_equip.fighter == fighter


@pytest.mark.django_db
def test_default_assignment_with_weapon_profile(content_equipment_categories):
    house, _ = ContentHouse.objects.get_or_create(
        name="Spoonlickers",
    )
    fighter, _ = ContentFighter.objects.get_or_create(
        type="Sporker", category=FighterCategoryChoices.JUVE, house=house
    )
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Spoon",
        category=ContentEquipmentCategory.objects.get(name="Basic Weapons"),
        cost=10,
    )

    fighter_equip: ContentFighterDefaultAssignment = fighter.default_assignments.create(
        equipment=spoon
    )
    spoon_profile = fighter_equip.weapon_profiles_field.create(equipment=spoon)

    assert fighter.default_assignments.count() == 1
    assert fighter.default_assignments.first().equipment == spoon
    assert fighter.default_assignments.first().weapon_profiles_field.contains(
        spoon_profile
    )
