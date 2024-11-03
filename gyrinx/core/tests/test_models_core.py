import pytest

from gyrinx.content.models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentAssignment,
    ContentHouse,
)
from gyrinx.core.models import Build, BuildFighter


def make_content():
    category = ContentCategory.objects.create(
        name=ContentCategory.Choices.JUVE,
    )
    house = ContentHouse.objects.create(
        name=ContentHouse.Choices.SQUAT_PROSPECTORS,
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
        base_cost=100,
    )
    return category, house, fighter


@pytest.mark.django_db
def test_basic_build():
    category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)

    assert build.name == "Test Build"


@pytest.mark.django_db
def test_basic_build_fighter():
    category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert build.name == "Test Build"
    assert fighter.name == "Test Fighter"


@pytest.mark.django_db
def test_build_fighter_requires_content_fighter():
    category, house, content_fighter = make_content()
    build = Build.objects.create(name="Test Build", content_house=house)
    with pytest.raises(Exception):
        BuildFighter.objects.create(name="Test Fighter", build=build)


@pytest.mark.django_db
def test_build_fighter_content_fighter():
    category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert fighter.content_fighter.type == "Prospector Digger"


@pytest.mark.django_db
def test_build_fighter_house_matches_build():
    category, house, content_fighter = make_content()

    build_house = ContentHouse.objects.create(
        name=ContentHouse.Choices.ASH_WASTE_NOMADS,
    )

    build = Build.objects.create(name="Test Build AWN", content_house=build_house)

    with pytest.raises(
        Exception,
        match="Prospector Digger cannot be a member of Ash Waste Nomads build",
    ):
        BuildFighter.objects.create(
            name="Test Fighter", build=build, content_fighter=content_fighter
        ).full_clean()


@pytest.mark.django_db
def test_archive_build():
    category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)

    build.archive()

    assert build.archived
    assert build.archived_at is not None


@pytest.mark.django_db
def test_history():
    category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)

    assert build.history.all().count() == 1

    build.name = "Test Build 2"
    build.save()

    assert build.history.all().count() == 2
    assert build.history.first().name == "Test Build 2"

    build.archive()

    assert build.history.first().archived
    assert not build.history.first().prev_record.archived


@pytest.mark.django_db
def test_build_cost():
    category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert fighter.cost() == content_fighter.cost()
    assert build.cost() == content_fighter.cost()

    fighter2 = BuildFighter.objects.create(
        name="Test Fighter 2", build=build, content_fighter=content_fighter
    )

    assert fighter2.cost() == content_fighter.cost()
    assert build.cost() == content_fighter.cost() * 2


@pytest.mark.django_db
def test_build_cost_variable():
    category, house, content_fighter = make_content()
    content_fighter2 = ContentFighter.objects.create(
        type="Expensive Guy",
        category=category,
        house=house,
        base_cost=150,
    )

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )
    fighter2 = BuildFighter.objects.create(
        name="Test Fighter 2", build=build, content_fighter=content_fighter2
    )

    assert fighter.cost() == content_fighter.cost()
    assert fighter2.cost() == content_fighter2.cost()
    assert build.cost() == content_fighter.cost() + content_fighter2.cost()


@pytest.mark.django_db
def test_build_fighter_with_spoon():
    category, house, content_fighter = make_content()
    spoon = ContentEquipment.objects.create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.create(
            name=ContentEquipmentCategory.Choices.BASIC_WEAPONS,
        ),
        trading_post_cost=10,
    )
    spoon.save()

    ContentFighterEquipmentAssignment.objects.create(
        equipment=spoon,
        fighter=content_fighter,
        qty=1,
    ).save()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert fighter.cost() == content_fighter.base_cost + spoon.cost()
    assert build.cost() == fighter.cost()
    assert build.cost() == 110


@pytest.mark.django_db
def test_build_fighter_with_spoon_and_not_other_assignments():
    # This test was introduced to fix a bug where the cost of a fighter was
    # including all equipment assignments, not just the ones for that fighter.

    category, house, content_fighter = make_content()
    spoon = ContentEquipment.objects.create(
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.create(
            name=ContentEquipmentCategory.Choices.BASIC_WEAPONS,
        ),
        trading_post_cost=10,
    )
    spoon.save()

    ContentFighterEquipmentAssignment.objects.create(
        equipment=spoon,
        fighter=content_fighter,
        qty=1,
    ).save()

    content_fighter2 = ContentFighter.objects.create(
        type="Expensive Guy",
        category=category,
        house=house,
        base_cost=150,
    )

    spork = ContentEquipment.objects.create(
        name="Metal Spork",
        category=ContentEquipmentCategory.objects.create(
            name=ContentEquipmentCategory.Choices.BASIC_WEAPONS,
        ),
        trading_post_cost=15,
    )
    spork.save()

    ContentFighterEquipmentAssignment.objects.create(
        equipment=spork,
        fighter=content_fighter2,
        qty=1,
    ).save()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert fighter.cost() == content_fighter.base_cost + spoon.cost()
    assert build.cost() == fighter.cost()
    assert build.cost() == 110
