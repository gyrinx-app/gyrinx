from typing import Callable

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentHouse,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.fixture(scope="session", autouse=True)
def django_test_settings():
    """Configure Django settings for tests to avoid static files issues."""
    settings.STORAGES["staticfiles"]["BACKEND"] = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )


@pytest.fixture
def make_user(django_user_model) -> Callable[[str, str], object]:
    def make_user_(username: str, password: str) -> object:
        return django_user_model.objects.create_user(
            username=username, password=password
        )

    return make_user_


@pytest.fixture
def user(make_user):
    return make_user("testuser", "password")


@pytest.fixture
def make_content_house() -> Callable[[str], ContentHouse]:
    def make_content_house_(name: str, **kwargs) -> ContentHouse:
        return ContentHouse.objects.create(name=name, **kwargs)

    return make_content_house_


@pytest.fixture
def content_house(make_content_house) -> ContentHouse:
    return make_content_house("Squat Prospectors")


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
        movement='5"',
        weapon_skill="5+",
        ballistic_skill="5+",
        strength="4",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="8+",
        cool="7+",
        willpower="6+",
        intelligence="7+",
    )


@pytest.fixture
def make_list(user, content_house: ContentHouse) -> Callable[[str], List]:
    def make_list_(name, **kwargs) -> List:
        kwargs = {
            "content_house": content_house,
            "owner": user,
            **kwargs,
        }
        return List.objects.create(name=name, **kwargs)

    return make_list_


@pytest.fixture
def make_list_fighter(user, content_fighter) -> Callable[[List, str], ListFighter]:
    def make_list_fighter_(list_: List, name: str, **kwargs) -> ListFighter:
        kwargs = {
            "owner": user,
            "content_fighter": content_fighter,
            **kwargs,
        }
        return ListFighter.objects.create(list=list_, name=name, **kwargs)

    return make_list_fighter_


@pytest.fixture
def make_equipment():
    def make_equipment_(name, **kwargs) -> Callable[[str], ContentEquipment]:
        return ContentEquipment.objects.create(name=name, **kwargs)

    return make_equipment_


@pytest.fixture
def make_weapon_profile():
    def make_weapon_profile_(
        equipment, **kwargs
    ) -> Callable[[str], ContentWeaponProfile]:
        return ContentWeaponProfile.objects.create(equipment=equipment, **kwargs)

    return make_weapon_profile_


@pytest.fixture
def make_weapon_accessory():
    def make_weapon_accessory_(
        name, **kwargs
    ) -> Callable[[str], ContentWeaponAccessory]:
        return ContentWeaponAccessory.objects.create(name=name, **kwargs)

    return make_weapon_accessory_


@pytest.fixture
def make_campaign(user) -> Callable[[str], Campaign]:
    def make_campaign_(name: str, **kwargs) -> Campaign:
        kwargs = {
            "owner": user,
            **kwargs,
        }
        return Campaign.objects.create(name=name, **kwargs)

    return make_campaign_


@pytest.fixture
def campaign(make_campaign) -> Campaign:
    """A basic campaign for testing."""
    return make_campaign("Test Campaign", status=Campaign.IN_PROGRESS)


@pytest.fixture
def house() -> ContentHouse:
    """Alias for content_house for backward compatibility."""
    return ContentHouse.objects.create(name="Test House")


@pytest.fixture
def list_with_campaign(user, content_house, campaign) -> List:
    """A list in campaign mode with an associated campaign."""
    lst = List.objects.create(
        name="Test List",
        content_house=content_house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    campaign.lists.add(lst)
    return lst
