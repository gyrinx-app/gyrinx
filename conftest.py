from typing import Callable

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.sites.models import Site
from django.core.cache import cache, caches
from django.db.models.signals import post_migrate

from n23.content.models import (
    ContentBook,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentPageRef,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from n23.content.models.skill import ContentSkill, ContentSkillCategory
from gyrinx.site.models import BANNER_CACHE_KEY
from n23.core.models.action import ListAction, ListActionType
from n23.core.models.campaign import Campaign
from n23.core.models.list import List, ListFighter
from n23.core.models.pack import CustomContentPack, CustomContentPackItem
from n23.models import FighterCategoryChoices

# Re-export the local task-queue driver fixture so tests can request `task_queue`
# to drive the durable queue in manual mode (inject duplicates/failures/drops).
from gyrinx.tasks.testing import task_queue  # noqa: F401

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

    # Disable tracing in tests to avoid loading GCP dependencies
    # We need to reset tracing state because it was already initialized
    # during module import with settings_dev.py (which has TRACING_MODE="console")
    settings.TRACING_MODE = "off"

    # Reset and reinitialize tracing with the new setting
    from gyrinx import tracing

    tracing._reset_tracing()
    tracing._init_tracing()

    # Use faster password hasher for tests (MD5 instead of PBKDF2)
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]


@pytest.fixture(autouse=True)
def clear_content_page_ref_cache():
    """Empty the per-title page-ref cache before every test.

    ``ContentPageRef.find_similar`` caches one entry per title in a process-local
    ``LocMemCache``, and it sits in the fighter-card render path. Nothing else
    clears it — every other autouse fixture here is session-scoped — so its
    contents at test start depend on which tests ran earlier *in the same xdist
    worker*, and it keeps filling while a test runs.

    That makes query counts depend on worker history and on how many renders have
    already happened, which is what made the relative query-count tests in
    test_crew.py flaky on CI but not locally (#2114).

    Only this cache is cleared. The ``default`` cache deliberately holds
    ``BANNER_CACHE_KEY`` from ``django_test_settings`` so the banner query stays
    out of every test's count; clearing that here would put the query back.
    """
    caches["content_page_ref_cache"].clear()
    yield


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

        from n23.content.models import ContentMod, ContentModFighterStat

        ContentType.objects.get_for_model(ContentMod)
        ContentType.objects.get_for_model(ContentModFighterStat)


# Stats that every real environment is guaranteed to have, because data
# migrations create them: content.0148 seeds the stats that modifications
# classify, and content.0156 seeds the standard fighter statline. Tests run
# with --nomigrations, so data migrations never execute and the test database
# would otherwise have no ContentStat rows at all — mod formatting would then
# be driven by absent configuration rather than by the definitions production
# actually holds.
#
# field_name -> (short_name, full_name, inverted, inches, modifier, target)
CANONICAL_CONTENT_STATS = {
    # From content.0148 — the stats a modification classifies
    "accuracy_long": ("L", "Long Accuracy", False, False, True, False),
    "accuracy_short": ("S", "Short Accuracy", False, False, True, False),
    "ammo": ("Am", "Ammo", True, False, False, True),
    "armour_piercing": ("AP", "Armour Piercing", True, False, True, False),
    "ballistic_skill": ("BS", "Ballistic Skill", True, False, False, True),
    "cool": ("Cl", "Cool", True, False, False, True),
    "handling": ("Hnd", "Handling", True, False, False, True),
    "initiative": ("I", "Initiative", True, False, False, True),
    "intelligence": ("Int", "Intelligence", True, False, False, True),
    "leadership": ("Ld", "Leadership", True, False, False, True),
    "movement": ("M", "Movement", False, True, False, False),
    "range_long": ("L", "Long Range", False, True, False, False),
    "range_short": ("S", "Short Range", False, True, False, False),
    "save": ("Sv", "Save", True, False, False, True),
    "weapon_skill": ("WS", "Weapon Skill", True, False, False, True),
    "willpower": ("Wil", "Willpower", True, False, False, True),
    # Also from content.0156 — carry no classification flags
    "attacks": ("A", "Attacks", False, False, False, False),
    "strength": ("S", "Strength", False, False, False, False),
    "toughness": ("T", "Toughness", False, False, False, False),
    "wounds": ("W", "Wounds", False, False, False, False),
}


