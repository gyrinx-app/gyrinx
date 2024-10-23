import uuid

import pytest

from gyrinx.core.models import ContentCategory, ContentFighter, ContentHouse


@pytest.mark.django_db
def test_basic_fighter():
    version = uuid.uuid4()
    category = ContentCategory.objects.create(
        name=ContentCategory.ContentCategoryNameChoices.JUVE,
        uuid=uuid.uuid4(),
        version=version,
    )
    house = ContentHouse.objects.create(
        name=ContentHouse.ContentHouseNameChoices.SQUAT_PROSPECTORS,
        uuid=uuid.uuid4(),
        version=version,
    )
    fighter = ContentFighter.objects.create(
        uuid=uuid.uuid4(), type="Prospector Digger", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Prospector Digger"
    assert fighter.category.name == ContentCategory.ContentCategoryNameChoices.JUVE
