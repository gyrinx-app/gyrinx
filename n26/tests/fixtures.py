import pytest

from n26.library.models import (
    ContentPack,
    GangType,
    Profile,
    ProfileType,
    Stat,
    Statline,
    StatlineStat,
    StatlineType,
    StatlineTypeStat,
    get_default_pack,
)
from n26.library.standard_content import MODEL_CHARACTERISTICS, MODEL_STATLINE


@pytest.fixture
def owner(db):
    """A player to own the gangs a test founds."""
    from django.contrib.auth.models import User

    return User.objects.create_user("player")


@pytest.fixture
def default_pack(db):
    """The N26 pack."""
    return get_default_pack()


@pytest.fixture
def homebrew(db):
    return ContentPack.objects.create(name="Homebrew", slug="homebrew")


@pytest.fixture
def other_pack(db):
    return ContentPack.objects.create(name="Other", slug="other")


@pytest.fixture
def make_stat(db):
    def _make(short_name, full_name, **kwargs):
        return Stat.objects.create(short_name=short_name, full_name=full_name, **kwargs)

    return _make


@pytest.fixture
def person_statline_type(make_stat):
    """A small three-stat statline, exercising each display rule.

    ``M`` is a distance, ``WS`` a roll target, ``T`` a plain number.
    """
    statline_type = StatlineType.objects.create(name="Person")
    definitions = [
        ("M", "Movement", {"is_inches": True}),
        ("WS", "Weapon Skill", {"is_target": True, "is_inverted": True}),
        ("T", "Toughness", {}),
    ]
    for position, (short_name, full_name, flags) in enumerate(definitions):
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=make_stat(short_name, full_name, **flags),
            position=position,
        )
    return statline_type


@pytest.fixture
def person_type(person_statline_type):
    """A Fighter carrying the small three-stat shape.

    The Type is Fighter because that is one of the only two there are;
    what varies between this and ``fighter_type`` is the statline, not
    the Type. A test wants one or the other, never both.
    """
    return ProfileType.objects.create(
        name="Fighter", statline_type=person_statline_type
    )


@pytest.fixture
def gang_type(db):
    return GangType.objects.create(name="Escher")


@pytest.fixture
def campaign_type(default_pack):
    """A bare campaign type in the system pack, for a campaign to be
    founded on. Nothing built in: a suite that wants the Territory campaign shape —
    Reputation at 0, a Settlement — seeds it with ``seed_core_campaign``."""
    from n26.library.authoring import create_campaign_type

    return create_campaign_type("Territory campaign")


#: The fixtures build exactly what the Foundations page creates — one
#: definition, so a suite can never stand on a shape the app cannot
#: produce.
FIGHTER_STAT_DEFINITIONS = MODEL_CHARACTERISTICS


@pytest.fixture
def fighter_stats(make_stat):
    """The thirteen real characteristics, keyed by short name.

    Stat definitions are shared across statline types by design — a
    weapon's Strength is the fighter's Strength — so an existing
    definition is reused rather than redefined.
    """
    made = {}
    for short, full, flags, _ in FIGHTER_STAT_DEFINITIONS:
        made[short] = Stat.objects.filter(full_name=full).first() or make_stat(
            short, full, **flags
        )
    return made


@pytest.fixture
def fighter_statline_type(fighter_stats):
    statline_type = StatlineType.objects.create(name=MODEL_STATLINE)
    for position, (short, _, _, display) in enumerate(FIGHTER_STAT_DEFINITIONS):
        StatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=fighter_stats[short],
            position=position,
            **display,
        )
    return statline_type


@pytest.fixture
def fighter_type(fighter_statline_type):
    return ProfileType.objects.create(
        name="Fighter", statline_type=fighter_statline_type
    )


@pytest.fixture
def vehicle_type(fighter_statline_type):
    """Vehicles use the same characteristics profile — only the Type
    line differs (core rules)."""
    return ProfileType.objects.create(
        name="Vehicle",
        statline_type=fighter_statline_type,
    )


@pytest.fixture
def make_profile(person_type, gang_type):
    """Create a Profile, defaulting to the Person type, Escher, and N26."""

    def _make(name, **kwargs):
        kwargs.setdefault("profile_type", person_type)
        kwargs.setdefault("gang_type", gang_type)
        return Profile.objects.create(name=name, **kwargs)

    return _make


@pytest.fixture
def make_statline(db):
    """Attach a statline to a profile, given values keyed by field name."""

    def _make(profile, **values):
        statline = Statline.objects.create(profile=profile)
        for type_stat in profile.statline_type.stats.all():
            if type_stat.field_name in values:
                StatlineStat.objects.create(
                    statline=statline,
                    statline_type_stat=type_stat,
                    value=str(values[type_stat.field_name]),
                )
        return statline

    return _make


@pytest.fixture
def own_storage(settings, tmp_path):
    """Point the site's storage at a directory this test owns.

    Uploads go to whatever storage is configured, which outside a test is a
    bucket and inside one is a directory under the checkout. A test that
    wrote there would leave files behind and see another test's. The address
    they are published at is pinned too, so what a test asserts about one
    does not depend on how the machine running it is configured.
    """
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    return tmp_path


@pytest.fixture
def store_artwork(own_storage):
    """Put a drawing in the site's storage and return its address —
    the shape a gang type's ``icon_url`` holds."""
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage

    def _store(source, name="badge.svg"):
        key = default_storage.save(
            f"gang-type-icons/{name}", ContentFile(source.encode())
        )
        return default_storage.url(key)

    return _store


@pytest.fixture
def names():
    """Pull the ``name`` column off a queryset, for readable assertions."""

    def _names(queryset):
        return sorted(queryset.values_list("name", flat=True))

    return _names