def _seed_content_stats(**kwargs):
    """Create or correct every canonical ContentStat row."""
    from n23.content.models.statline import ContentStat

    for field_name, (
        short_name,
        full_name,
        is_inverted,
        is_inches,
        is_modifier,
        is_target,
    ) in CANONICAL_CONTENT_STATS.items():
        ContentStat.objects.update_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
                "is_inverted": is_inverted,
                "is_inches": is_inches,
                "is_modifier": is_modifier,
                "is_target": is_target,
            },
        )


@pytest.fixture(scope="session", autouse=True)
def content_stat_definitions(django_db_setup, django_db_blocker):
    """Seed the ContentStat rows the data migrations guarantee.

    Stat classification (inverted / inches / modifier / target) is read from
    ContentStat when a modification is applied. Without these rows every stat
    would look unconfigured, so tests would exercise a code path that no real
    environment reaches. Tests needing stats beyond this set create their own.

    Seeding once per session is not enough: a transactional test truncates
    every table on teardown, which would leave the rest of that worker's
    transactional tests running against an empty table. Django re-emits
    post_migrate after that flush — the same hook that restores content types
    and permissions — so re-seed from there too.
    """
    with django_db_blocker.unblock():
        _seed_content_stats()

    post_migrate.connect(
        _seed_content_stats,
        sender=apps.get_app_config("content"),
        dispatch_uid="tests.seed_content_stats",
    )


#: The "Fighter" statline type content.0156 guarantees, in display order.
#: field_name -> (position, is_highlighted, is_first_of_group)
CANONICAL_FIGHTER_STATLINE = {
    "movement": (1, False, False),
    "weapon_skill": (2, False, False),
    "ballistic_skill": (3, False, False),
    "strength": (4, False, False),
    "toughness": (5, False, False),
    "wounds": (6, False, False),
    "initiative": (7, False, False),
    "attacks": (8, False, False),
    "leadership": (9, True, True),
    "cool": (10, True, False),
    "willpower": (11, True, False),
    "intelligence": (12, True, False),
}


def _seed_fighter_statline_type(**kwargs):
    """Create the standard "Fighter" statline type and its stats."""
    from n23.content.models.statline import (
        ContentStat,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )

    statline_type, _ = ContentStatlineType.objects.get_or_create(name="Fighter")
    for field_name, (
        position,
        highlighted,
        first_of_group,
    ) in CANONICAL_FIGHTER_STATLINE.items():
        stat = ContentStat.objects.filter(field_name=field_name).first()
        if stat is None:
            continue
        ContentStatlineTypeStat.objects.get_or_create(
            statline_type=statline_type,
            stat=stat,
            defaults={
                "position": position,
                "is_highlighted": highlighted,
                "is_first_of_group": first_of_group,
            },
        )


@pytest.fixture(scope="session", autouse=True)
def fighter_statline_type_definition(content_stat_definitions, django_db_blocker):
    """Seed the "Fighter" statline type the data migration guarantees.

    Every fighter type gets a statline on save, resolved from its category and
    falling back to "Fighter". Without this row that lookup fails, so no test
    fighter would have a statline at all — and the suite would be exercising
    an arrangement that no real environment has. Re-seeded from post_migrate
    for the same reason as the stat definitions: a transactional test
    truncates the table on teardown.
    """
    with django_db_blocker.unblock():
        _seed_fighter_statline_type()

    post_migrate.connect(
        _seed_fighter_statline_type,
        sender=apps.get_app_config("content"),
        dispatch_uid="tests.seed_fighter_statline_type",
    )


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
def make_content_skill() -> Callable[[str, str], ContentSkill]:
    """Factory fixture to create ContentSkill objects."""

    def make_content_skill_(
        name: str, category: str = "Combat", **kwargs
    ) -> ContentSkill:
        skill_category, _ = ContentSkillCategory.objects.get_or_create(name=category)
        skill, _ = ContentSkill.objects.get_or_create(
            name=name, category=skill_category, defaults=kwargs
        )
        return skill

    return make_content_skill_


