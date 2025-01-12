from typing import Callable

import pytest

from gyrinx.content.models import ContentEquipment, ContentFighter, ContentHouse
from gyrinx.core.models import List, ListFighter
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def make_user(django_user_model) -> Callable[[str, str], object]:
    def make_user_(username: str, password: str) -> object:
        return django_user_model.objects.create_user(
            username=username, password=password
        )

    return make_user_


@pytest.fixture
@pytest.mark.django_db
def user(make_user):
    return make_user("testuser", "password")


@pytest.fixture
def content_house():
    return ContentHouse.objects.create(
        name="Squat Prospectors",
    )


@pytest.fixture
def make_content_fighter() -> Callable[[str, str, int], ContentFighter]:
    def make_content_fighter_(
        type: str,
        category: FighterCategoryChoices,
        house: ContentHouse,
        base_cost: int,
        **kwargs,
    ) -> ContentFighter:
        return ContentFighter.objects.create(
            type=type,
            category=category,
            house=house,
            base_cost=base_cost,
            **kwargs,
        )

    return make_content_fighter_


@pytest.fixture
def content_fighter(content_house, make_content_fighter):
    return make_content_fighter(
        type="Prospector Digger",
        category=FighterCategoryChoices.JUVE,
        house=content_house,
        base_cost=100,
    )


@pytest.fixture
def make_list(user, content_house: ContentHouse) -> Callable[[str], List]:
    def make_list_(name) -> List:
        return List.objects.create(name=name, content_house=content_house, owner=user)

    return make_list_


@pytest.fixture
def make_list_fighter(user, content_fighter) -> Callable[[List, str], ListFighter]:
    def make_list_fighter_(list_: List, name: str, **kwargs) -> ListFighter:
        return ListFighter.objects.create(
            list=list_, name=name, content_fighter=content_fighter, owner=user, **kwargs
        )

    return make_list_fighter_


@pytest.fixture
def make_equipment():
    def make_equipment_(name, **kwargs) -> Callable[[str], ContentEquipment]:
        return ContentEquipment.objects.create(name=name, **kwargs)

    return make_equipment_
