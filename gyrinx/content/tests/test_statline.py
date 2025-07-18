import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)


@pytest.mark.django_db
def test_content_statline_stat_model():
    """Test the ContentStatlineStat model functionality."""
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter", 
        house=house,
        category="LEADER"  # Add required category
    )
    
    # Create statline type
    statline_type = ContentStatlineType.objects.create(name="Vehicle")
    
    # Create statline type stats
    movement_stat = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        field_name="movement",
        short_name="M",
        full_name="Movement",
        position=1,
    )
    
    front_stat = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        field_name="front",
        short_name="Fr",
        full_name="Front",
        position=2,
    )
    
    # Create statline
    statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=statline_type,
    )
    
    # Create stat values
    movement_value = ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=movement_stat,
        value='8"',
    )
    
    front_value = ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=front_stat,
        value="12",
    )
    
    # Test relationships
    assert statline.stats.count() == 2
    assert movement_value.statline == statline
    assert movement_value.statline_type_stat == movement_stat
    assert movement_value.value == '8"'
    
    # Test string representation
    assert str(movement_value) == "M: 8\""
    assert str(statline) == "Test House Test Fighter (Leader) - Vehicle Statline"
    
    # Test unique together constraint
    with pytest.raises(Exception):  # IntegrityError
        ContentStatlineStat.objects.create(
            statline=statline,
            statline_type_stat=movement_stat,
            value="10\"",
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
    for field_name, short_name, full_name, position, highlight, first_of_group in stats_data:
        stat = ContentStatlineTypeStat.objects.create(
            statline_type=vehicle_type,
            field_name=field_name,
            short_name=short_name,
            full_name=full_name,
            position=position,
            is_highlighted=highlight,
            is_first_of_group=first_of_group,
        )
        type_stats.append(stat)
    
    # Create custom statline
    custom_statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=vehicle_type,
    )
    
    # Create stat values
    stat_values = ['8"', "12", "10", "9", "3", "6+", "5+"]
    for stat, value in zip(type_stats, stat_values):
        ContentStatlineStat.objects.create(
            statline=custom_statline,
            statline_type_stat=stat,
            value=value,
        )
    
    # Test the statline method
    statline = fighter.statline()
    
    assert len(statline) == 7
    assert statline[0]["name"] == "M"
    assert statline[0]["value"] == '8"'
    assert statline[0]["highlight"] is False
    
    assert statline[4]["name"] == "HP"
    assert statline[4]["value"] == "3"
    assert statline[4]["classes"] == "border-start"
    
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
        category="GANGER"  # Add required category
    )
    
    # Create statline type with stats
    statline_type = ContentStatlineType.objects.create(name="Test Type")
    
    ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        field_name="stat1",
        short_name="S1",
        full_name="Stat 1",
        position=1,
    )
    
    ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        field_name="stat2",
        short_name="S2",
        full_name="Stat 2",
        position=2,
    )
    
    # Create statline without all required stats
    statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=statline_type,
    )
    
    # Add only one stat value
    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=statline_type.stats.first(),
        value="10",
    )
    
    # Validation should fail because stat2 is missing
    with pytest.raises(ValidationError) as exc_info:
        statline.clean()
    
    assert "Missing required stats: stat2" in str(exc_info.value)