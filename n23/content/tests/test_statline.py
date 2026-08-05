import pytest
from django.core.exceptions import ValidationError

from n23.content.models import (
    ContentFighter,
    ContentHouse,
    ContentStat,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from n23.content.statlines import set_fighter_statline


@pytest.mark.django_db
def test_content_statline_stat_model():
    """Test the ContentStatlineStat model functionality."""
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="LEADER",  # Add required category
    )

    # Create statline type
    statline_type = ContentStatlineType.objects.create(name="Vehicle")

    # Create stat definitions
    movement_stat_def, _ = ContentStat.objects.get_or_create(
        field_name="movement",
        short_name="M",
        full_name="Movement",
    )

    front_stat_def, _ = ContentStat.objects.get_or_create(
        field_name="front",
        short_name="Fr",
        full_name="Front",
    )

    # Create statline type stats linking to stat definitions
    movement_stat = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=movement_stat_def,
        position=1,
    )

    front_stat = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=front_stat_def,
        position=2,
    )

    # Saving the fighter already gave it a default statline, so move it onto
    # this type and set the values in one go.
    statline = set_fighter_statline(
        fighter,
        statline_type,
        {movement_stat.id: '8"', front_stat.id: "12"},
    )
    movement_value = statline.stats.get(statline_type_stat=movement_stat)

    # Test relationships
    assert statline.stats.count() == 2
    assert movement_value.statline == statline
    assert movement_value.statline_type_stat == movement_stat
    assert movement_value.value == '8"'

    # Test string representation
    assert str(movement_value) == 'M: 8"'
    assert str(statline) == "Test House Test Fighter (Leader) - Vehicle Statline"

    # Test unique together constraint
    with pytest.raises(Exception):  # IntegrityError
        ContentStatlineStat.objects.create(
            statline=statline,
            statline_type_stat=movement_stat,
            value='10"',
        )


@pytest.mark.django_db
def test_content_fighter_statline_method():
    """Test that ContentFighter.statline() works with the new model structure."""
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Vehicle",
        house=house,
        category="CREW",  # Add required category
        movement=0,  # Default values for legacy fields
        weapon_skill=0,
        ballistic_skill=0,
        strength=0,
        toughness=0,
        wounds=0,
        initiative=0,
        attacks=0,
        leadership=0,
        cool=0,
        willpower=0,
        intelligence=0,
    )

    # Create vehicle statline type
    vehicle_type = ContentStatlineType.objects.create(name="Vehicle")

    # Create stats for vehicle
    stats_data = [
        ("movement", "M", "Movement", 1, False, False),
        ("front", "Fr", "Front", 2, False, False),
        ("side", "Sd", "Side", 3, False, False),
        ("rear", "Rr", "Rear", 4, False, False),
        ("hit_points", "HP", "Hit Points", 5, False, True),
        ("handling", "Hnd", "Handling", 6, True, False),
        ("crew", "Sv", "Crew", 7, True, False),
    ]

    type_stats = []
    for (
        field_name,
        short_name,
        full_name,
        position,
        highlight,
        first_of_group,
    ) in stats_data:
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
            statline_type=vehicle_type,
            stat=stat_def,
            position=position,
            is_highlighted=highlight,
            is_first_of_group=first_of_group,
        )
        type_stats.append(stat)

    # Move the fighter's statline onto the vehicle type, with these values
    stat_values = ['8"', "12", "10", "9", "3", "6+", "5+"]
    set_fighter_statline(
        fighter,
        vehicle_type,
        {stat.id: value for stat, value in zip(type_stats, stat_values)},
    )

    # Test the statline method
    statline = fighter.statline()

    assert len(statline) == 7
    assert statline[0]["name"] == "M"
    assert statline[0]["value"] == '8"'
    assert statline[0]["highlight"] is False

    assert statline[4]["name"] == "HP"
    assert statline[4]["value"] == "3"
    assert statline[4]["first_of_group"] is True

    assert statline[5]["name"] == "Hnd"
    assert statline[5]["value"] == "6+"
    assert statline[5]["highlight"] is True


@pytest.mark.django_db
def test_statline_validation():
    """Test ContentStatline validation for missing stats."""
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
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
    ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat1_def,
        position=1,
    )

    ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat2_def,
        position=2,
    )

    # A statline missing one of its type's stats. The normal write path always
    # fills the whole set, so drop a row deliberately to get there — this is
    # the shape clean() exists to catch, however it arose.
    statline = set_fighter_statline(
        fighter, statline_type, {statline_type.stats.first().id: "10"}
    )
    statline.stats.exclude(statline_type_stat=statline_type.stats.first()).delete()

    # Validation should fail because stat2 is missing
    with pytest.raises(ValidationError) as exc_info:
        statline.clean()

    assert "Missing required stats: stat2" in str(exc_info.value)
