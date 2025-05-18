import pytest

from gyrinx.content.models import ContentEquipmentCategory
from gyrinx.core.models.list import ListFighter


@pytest.mark.django_db
def test_house_additional_assignments(
    content_fighter,
    make_list,
    make_list_fighter,
    make_equipment,
    make_weapon_profile,
):
    house = content_fighter.house
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="House Additional Category"
    )
    category.restricted_to.add(house)

    spoon = make_equipment(
        "Spoonetika",
        category=category,
        cost=10,
    )

    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Assign the weapon to the fighter
    fighter.assign(spoon)

    # Refresh because cache
    fighter = ListFighter.objects.get(pk=fighter.pk)

    assert len(fighter.assignments()) == 1
    assert len(fighter.house_additional_assignments(category)) == 1
    assign = fighter.assignments()[0]
    assert assign.content_equipment == spoon
    assert assign.is_house_additional
    assert assign.category == category.name
