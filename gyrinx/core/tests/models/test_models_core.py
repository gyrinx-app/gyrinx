import uuid

import pytest

from gyrinx.core.models import Build, BuildFighter


@pytest.mark.django_db
def test_basic_build():
    build = Build.objects.create(name="Test Build", house_uuid=uuid.uuid4())

    assert build.name == "Test Build"


@pytest.mark.django_db
def test_basic_build_fighter():
    build = Build.objects.create(name="Test Build", house_uuid=uuid.uuid4())
    fighter = BuildFighter.objects.create(
        name="Test Fighter", build=build, fighter_uuid=uuid.uuid4()
    )

    assert build.name == "Test Build"
    assert fighter.name == "Test Fighter"
