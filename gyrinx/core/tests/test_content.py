import uuid

import pytest

from gyrinx.core.models import Category, Fighter, House


@pytest.mark.django_db
def test_basic_fighter():
    version = uuid.uuid4()
    category = Category.objects.create(
        name=Category.CategoryNameChoices.JUVE,
        uuid=uuid.uuid4(),
        version=version,
    )
    house = House.objects.create(
        name=House.HouseNameChoices.SQUAT_PROSPECTORS,
        uuid=uuid.uuid4(),
        version=version,
    )
    fighter = Fighter.objects.create(
        uuid=uuid.uuid4(), type="Prospector Digger", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Prospector Digger"
    assert fighter.category.name == Category.CategoryNameChoices.JUVE
