from typing import Callable
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache

from gyrinx.content.models import (
    ContentBook,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentPageRef,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.context_processors import BANNER_CACHE_KEY
from gyrinx.core.models.action import ListAction, ListActionType
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

    # This prevents the banner query being fired in tests
    cache.set(BANNER_CACHE_KEY, False, None)

    # Optimize test performance
    # Disable DEBUG to avoid query tracking overhead
    settings.DEBUG = False

    # Disable GYRINX_DEBUG to avoid debug UI elements in test output
    settings.GYRINX_DEBUG = False

    # Use faster password hasher for tests (MD5 instead of PBKDF2)
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


@pytest.fixture(scope="session", autouse=True)
def warm_contenttype_cache(django_db_setup, django_db_blocker):
    """Warm up ContentType cache for polymorphic models at test session start.

    This ensures consistent query counts regardless of whether tests run
    in isolation or as part of a larger suite. Polymorphic models (ContentMod
    and subclasses) trigger ContentType lookups, and the cache state varies
    without this initialization.
    """
    with django_db_blocker.unblock():
        from django.contrib.contenttypes.models import ContentType

        from gyrinx.content.models import ContentMod, ContentModFighterStat

        ContentType.objects.get_for_model(ContentMod)
        ContentType.objects.get_for_model(ContentModFighterStat)


@pytest.fixture(autouse=True)
def disable_cost_cache_in_tests(request):
    """
    Disable expensive cost cache updates in all tests by default.

    The cost cache updates are expensive operations that recalculate
    the entire list cost on every save. This is unnecessary for most
    tests and significantly slows down test execution.

    Tests that specifically need to test cost calculations can
    re-enable this by using the 'with_cost_cache' marker.
    """
    # Check if the test has the 'with_cost_cache' marker
    if request.node.get_closest_marker("with_cost_cache"):
        # Don't mock for this test
        yield
    else:
        # Mock the cost cache update for performance
        with patch("gyrinx.core.models.list.List.update_cost_cache"):
            yield


@pytest.fixture(scope="session")
def content_books(django_db_setup, django_db_blocker):
    """Create ContentBook objects needed for tests."""
    with django_db_blocker.unblock():
        books_data = [
            {"shortname": "Core", "name": "Core Rulebook", "obsolete": False},
            {"shortname": "Outcast", "name": "Book of the Outcast", "obsolete": False},
            {
                "shortname": "Outlands",
                "name": "Book of the Outlands",
                "obsolete": False,
            },
            {"shortname": "HoI", "name": "House of Iron", "obsolete": False},
            {"shortname": "HoA", "name": "House of Artifice", "obsolete": False},
            {"shortname": "HoB", "name": "House of Blades", "obsolete": False},
            {"shortname": "HoC", "name": "House of Chains", "obsolete": False},
            {"shortname": "GW2018", "name": "Gang War 2018", "obsolete": True},
        ]
        for book_data in books_data:
            ContentBook.objects.get_or_create(**book_data)
        return ContentBook.objects.all()


@pytest.fixture(scope="session")
def content_equipment_categories(django_db_setup, django_db_blocker):
    """Create ContentEquipmentCategory objects needed for tests."""
    with django_db_blocker.unblock():
        categories = [
            # Weapons & Ammo
            ("Basic Weapons", "Weapons & Ammo"),
            ("Close Combat Weapons", "Weapons & Ammo"),
            ("Pistols", "Weapons & Ammo"),
            ("Special Weapons", "Weapons & Ammo"),
            ("Heavy Weapons", "Weapons & Ammo"),
            ("Grenades", "Weapons & Ammo"),
            ("Ammo", "Weapons & Ammo"),
            ("Power Pack Weapons", "Weapons & Ammo"),
            # Gear
            ("Armor", "Gear"),
            ("Personal Equipment", "Gear"),
            ("Gang Equipment", "Gear"),
            ("Status Items", "Gear"),
            ("Bionics", "Gear"),
            ("Body Upgrades", "Gear"),
            ("Booby Traps", "Gear"),
            ("Chem-alchemy Elixirs", "Gear"),
            ("Chems", "Gear"),
            ("Cyberteknika", "Gear"),
            ("Equipment", "Gear"),
            ("Field Armour", "Gear"),
            ("Gang Terrain", "Gear"),
            ("Gene-smithing", "Gear"),
            ("Relics", "Gear"),
            # Vehicle & Mount
            ("Drive Upgrades", "Vehicle & Mount"),
            ("Engine Upgrades", "Vehicle & Mount"),
            ("Hardpoint Upgrades", "Vehicle & Mount"),
            ("Mounts", "Vehicle & Mount"),
            ("Vehicle Wargear", "Vehicle & Mount"),
            ("Vehicles", "Vehicle & Mount"),
            # Other
            ("Options", "Other"),
        ]
        for name, group in categories:
            ContentEquipmentCategory.objects.get_or_create(
                name=name, defaults={"group": group}
            )
        return ContentEquipmentCategory.objects.all()


@pytest.fixture(scope="session")
def content_page_refs(django_db_setup, django_db_blocker, content_books):
    """Create sample ContentPageRef objects for tests."""
    with django_db_blocker.unblock():
        # Create specific page refs that tests expect
        core_book = ContentBook.objects.get(shortname="Core")
        outcast_book = ContentBook.objects.get(shortname="Outcast")

        refs_data = [
            {
                "title": "Agility",
                "book": core_book,
                "category": "Skills",
                "page": "256",
            },
            {
                "title": "Ironhead Squat Prospectors Charter Master",
                "book": core_book,
                "category": "Fighters",
                "page": "100",
            },
            {
                "title": "Settlement Raid",
                "book": core_book,
                "category": "Scenarios",
                "page": "300",
            },
            {
                "title": "Settlement Raid",
                "book": outcast_book,
                "category": "Scenarios",
                "page": "150",
            },
        ]

        for ref_data in refs_data:
            ContentPageRef.objects.get_or_create(**ref_data)

        return ContentPageRef.objects.all()


@pytest.fixture(scope="session")
def content_page_refs_full(django_db_setup, django_db_blocker, content_page_refs):
    """Create full set of ContentPageRef objects (566) for tests that need them.

    Only use this fixture in tests that specifically require a large dataset.
    Most tests should use the basic content_page_refs fixture instead.
    """
    with django_db_blocker.unblock():
        core_book = ContentBook.objects.get(shortname="Core")

        # Create additional refs to reach the expected count (566)
        existing_count = ContentPageRef.objects.count()
        for i in range(existing_count, 566):
            ContentPageRef.objects.get_or_create(
                title=f"Test Ref {i}",
                book=core_book,
                category="Other",
                page=str(100 + i),
            )

        return ContentPageRef.objects.all()


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
def site():
    """Get the current site."""
    return Site.objects.get_current()


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
def make_content_skill():
    """Factory fixture to create ContentSkill objects."""
    from gyrinx.content.models import ContentSkill, ContentSkillCategory

    def make_content_skill_(name: str, category: str = "Combat", **kwargs):
        skill_category, _ = ContentSkillCategory.objects.get_or_create(name=category)
        skill, _ = ContentSkill.objects.get_or_create(
            name=name, category=skill_category, defaults=kwargs
        )
        return skill

    return make_content_skill_


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
    def make_list_(name, create_initial_action=True, **kwargs) -> List:
        kwargs = {
            "content_house": content_house,
            "owner": user,
            **kwargs,
        }
        lst = List.objects.create(name=name, **kwargs)

        # Create initial LIST_CREATE action so other actions can be created
        if create_initial_action:
            ListAction.objects.create(
                list=lst,
                action_type=ListActionType.CREATE,
                owner=user,
                applied=True,
            )

        return lst

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
def make_equipment(content_equipment_categories):
    """Make equipment fixture that ensures categories are available."""

    def make_equipment_(name, **kwargs) -> Callable[[str], ContentEquipment]:
        # If category is provided as a string, get or create the category
        if "category" in kwargs and isinstance(kwargs["category"], str):
            category_name = kwargs["category"]
            kwargs["category"], _ = ContentEquipmentCategory.objects.get_or_create(
                name=category_name,
                defaults={"group": "Weapons & Ammo"},  # Default group
            )
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
    return ContentHouse.objects.create(name="Test House", can_hire_any=True)


@pytest.fixture
def list_with_campaign(user, content_house, campaign, make_list) -> List:
    """A list in campaign mode with an associated campaign."""
    lst = make_list(
        "Test List",
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    campaign.lists.add(lst)
    return lst


@pytest.fixture
def make_weapon_with_accessory(content_equipment_categories):
    """Make a weapon with an accessory fixture."""

    def make_weapon_with_accessory_(
        cost=50, accessory_cost=25
    ) -> tuple[ContentEquipment, ContentWeaponAccessory]:
        from gyrinx.content.models import ContentEquipment, ContentWeaponAccessory

        weapon = ContentEquipment.objects.create(
            name="Test Weapon",
            cost=str(cost),  # cost is a CharField
            category=content_equipment_categories[0],
        )

        accessory = ContentWeaponAccessory.objects.create(
            name="Test Accessory",
            cost=accessory_cost,
        )
        # No need to link them - tests will add accessory to assignment

        return weapon, accessory

    return make_weapon_with_accessory_


@pytest.fixture
def make_weapon_with_profile(content_equipment_categories):
    """Make a weapon with a profile fixture."""

    def make_weapon_with_profile_(
        cost=50, profile_cost=30
    ) -> tuple[ContentEquipment, object]:
        from gyrinx.content.models import ContentEquipment, ContentWeaponProfile

        weapon = ContentEquipment.objects.create(
            name="Test Weapon",
            cost=str(cost),  # cost is a CharField
            category=content_equipment_categories[0],
        )

        profile = ContentWeaponProfile.objects.create(
            name="Test Profile",
            equipment=weapon,
            cost=profile_cost,
        )

        return weapon, profile

    return make_weapon_with_profile_


@pytest.fixture
def make_equipment_with_upgrades(content_equipment_categories):
    """Make equipment with upgrades fixture."""

    def make_equipment_with_upgrades_(
        cost=50, upgrade_cost=20
    ) -> tuple[ContentEquipment, object]:
        from gyrinx.content.models import ContentEquipment, ContentEquipmentUpgrade

        equipment = ContentEquipment.objects.create(
            name="Test Equipment",
            cost=str(cost),  # cost is a CharField
            category=content_equipment_categories[0],
        )

        upgrade = ContentEquipmentUpgrade.objects.create(
            name="Test Upgrade",
            cost=upgrade_cost,
            equipment=equipment,  # ContentEquipmentUpgrade has FK to ContentEquipment
        )

        return equipment, upgrade

    return make_equipment_with_upgrades_


@pytest.fixture
def make_vehicle_equipment(content_equipment_categories, content_house):
    """Make vehicle equipment with associated fighter profile."""

    def make_vehicle_equipment_(cost=200) -> tuple[ContentEquipment, ContentFighter]:
        from gyrinx.content.models import (
            ContentEquipment,
            ContentEquipmentFighterProfile,
            ContentFighter,
        )

        # Create vehicle equipment
        vehicle = ContentEquipment.objects.create(
            name="Test Vehicle",
            cost=str(cost),  # cost is a CharField
            category=content_equipment_categories[0],
        )

        # Create vehicle fighter profile
        vehicle_fighter = ContentFighter.objects.create(
            type="Vehicle",
            house=content_house,
            base_cost=cost,
        )

        # Link them via ContentEquipmentFighterProfile - this makes it a vehicle
        ContentEquipmentFighterProfile.objects.create(
            equipment=vehicle,
            content_fighter=vehicle_fighter,
        )

        return vehicle, vehicle_fighter

    return make_vehicle_equipment_


@pytest.fixture
def make_equipment_upgrade():
    """Make equipment upgrade fixture."""

    def make_equipment_upgrade_(equipment, name, cost):
        from gyrinx.content.models import ContentEquipmentUpgrade

        return ContentEquipmentUpgrade.objects.create(
            equipment=equipment, name=name, cost=cost
        )

    return make_equipment_upgrade_