@pytest.fixture
def make_content_skills_in_category() -> Callable[
    [list[str], str, dict, dict], tuple[list[ContentSkill], ContentSkillCategory]
]:
    """Factory fixture to create multiple ContentSkill objects in a given category.

    Accepts separate kwargs for category and skills.
    """

    def make_content_skills_in_category_(
        skill_names: list[str],
        category_name: str = "Combat",
        category_kwargs: dict = None,
        skill_kwargs: dict = None,
    ) -> tuple[list[ContentSkill], ContentSkillCategory]:
        category_kwargs = category_kwargs or {}
        skill_kwargs = skill_kwargs or {}
        skill_category, _ = ContentSkillCategory.objects.get_or_create(
            name=category_name, defaults=category_kwargs
        )
        skills = []
        for skill_name in skill_names:
            skill, _ = ContentSkill.objects.get_or_create(
                name=skill_name, category=skill_category, defaults=skill_kwargs
            )
            skills.append(skill)
        return skills, skill_category

    return make_content_skills_in_category_


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


#: The stats a materialised statline carries, in card order, and which of them
#: the card highlights / starts a group with. Mirrors what #1861 Track C1 built
#: for every template in production.
STATLINE_FIELDS = (
    "movement",
    "weapon_skill",
    "ballistic_skill",
    "strength",
    "toughness",
    "wounds",
    "initiative",
    "attacks",
    "leadership",
    "cool",
    "willpower",
    "intelligence",
)
_HIGHLIGHTED_STATS = {"leadership", "cool", "willpower", "intelligence"}


@pytest.fixture
def make_statline(content_stat_definitions) -> Callable[..., object]:
    """Give a ContentFighter a statline, mirroring what Track C1 produced.

    Every template in production has one, and stat overrides are rows keyed to
    a statline's stats — so a fighter without one cannot be overridden at all.
    Tests that exercise overrides need this.
    """
    from n23.content.models.statline import (
        ContentStat,
        ContentStatline,
        ContentStatlineStat,
        ContentStatlineType,
        ContentStatlineTypeStat,
    )

    def make_statline_(content_fighter, fields=STATLINE_FIELDS, name="Fighter"):
        # A fighter has at most one statline (OneToOne), so a second call --
        # or a call on a fixture that already has one -- would raise
        # IntegrityError rather than doing the obvious thing.
        existing = getattr(content_fighter, "custom_statline", None)
        if existing is not None:
            return existing

        statline_type, _ = ContentStatlineType.objects.get_or_create(name=name)
        statline = ContentStatline.objects.create(
            content_fighter=content_fighter, statline_type=statline_type
        )
        for position, field_name in enumerate(fields, start=1):
            type_stat, _ = ContentStatlineTypeStat.objects.get_or_create(
                statline_type=statline_type,
                stat=ContentStat.objects.get(field_name=field_name),
                defaults={
                    "position": position,
                    "is_highlighted": field_name in _HIGHLIGHTED_STATS,
                    "is_first_of_group": field_name == "leadership",
                },
            )
            ContentStatlineStat.objects.create(
                statline=statline,
                statline_type_stat=type_stat,
                value=getattr(content_fighter, field_name) or "-",
            )
        return statline

    return make_statline_


@pytest.fixture
def make_stat_override(user) -> Callable[..., object]:
    """Override one stat on a fighter, the way the stats form does."""
    from n23.core.models.list import ListFighterStatOverride

    def make_stat_override_(fighter, field_name, value, owner=None):
        statline = fighter.content_fighter.custom_statline
        type_stat = statline.statline_type.stats.get(stat__field_name=field_name)
        override, _ = ListFighterStatOverride.objects.update_or_create(
            list_fighter=fighter,
            content_stat=type_stat,
            # Un-archive: reviving a soft-deleted row would otherwise leave it
            # archived, so the override would not apply and the fixture would
            # quietly not do what it says.
            defaults={
                "value": value,
                "owner": owner or fighter.owner,
                "archived": False,
                "archived_at": None,
            },
        )
        # The statline is a cached_property; a caller that already touched it
        # would otherwise see the pre-override card.
        fighter.__dict__.pop("statline", None)
        return override

    return make_stat_override_


