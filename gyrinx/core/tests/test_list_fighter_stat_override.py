"""
Tests for ListFighterStatOverride model and stat editing functionality.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from gyrinx.core.models import List, ListFighter, ListFighterStatOverride

User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def house(db):
    """Create a test house."""
    return ContentHouse.objects.create(name="Test House", generic=False)


@pytest.fixture
def content_fighter(db, house):
    """Create a test content fighter."""
    return ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="leader",
        base_cost=100,
        movement='5"',
        weapon_skill="3+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="7",
        cool="6+",
        willpower="6+",
        intelligence="7+",
    )


@pytest.fixture
def list_obj(db, user, house):
    """Create a test list."""
    return List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )


@pytest.fixture
def list_fighter(db, list_obj, content_fighter, user):
    """Create a test list fighter."""
    return ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=list_obj,
        owner=user,
    )


@pytest.fixture
def vehicle_statline_type(db):
    """Create a vehicle statline type."""
    return ContentStatlineType.objects.create(
        name="Vehicle",
    )


@pytest.fixture
def vehicle_stats(db, vehicle_statline_type):
    """Create vehicle stat definitions."""
    stats = []
    stat_data = [
        ("movement", "M", "Movement", 0, False, False),
        ("front_toughness", "Fr", "Front Toughness", 1, False, False),
        ("side_toughness", "Sd", "Side Toughness", 2, False, False),
        ("rear_toughness", "Rr", "Rear Toughness", 3, False, False),
        ("hit_points", "HP", "Hit Points", 4, False, False),
        ("handling", "Hnd", "Handling", 5, True, True),
        ("cool", "Cl", "Cool", 6, True, False),
        ("speed", "Spd", "Speed", 7, True, False),
    ]

    for (
        field_name,
        short_name,
        full_name,
        position,
        is_highlighted,
        is_first_of_group,
    ) in stat_data:
        # Create or get the stat definition
        stat_def, _ = ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
            },
        )

        # Create the statline type stat
        stat = ContentStatlineTypeStat.objects.create(
            statline_type=vehicle_statline_type,
            stat=stat_def,
            position=position,
            is_highlighted=is_highlighted,
            is_first_of_group=is_first_of_group,
        )
        stats.append(stat)

    return stats


@pytest.fixture
def vehicle_statline(db, content_fighter, vehicle_statline_type, vehicle_stats):
    """Create a vehicle statline for the content fighter."""
    statline = ContentStatline.objects.create(
        content_fighter=content_fighter,
        statline_type=vehicle_statline_type,
    )

    # Add stat values
    stat_values = ['8"', "6", "5", "4", "3", "4+", "6+", "Slow"]
    for stat_def, value in zip(vehicle_stats, stat_values):
        ContentStatlineStat.objects.create(
            statline=statline,
            statline_type_stat=stat_def,
            value=value,
        )

    return statline


@pytest.mark.django_db
def test_list_fighter_stat_override_creation(list_fighter, vehicle_stats, user):
    """Test creating a ListFighterStatOverride."""
    stat_override = ListFighterStatOverride.objects.create(
        list_fighter=list_fighter,
        content_stat=vehicle_stats[0],  # Movement
        value='10"',
        owner=user,
    )

    assert stat_override.list_fighter == list_fighter
    assert stat_override.content_stat == vehicle_stats[0]
    assert stat_override.value == '10"'
    assert str(stat_override) == 'Test Fighter - M: 10"'


@pytest.mark.django_db
def test_list_fighter_statline_with_custom_statline(list_fighter, vehicle_statline):
    """Test that ListFighter.statline() uses custom statline when available."""
    statline = list_fighter.statline

    # Should have vehicle stats, not standard fighter stats
    assert len(statline) == 8  # Vehicle has 8 stats
    assert statline[0].name == "M"
    assert statline[0].value == '8"'
    assert statline[1].name == "Fr"
    assert statline[1].value == "6"


@pytest.mark.django_db
def test_list_fighter_statline_with_overrides(
    list_fighter, vehicle_statline, vehicle_stats, user
):
    """Test that ListFighter.statline() uses stat overrides."""
    # Create overrides
    ListFighterStatOverride.objects.create(
        list_fighter=list_fighter,
        content_stat=vehicle_stats[0],  # Movement
        value='12"',
        owner=user,
    )
    ListFighterStatOverride.objects.create(
        list_fighter=list_fighter,
        content_stat=vehicle_stats[4],  # Hit Points
        value="5",
        owner=user,
    )

    # Clear cached property
    if hasattr(list_fighter, "statline"):
        del list_fighter.__dict__["statline"]

    statline = list_fighter.statline

    # Check overridden values
    assert statline[0].value == '12"'  # Movement overridden
    assert statline[0].modded
    assert statline[4].value == "5"  # Hit Points overridden
    assert statline[4].modded

    # Check non-overridden values
    assert statline[1].value == "6"  # Front Toughness not overridden
    assert not statline[1].modded


@pytest.mark.django_db
def test_list_fighter_statline_legacy_overrides(list_fighter):
    """Test that ListFighter.statline() still works with legacy overrides."""
    # Set legacy overrides
    list_fighter.movement_override = '6"'
    list_fighter.weapon_skill_override = "2+"
    list_fighter.save()

    # Clear cached property
    if hasattr(list_fighter, "statline"):
        del list_fighter.__dict__["statline"]

    statline = list_fighter.statline

    # Should use legacy stats (12 standard fighter stats)
    assert len(statline) == 12

    # Check overridden values
    movement_stat = next(s for s in statline if s.field_name == "movement")
    assert movement_stat.value == '6"'
    assert movement_stat.modded

    ws_stat = next(s for s in statline if s.field_name == "weapon_skill")
    assert ws_stat.value == "2+"
    assert ws_stat.modded


@pytest.mark.django_db
def test_stat_override_unique_constraint(list_fighter, vehicle_stats, user):
    """Test that only one override per stat per fighter is allowed."""
    # Create first override
    ListFighterStatOverride.objects.create(
        list_fighter=list_fighter,
        content_stat=vehicle_stats[0],
        value='10"',
        owner=user,
    )

    # Try to create duplicate - should fail
    with pytest.raises(Exception):  # Will be IntegrityError
        ListFighterStatOverride.objects.create(
            list_fighter=list_fighter,
            content_stat=vehicle_stats[0],
            value='12"',
            owner=user,
        )


@pytest.mark.django_db
def test_edit_fighter_stats_view_get(client, list_fighter, user):
    """Test GET request to edit fighter stats view."""
    client.force_login(user)
    url = reverse(
        "core:list-fighter-stats-edit", args=[list_fighter.list.id, list_fighter.id]
    )

    response = client.get(url)
    assert response.status_code == 200
    assert "form" in response.context
    assert response.context["fighter"] == list_fighter
    assert response.context["list"] == list_fighter.list


@pytest.mark.django_db
def test_edit_fighter_stats_view_post_legacy(client, list_fighter, user):
    """Test POST request to edit fighter stats with legacy overrides."""
    client.force_login(user)
    url = reverse(
        "core:list-fighter-stats-edit", args=[list_fighter.list.id, list_fighter.id]
    )

    data = {
        "movement_override": '6"',
        "weapon_skill_override": "2+",
        "ballistic_skill_override": "",  # Empty should clear override
    }

    response = client.post(url, data)
    assert response.status_code == 302  # Redirect after success

    # Refresh from DB
    list_fighter.refresh_from_db()
    assert list_fighter.movement_override == '6"'
    assert list_fighter.weapon_skill_override == "2+"
    assert list_fighter.ballistic_skill_override is None


@pytest.mark.django_db
def test_edit_fighter_stats_view_post_custom_statline(
    client, list_fighter, vehicle_statline, vehicle_stats, user
):
    """Test POST request to edit fighter stats with custom statline."""
    client.force_login(user)
    url = reverse(
        "core:list-fighter-stats-edit", args=[list_fighter.list.id, list_fighter.id]
    )

    data = {
        f"stat_{vehicle_stats[0].id}": '12"',  # Movement
        f"stat_{vehicle_stats[4].id}": "5",  # Hit Points
        f"stat_{vehicle_stats[1].id}": "",  # Front Toughness - empty
    }

    response = client.post(url, data)
    assert response.status_code == 302  # Redirect after success

    # Check overrides were created
    overrides = ListFighterStatOverride.objects.filter(list_fighter=list_fighter)
    assert overrides.count() == 2

    movement_override = overrides.get(content_stat=vehicle_stats[0])
    assert movement_override.value == '12"'

    hp_override = overrides.get(content_stat=vehicle_stats[4])
    assert hp_override.value == "5"


@pytest.mark.django_db
def test_edit_fighter_stats_form_initialization_with_overrides(
    list_fighter, vehicle_statline, vehicle_stats, user
):
    """Test that the form is initialized with existing overrides."""
    from gyrinx.core.forms.list import EditListFighterStatsForm

    # Create some existing overrides
    ListFighterStatOverride.objects.create(
        list_fighter=list_fighter,
        content_stat=vehicle_stats[0],
        value='10"',
        owner=user,
    )

    form = EditListFighterStatsForm(fighter=list_fighter)

    # Check that the form has the right fields
    assert form.has_custom_statline
    assert f"stat_{vehicle_stats[0].id}" in form.fields

    # Check initial value
    assert form.fields[f"stat_{vehicle_stats[0].id}"].initial == '10"'


@pytest.mark.django_db
def test_statline_annotation_with_legacy_statline(list_obj):
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=list_obj.content_house,
        category="GANGER",
        movement="1",
        weapon_skill="1",
        ballistic_skill="1",
        strength="1",
        toughness="1",
        wounds="1",
        initiative="1",
        attacks="1",
        leadership="1",
        cool="1",
        willpower="1",
        intelligence="1",
    )

    # Make a ListFighter from the ContentFighter
    lf = ListFighter.objects.create(
        content_fighter=fighter,
        list=list_obj,
    )

    # ... then refetch with all related data
    lf = ListFighter.objects.with_related_data().get(id=lf.id)

    assert lf.annotated_content_fighter_statline is None


@pytest.mark.django_db
def test_statline_annotation_with_custom_statline(list_obj):
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=list_obj.content_house,
        category="GANGER",  # Add required category
    )

    # Create statline type with stats
    statline_type = ContentStatlineType.objects.create(name="Test Type")

    # Create stat definitions
    stat1_def = ContentStat.objects.create(
        field_name="stat1",
        short_name="S1",
        full_name="Stat 1",
    )

    stat2_def = ContentStat.objects.create(
        field_name="stat2",
        short_name="S2",
        full_name="Stat 2",
    )

    # Create statline type stats
    s1 = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat1_def,
        position=1,
    )

    s2 = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat2_def,
        position=2,
    )

    # Create statline without all required stats
    statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=statline_type,
    )

    # Add some values
    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=s1,
        value="1",
    )

    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=s2,
        value="2",
    )

    # Make a ListFighter from the ContentFighter
    lf = ListFighter.objects.create(
        content_fighter=fighter,
        list=list_obj,
    )

    # ... then refetch with all related data
    lf = ListFighter.objects.with_related_data().get(id=lf.id)

    assert lf.annotated_content_fighter_statline == [
        {
            "field_name": "stat1",
            "name": "S1",
            "value": "1",
            "highlight": False,
            "first_of_group": False,
        },
        {
            "field_name": "stat2",
            "name": "S2",
            "value": "2",
            "highlight": False,
            "first_of_group": False,
        },
    ]


@pytest.mark.django_db
def test_statline_override_annotation_with_custom_statline(list_obj):
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=list_obj.content_house,
        category="GANGER",  # Add required category
    )

    # Create statline type with stats
    statline_type = ContentStatlineType.objects.create(name="Test Type")

    # Create stat definitions
    stat1_def = ContentStat.objects.create(
        field_name="stat1",
        short_name="S1",
        full_name="Stat 1",
    )

    stat2_def = ContentStat.objects.create(
        field_name="stat2",
        short_name="S2",
        full_name="Stat 2",
    )

    # Create statline type stats
    s1 = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat1_def,
        position=1,
    )

    s2 = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat2_def,
        position=2,
    )

    # Create statline without all required stats
    statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=statline_type,
    )

    # Add some values
    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=s1,
        value="1",
    )

    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=s2,
        value="2",
    )

    # Make a ListFighter from the ContentFighter
    lf = ListFighter.objects.create(
        content_fighter=fighter,
        list=list_obj,
    )

    # And override the stat
    ListFighterStatOverride.objects.create(
        list_fighter=lf,
        content_stat=s1,
        value="3",
    )

    # ... then refetch with all related data
    lf = ListFighter.objects.with_related_data().get(id=lf.id)

    assert lf.annotated_stat_overrides == [
        {
            "field_name": "stat1",
            "value": "3",
        },
    ]
