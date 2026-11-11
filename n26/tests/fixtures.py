import json
from functools import wraps

import pytest
from bs4 import BeautifulSoup
from django.db import transaction

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
from n26.write_pause import write_guard


def library_setup(builder):
    """Build fixture content within one admitted transaction. Nested authoring verbs retain
    savepoints and reuse admission; release the scope before the test runs.
    """

    @wraps(builder)
    def build(*args, **kwargs):
        with transaction.atomic(), write_guard():
            return builder(*args, **kwargs)

    return build


@pytest.fixture
def counter_tracking(db):
    """Create an activated counter-tracking checkpoint."""
    from uuid import uuid4

    from django.utils import timezone

    from n26.core.models import CounterTracking

    return CounterTracking.objects.create(
        activated_at=timezone.now(), activation_run=uuid4()
    )


@pytest.fixture
def owner(db):

    from django.contrib.auth.models import User

    return User.objects.create_user("player")


@pytest.fixture
def default_pack(db):

    return get_default_pack()


@pytest.fixture
def homebrew(db):
    return ContentPack.objects.create(name="Homebrew", slug="homebrew")


@pytest.fixture
def other_pack(db):
    return ContentPack.objects.create(name="Other", slug="other")


@pytest.fixture
def make_stat(default_pack):
    def _make(short_name, full_name, **kwargs):
        if "pack" not in kwargs and "pack_id" not in kwargs:
            kwargs["pack_id"] = default_pack.pk
        return Stat.objects.create(short_name=short_name, full_name=full_name, **kwargs)

    return _make


@pytest.fixture
def person_statline_type(make_stat, default_pack):
    """Use three characteristics to cover distance, roll-target and plain-number display
    rules.
    """
    statline_type = StatlineType.objects.create(name="Person", pack_id=default_pack.pk)
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
            pack_id=default_pack.pk,
        )
    return statline_type


@pytest.fixture
def person_type(person_statline_type):
    """Fighter profile type with the three-characteristic statline. Use either this fixture
    or fighter_type in a test because both create a Fighter type.
    """
    return ProfileType.objects.create(
        name="Fighter",
        statline_type=person_statline_type,
        pack_id=person_statline_type.pack_id,
    )


@pytest.fixture
def gang_type(default_pack):
    return GangType.objects.create(name="Escher", pack_id=default_pack.pk)


@pytest.fixture
def campaign_type(default_pack):
    """Create a campaign type without built-ins. Tests needing the standard Territory
    campaign grants must call seed_core_campaign.
    """
    from n26.library.authoring import create_campaign_type

    return create_campaign_type("Territory campaign")


#: Share the Foundations characteristic definitions so fixtures match the content the app
#: creates.
FIGHTER_STAT_DEFINITIONS = MODEL_CHARACTERISTICS


@pytest.fixture
def fighter_stats(default_pack):
    """Reuse standard characteristic definitions by full name because multiple statline
    types can share them, including fighter and weapon Strength.
    """
    existing = {}
    for stat in Stat.objects.filter(
        full_name__in=[full for _, full, _, _ in FIGHTER_STAT_DEFINITIONS]
    ):
        existing.setdefault(stat.full_name, stat)
    missing = []
    made = {}
    for short, full, flags, _ in FIGHTER_STAT_DEFINITIONS:
        stat = existing.get(full)
        if stat is None:
            stat = Stat(
                short_name=short,
                full_name=full,
                field_name=Stat.derive_field_name(full),
                pack_id=default_pack.pk,
                **flags,
            )
            missing.append(stat)
        made[short] = stat
    Stat.objects.bulk_create(missing)
    return made


@pytest.fixture
def fighter_statline_type(fighter_stats, default_pack):
    statline_type = StatlineType.objects.create(
        name=MODEL_STATLINE, pack_id=default_pack.pk
    )
    StatlineTypeStat.objects.bulk_create(
        [
            StatlineTypeStat(
                statline_type=statline_type,
                stat=fighter_stats[short],
                position=position,
                pack_id=default_pack.pk,
                **display,
            )
            for position, (short, _, _, display) in enumerate(FIGHTER_STAT_DEFINITIONS)
        ]
    )
    return statline_type


@pytest.fixture
def fighter_type(fighter_statline_type):
    return ProfileType.objects.create(
        name="Fighter",
        statline_type=fighter_statline_type,
        pack_id=fighter_statline_type.pack_id,
    )


@pytest.fixture
def vehicle_type(fighter_statline_type):
    """Use the standard model characteristics with a Vehicle profile-type label."""
    return ProfileType.objects.create(
        name="Vehicle",
        statline_type=fighter_statline_type,
        pack_id=fighter_statline_type.pack_id,
    )


