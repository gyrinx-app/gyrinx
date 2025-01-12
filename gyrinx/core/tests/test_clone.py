import pytest

from gyrinx.core.models import List, ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_basic_list_clone(make_list, make_list_fighter, make_equipment):
    list_ = make_list("Test List")
    fighter: ListFighter = make_list_fighter(list_, "Test Fighter")
    spoon = make_equipment("Spoon")
    fighter.assign(spoon)

    list_clone: List = list_.clone(
        name="Test List (Clone)",
    )

    assert list_clone.name == "Test List (Clone)"
    assert list_clone.owner == list_.owner
    assert list_clone.content_house == list_.content_house
    assert list_clone.public == list_.public
    assert list_clone.fighters().count() == 1

    fighter_clone = list_clone.fighters().first()

    assert fighter_clone.name == "Test Fighter"
    assert fighter_clone.content_fighter == fighter.content_fighter
    assert fighter_clone.owner == fighter.owner
    assert fighter_clone.archived == fighter.archived

    assert fighter_clone.equipment.all().count() == 1
    assert fighter_clone.equipment.all().first().name == "Spoon"


@pytest.mark.django_db
def test_list_clone_with_mods(make_list, make_user):
    list_ = make_list("Test List")
    new_owner = make_user("new_owner", "password")

    list_clone: List = list_.clone(
        name="Test List (Clone)",
        owner=new_owner,
        public=False,
    )

    assert list_clone.public is False
    assert list_clone.owner == new_owner


@pytest.mark.django_db
def test_fighter_clone_with_mods(
    make_list, make_list_fighter, make_equipment, make_content_fighter
):
    list_ = make_list("Test List")
    fighter: ListFighter = make_list_fighter(list_, "Test Fighter")
    spoon = make_equipment("Spoon")
    fighter.assign(spoon)

    new_content_fighter = make_content_fighter(
        type="Drill Master",
        category=FighterCategoryChoices.CHAMPION,
        house=fighter.content_fighter.house,
        base_cost=200,
    )

    new_fighter = fighter.clone(
        name="Test Fighter (Clone)",
        content_fighter=new_content_fighter,
        narrative="This is a clone.",
    )

    assert new_fighter.name == "Test Fighter (Clone)"
    assert new_fighter.content_fighter == new_content_fighter
    assert new_fighter.owner == fighter.owner
    assert new_fighter.archived == fighter.archived
    assert new_fighter.narrative == "This is a clone."
    assert new_fighter.equipment.all().count() == 1
    assert new_fighter.equipment.all().first().name == "Spoon"
