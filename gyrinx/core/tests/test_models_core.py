import uuid

import pytest

from gyrinx.content.models import (
    ContentCategory,
    ContentFighter,
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
        uuid=uuid.uuid4(), type="Prospector Digger", category=category, house=house
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
