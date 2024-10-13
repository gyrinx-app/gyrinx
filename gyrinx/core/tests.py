# A simple check to see if the test suite is working
import uuid

import pytest

from gyrinx.core.models import Category, Fighter, House


def test_nothing():
    assert True


@pytest.mark.django_db
def test_basic_fighter():
    category = Category.objects.create()
    house = House.objects.create(name=House.HouseNameChoices.ORLOCK_HOI)
    fighter = Fighter.objects.create(
        uuid=uuid.uuid4(), type="Example Fighter", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Example Fighter"
    assert fighter.category.name == Category.CategoryNameChoices.NONE
