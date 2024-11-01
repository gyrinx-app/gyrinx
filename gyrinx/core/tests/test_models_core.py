import uuid

import pytest

from gyrinx.content.models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentAssignment,
    ContentHouse,
    ContentImportVersion,
)
from gyrinx.core.models import Build, BuildFighter


def make_content():
    version = ContentImportVersion.objects.create(
        uuid=uuid.uuid4(), ruleset="necromunda-2018", directory="content"
    )
    category = ContentCategory.objects.create(
        name=ContentCategory.Choices.JUVE,
        uuid=uuid.uuid4(),
        version=version,
    )
    house = ContentHouse.objects.create(
        name=ContentHouse.Choices.SQUAT_PROSPECTORS,
        uuid=uuid.uuid4(),
        version=version,
    )
    fighter = ContentFighter.objects.create(
        uuid=uuid.uuid4(),
        type="Prospector Digger",
        category=category,
        house=house,
        base_cost=100,
    )
    return version, category, house, fighter


@pytest.mark.django_db
def test_basic_build():
    version, category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)

    assert build.name == "Test Build"


@pytest.mark.django_db
def test_basic_build_fighter():
    version, category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert build.name == "Test Build"
    assert fighter.name == "Test Fighter"


@pytest.mark.django_db
def test_build_fighter_requires_content_fighter():
    version, category, house, content_fighter = make_content()
    build = Build.objects.create(name="Test Build", content_house=house)
    with pytest.raises(Exception):
        BuildFighter.objects.create(name="Test Fighter", build=build)


@pytest.mark.django_db
def test_build_fighter_content_fighter():
    version, category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, content_fighter=content_fighter
    )

    assert fighter.content_fighter.type == "Prospector Digger"


@pytest.mark.django_db
def test_build_fighter_house_matches_build():
    version, category, house, content_fighter = make_content()

    build_house = ContentHouse.objects.create(
        name=ContentHouse.Choices.ASH_WASTE_NOMADS,
        uuid=uuid.uuid4(),
        version=version,
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
    version, category, house, content_fighter = make_content()

    build = Build.objects.create(name="Test Build", content_house=house)

    build.archive()

    assert build.archived
    assert build.archived_at is not None


@pytest.mark.django_db
def test_history():
    version, category, house, content_fighter = make_content()

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
    version, category, house, content_fighter = make_content()

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
    version, category, house, content_fighter = make_content()
    content_fighter2 = ContentFighter.objects.create(
        uuid=uuid.uuid4(),
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
    version, category, house, content_fighter = make_content()
    spoon = ContentEquipment.objects.create(
        version=version,
        uuid=uuid.uuid4(),
        name="Wooden Spoon",
        category=ContentEquipmentCategory.objects.create(
            uuid=uuid.uuid4(),
            name=ContentEquipmentCategory.Choices.BASIC_WEAPONS,
            version=version,
        ),
        trading_post_cost=10,
    )
    spoon.save()

    ContentFighterEquipmentAssignment.objects.create(
        version=version,
        uuid=uuid.uuid4(),
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