@pytest.fixture
def make_list(user, content_house: ContentHouse) -> Callable[..., List]:
    def make_list_(name, **kwargs) -> List:
        kwargs = {
            "content_house": content_house,
            "owner": user,
            **kwargs,
        }
        lst = List.objects.create_with_facts(name=name, **kwargs)

        # Bootstrap CREATE action, matching what handle_list_creation writes
        ListAction.objects.create(
            user=user,
            owner=user,
            list=lst,
            action_type=ListActionType.CREATE,
            description="List created",
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
        from n23.content.models import ContentEquipment, ContentWeaponAccessory

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
        from n23.content.models import ContentEquipment, ContentWeaponProfile

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
        from n23.content.models import ContentEquipment, ContentEquipmentUpgrade

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
        from n23.content.models import (
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
        from n23.content.models import ContentEquipmentUpgrade

        return ContentEquipmentUpgrade.objects.create(
            equipment=equipment, name=name, cost=cost
        )

    return make_equipment_upgrade_


@pytest.fixture
def stash_fighter_type(content_house, make_content_fighter):
    """Create a stash fighter type (ContentFighter with is_stash=True)."""
    return make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )


@pytest.fixture
def cc_user(user):
    """A user for content pack operations (group membership no longer required)."""
    return user


@pytest.fixture
def make_pack(user):
    """Factory fixture to create CustomContentPack objects."""

    def make_pack_(name="Test Pack", **kwargs):
        kwargs = {"owner": user, "listed": True, **kwargs}
        return CustomContentPack.objects.create(name=name, **kwargs)

    return make_pack_


@pytest.fixture
def pack(make_pack):
    """A listed content pack owned by cc_user."""
    return make_pack("Test Pack", summary="A test content pack")


@pytest.fixture
def pack_fighter(pack, content_house):
    """A fighter in a pack."""
    fighter = ContentFighter.objects.create(
        type="Pack Fighter",
        category=FighterCategoryChoices.GANGER,
        house=content_house,
        base_cost=50,
    )
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    return fighter


@pytest.fixture
def make_pack_fighter(make_pack, make_content_fighter, user):
    """Factory fixture to create a fighter that belongs to a content pack.

    Pack content is excluded by the default content manager but surfaced by
    ``all_content()`` (and so by the content admin inlines).
    """
    from django.contrib.contenttypes.models import ContentType

    def make_pack_fighter_(
        house,
        owner=None,
        type="Pack Fighter",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        **kwargs,
    ):
        owner = owner or user
        fighter = make_content_fighter(
            type=type,
            category=category,
            house=house,
            base_cost=base_cost,
            **kwargs,
        )
        pack = make_pack(name="Test Pack", owner=owner)
        CustomContentPackItem.objects.create(
            pack=pack,
            content_type=ContentType.objects.get_for_model(ContentFighter),
            object_id=fighter.pk,
            owner=pack.owner,
        )
        return fighter

    return make_pack_fighter_


@pytest.fixture
def pack_rule(pack, cc_user):
    """A rule in a pack."""
    from n23.content.models import ContentRule

    rule = ContentRule.objects.create(
        name="Pack Rule",
        description="A custom rule from a pack",
    )
    from django.contrib.contenttypes.models import ContentType

    ct = ContentType.objects.get_for_model(ContentRule)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=rule.pk,
        owner=cc_user,
    )
    return rule


@pytest.fixture
def default_promotions(db):
    """Seed the default promotion paths (Ganger→Specialist, Specialist→Champion).

    The test DB is built with --nomigrations, so the data migration that seeds these in
    real deployments never runs; tests that exercise the data-driven promotion flow seed
    them explicitly with this fixture. Returns paths keyed by (from_category, to_category).
    """
    from n23.content.models import ContentPromotionPath
    from n23.content.models.promotion import seed_default_promotions

    seed_default_promotions(ContentPromotionPath)
    return {
        (p.from_category, p.to_category): p for p in ContentPromotionPath.objects.all()
    }


@pytest.fixture
def leader_nomination_path(db):
    """Seed the generic 'Nominate as leader' path (any category, dynamic Leader targets).

    Like default_promotions, this exists because the test DB is built with
    --nomigrations, so the deployment seed (0187) never runs in tests.
    """
    from n23.content.models import ContentPromotionPath
    from n23.content.models.promotion import seed_leader_nomination

    return seed_leader_nomination(ContentPromotionPath)