@pytest.fixture
def make_profile(person_type, gang_type):
    """Create a Profile, defaulting to the three-characteristic Fighter type, Escher gang
    type and default N26 pack.
    """

    def _make(name, **kwargs):
        kwargs.setdefault("profile_type", person_type)
        kwargs.setdefault("gang_type", gang_type)
        if "pack" not in kwargs and "pack_id" not in kwargs:
            kwargs["pack_id"] = person_type.pack_id
        return Profile.objects.create(name=name, **kwargs)

    return _make


@pytest.fixture
def make_statline(default_pack):
    """Attach a statline to a profile, given values keyed by field name."""

    def _make(profile, **values):
        statline = Statline.objects.create(profile=profile, pack_id=default_pack.pk)
        stats = []
        for type_stat in profile.statline_type.stats.select_related("stat"):
            if type_stat.field_name in values:
                value = str(values[type_stat.field_name])
                # Match StatlineStat.save(), including leaving stored blanks blank.
                if value:
                    value = type_stat.stat.format_value(value)
                stats.append(
                    StatlineStat(
                        statline=statline,
                        statline_type_stat=type_stat,
                        value=value,
                        pack_id=default_pack.pk,
                    )
                )
        StatlineStat.objects.bulk_create(stats)
        return statline

    return _make


@pytest.fixture
def own_storage(settings, tmp_path):
    """Isolate uploaded files in this test's temporary directory and fix their public base
    URL. Tests must not leave uploads in checkout storage or depend on machine-specific
    media settings.
    """
    settings.MEDIA_ROOT = tmp_path
    settings.MEDIA_URL = "/media/"
    return tmp_path


@pytest.fixture
def store_artwork(own_storage):
    """Store SVG artwork and return the public URL accepted by GangType.icon_url."""
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

    def _names(queryset):
        return sorted(queryset.values_list("name", flat=True))

    return _names


def island_props(body, name):
    soup = BeautifulSoup(body, "html.parser")
    host = soup.select_one(f'[data-react-name="{name}"]')
    assert host is not None
    return json.loads(soup.find(id=host["data-react-props"]).string)


@pytest.fixture
def scenario_content(db):
    """The original editable scenario catalogue, normally installed by migration."""
    from importlib import import_module

    from django.apps import apps

    migration = import_module(
        "n26.library.migrations.0130_scenario_content_is_author_editable"
    )
    migration.seed(apps)


@pytest.fixture
def past_cycle_context(campaign_type):
    """Put a gang in Takeover and return an explicit Occupation context."""
    from datetime import date
    from uuid import uuid4

    from gyrinx.site.models import Availability, FeatureFlag
    from n26.core import cycles, schedule
    from n26.core.cycle_context import CycleContext
    from n26.core.cycle_data import template_data
    from n26.core.models import Campaign, CampaignScheduleTemplate
    from n26.flags import CYCLE_TRACKING
    from n26.tests.sandbox.actions import found_campaign, join_campaign

    def attach(gang):
        FeatureFlag.objects.update_or_create(
            slug=CYCLE_TRACKING,
            defaults={"name": "Campaign cycles", "availability": Availability.EVERYONE},
        )
        campaign = found_campaign(
            "Historical action cycles",
            campaign_type,
            owner=gang.owner,
            status=Campaign.Status.IN_PROGRESS,
        )
        join_campaign(gang, campaign)
        template = CampaignScheduleTemplate.objects.create(
            name=schedule.DEFAULT_TEMPLATE.name,
            definition=template_data(schedule.DEFAULT_TEMPLATE),
        )
        cycles.configure(
            campaign,
            actor=gang.owner,
            template_id=template.pk,
            current_position=4,
            mode="fixed",
            request_key=uuid4(),
            calendar=schedule.CycleCalendar(date(2026, 11, 1)),
        )
        state = cycles.load(campaign)
        assert state.current_phase.details.name == "Takeover"
        return CycleContext(str(campaign.pk), state.cycles[0].id)

    return attach


@pytest.fixture
def cycle_tracking_switch(db):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.flags import CYCLE_TRACKING

    def set_open(opened):
        assert (
            FeatureFlag.objects.filter(slug=CYCLE_TRACKING).update(
                availability=Availability.EVERYONE if opened else Availability.OFF
            )
            == 1
        )

    return set_open


@pytest.fixture
def opened_cycle_tracking(db):
    from gyrinx.site.models import Availability, FeatureFlag
    from n26.flags import CYCLE_TRACKING

    flag, _ = FeatureFlag.objects.update_or_create(
        slug=CYCLE_TRACKING,
        defaults={"name": "Campaign cycles", "availability": Availability.EVERYONE},
    )
    return flag
