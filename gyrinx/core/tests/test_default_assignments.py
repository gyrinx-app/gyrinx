import pytest

from gyrinx.content.models import ContentEquipment, ContentWeaponProfile
from gyrinx.core.models import List, ListFighter
from gyrinx.core.tests.test_models_core import make_content
from gyrinx.models import EquipmentCategoryChoices


@pytest.mark.django_db
def test_fighter_with_default_spoon_weapon_assignment():
    category, house, content_fighter = make_content()
    spoon, _ = ContentEquipment.objects.get_or_create(
        name="Wooden Spoon",
        category=EquipmentCategoryChoices.BASIC_WEAPONS,
        cost=10,
    )

    spoon_profile, _ = ContentWeaponProfile.objects.get_or_create(equipment=spoon)

    content_fighter_equip = content_fighter.default_assignments.create(equipment=spoon)
    content_fighter_equip.weapon_profiles_field.add(spoon_profile)

    lst, _ = List.objects.get_or_create(name="Test List", content_house=house)
    fighter, _ = ListFighter.objects.get_or_create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert len(fighter.assignments()) == 1
    assert fighter.assignments()[0].content_equipment == spoon
    # Spoon is default and therefore free
    assert fighter.cost_int() == content_fighter.cost_int()
