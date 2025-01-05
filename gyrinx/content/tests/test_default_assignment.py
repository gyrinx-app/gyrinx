import pytest

from gyrinx.content.models import ContentEquipment, ContentFighter, ContentHouse
from gyrinx.models import EquipmentCategoryChoices, FighterCategoryChoices


@pytest.mark.django_db
def test_basic_default_assignment():
    house, _ = ContentHouse.objects.get_or_create(
        name="Spoonlickers",
    )
    fighter, _ = ContentFighter.objects.get_or_create(
        type="Sporker", category=FighterCategoryChoices.JUVE, house=house
    )
    holster, _ = ContentEquipment.objects.get_or_create(
        name="Holster", category=EquipmentCategoryChoices.EQUIPMENT, cost=10
    )

    fighter_equip = fighter.default_assignments.create(equipment=holster)

    assert fighter.default_assignments.count() == 1
    assert fighter_equip.fighter == fighter


@pytest.mark.django_db
def test_default_assignment_with_weapon_profile():
    house, _ = ContentHouse.objects.get_or_create(
        name="Spoonlickers",
    )
    fighter, _ = ContentFighter.objects.get_or_create(
        type="Sporker", category=FighterCategoryChoices.JUVE, house=house
    )
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Spoon", category=EquipmentCategoryChoices.BASIC_WEAPONS, cost=10
    )

    fighter_equip = fighter.default_assignments.create(equipment=spoon)
    spoon_profile = fighter_equip.weapon_profiles.create(equipment=spoon)

    assert fighter.default_assignments.count() == 1
    assert fighter.default_assignments.first().equipment == spoon
    assert fighter.default_assignments.first().weapon_profiles.contains(spoon_profile)
