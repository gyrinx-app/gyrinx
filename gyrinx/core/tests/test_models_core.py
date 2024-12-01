import pytest

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.models import List, ListFighter
from gyrinx.models import FighterCategoryChoices


def make_content():
    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
        base_cost=100,
    )
    return category, house, fighter


@pytest.mark.django_db
def test_basic_list():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)

    assert lst.name == "Test List"


@pytest.mark.django_db
def test_basic_list_fighter():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert lst.name == "Test List"
    assert fighter.name == "Test Fighter"


@pytest.mark.django_db
def test_list_fighter_requires_content_fighter():
    category, house, content_fighter = make_content()
    lst = List.objects.create(name="Test List", content_house=house)
    with pytest.raises(Exception):
        ListFighter.objects.create(name="Test Fighter", list=lst)


@pytest.mark.django_db
def test_list_fighter_content_fighter():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.content_fighter.type == "Prospector Digger"


@pytest.mark.django_db
def test_list_fighter_house_matches_list():
    category, house, content_fighter = make_content()

    house = ContentHouse.objects.create(
        name="Ash Waste Nomads",
    )

    lst = List.objects.create(name="Test List AWN", content_house=house)

    with pytest.raises(
        Exception,
        match="Prospector Digger cannot be a member of Ash Waste Nomads list",
    ):
        ListFighter.objects.create(
            name="Test Fighter", list=lst, content_fighter=content_fighter
        ).full_clean()


@pytest.mark.django_db
def test_archive_list():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)

    lst.archive()

    assert lst.archived
    assert lst.archived_at is not None


@pytest.mark.django_db
def test_history():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)

    assert lst.history.all().count() == 1

    lst.name = "Test List 2"
    lst.save()

    assert lst.history.all().count() == 2
    assert lst.history.first().name == "Test List 2"

    lst.archive()

    assert lst.history.first().archived
    assert not lst.history.first().prev_record.archived


@pytest.mark.django_db
def test_list_cost():
    category, house, content_fighter = make_content()

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )

    assert fighter.cost() == content_fighter.cost()
    assert lst.cost() == content_fighter.cost()

    fighter2 = ListFighter.objects.create(
        name="Test Fighter 2", list=lst, content_fighter=content_fighter
    )

    assert fighter2.cost() == content_fighter.cost()
    assert lst.cost() == content_fighter.cost() * 2


@pytest.mark.django_db
def test_list_cost_variable():
    category, house, content_fighter = make_content()
    content_fighter2 = ContentFighter.objects.create(
        type="Expensive Guy",
        category=category,
        house=house,
        base_cost=150,
    )

    lst = List.objects.create(name="Test List", content_house=house)
    fighter = ListFighter.objects.create(
        name="Test Fighter", list=lst, content_fighter=content_fighter
    )
    fighter2 = ListFighter.objects.create(
        name="Test Fighter 2", list=lst, content_fighter=content_fighter2
    )

    assert fighter.cost() == content_fighter.cost()
    assert fighter2.cost() == content_fighter2.cost()
    assert lst.cost() == content_fighter.cost() + content_fighter2.cost()


# @pytest.mark.django_db
# def test_list_fighter_with_spoon():
#     category, house, content_fighter = make_content()
#     spoon, _ = ContentEquipment.objects.get_or_create(
#         name="Wooden Spoon",
#         category=EquipmentCategoryChoices.BASIC_WEAPONS,
#         cost=10,
#     )
#     spoon.save()

#     lst = List.objects.create(name="Test List", content_house=house)
#     fighter = List.objects.create(
#         name="Test Fighter", list=lst, content_fighter=content_fighter
#     )

#     assert fighter.cost() == content_fighter.base_cost + spoon.cost()
#     assert lst.cost() == fighter.cost()
#     assert lst.cost() == 110


# @pytest.mark.django_db
# def test_list_fighter_with_spoon_and_not_other_assignments():
#     # This test was introduced to fix a bug where the cost of a fighter was
#     # including all equipment assignments, not just the ones for that fighter.

#     category, house, content_fighter = make_content()
#     spoon = ContentEquipment.objects.create(
#         name="Wooden Spoon",
#         category=EquipmentCategoryChoices.BASIC_WEAPONS,
#     )
#     spoon.save()

#     ContentFighterEquipmentAssignment.objects.create(
#         equipment=spoon,
#         fighter=content_fighter,
#         qty=1,
#     ).save()

#     content_fighter2 = ContentFighter.objects.create(
#         type="Expensive Guy",
#         category=category,
#         house=house,
#         base_cost=150,
#     )

#     spork = ContentEquipment.objects.create(
#         name="Metal Spork",
#         category=EquipmentCategoryChoices.BASIC_WEAPONS,
#     )
#     spork.save()

#     ContentFighterEquipmentAssignment.objects.create(
#         equipment=spork,
#         fighter=content_fighter2,
#         qty=1,
#     ).save()

#     lst = Build.objects.create(name="Test List", content_house=house)
#     fighter = BuildFighter.objects.create(
#         name="Test Fighter", list=lst, content_fighter=content_fighter
#     )

#     assert fighter.cost() == content_fighter.base_cost + spoon.cost()
#     assert lst.cost() == fighter.cost()
#     assert lst.cost() == 110
