# A simple check to see if the test suite is working
import uuid

import pytest

from gyrinx.core.models import Category, Fighter, House


def test_nothing():
    assert True


@pytest.mark.django_db
def test_basic_fighter():
    version = uuid.uuid4()
    category = Category.objects.create(
        name=Category.CategoryNameChoices.NONE,
        uuid=uuid.uuid4(),
        version=version,
    )
    house = House.objects.create(
        name=House.HouseNameChoices.ORLOCK_HOI,
        uuid=uuid.uuid4(),
        version=version,
    )
    fighter = Fighter.objects.create(
        uuid=uuid.uuid4(), type="Example Fighter", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Example Fighter"
    assert fighter.category.name == Category.CategoryNameChoices.NONE
