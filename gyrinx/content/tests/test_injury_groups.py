import pytest

from gyrinx.content.models import ContentInjury, ContentInjuryGroup
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_content_injury_group_creation():
    """Test creating a ContentInjuryGroup."""
    group = ContentInjuryGroup.objects.create(
        name="Vehicle Damage",
        description="Damage specific to vehicles",
        restricted_to=[FighterCategoryChoices.VEHICLE],
    )
    assert group.name == "Vehicle Damage"
    assert group.description == "Damage specific to vehicles"
    assert FighterCategoryChoices.VEHICLE in group.restricted_to
    assert group.unavailable_to == []


@pytest.mark.django_db
def test_injury_group_availability_logic():
    """Test the is_available_for_fighter_category method."""
    # Create a group restricted to Leaders and Champions
    leader_group = ContentInjuryGroup.objects.create(
        name="Leader Injuries",
        restricted_to=[FighterCategoryChoices.LEADER, FighterCategoryChoices.CHAMPION],
    )

    # Leaders and Champions should see it
    assert leader_group.is_available_for_fighter_category(FighterCategoryChoices.LEADER)
    assert leader_group.is_available_for_fighter_category(
        FighterCategoryChoices.CHAMPION
    )

    # Others should not
    assert not leader_group.is_available_for_fighter_category(
        FighterCategoryChoices.GANGER
    )
    assert not leader_group.is_available_for_fighter_category(
        FighterCategoryChoices.JUVE
    )


@pytest.mark.django_db
def test_injury_group_unavailable_to():
    """Test unavailable_to restriction."""
    # Create a group that's available to all except vehicles
    non_vehicle_group = ContentInjuryGroup.objects.create(
        name="Standard Injuries",
        unavailable_to=[FighterCategoryChoices.VEHICLE],
    )

    # Non-vehicles should see it
    assert non_vehicle_group.is_available_for_fighter_category(
        FighterCategoryChoices.LEADER
    )
    assert non_vehicle_group.is_available_for_fighter_category(
        FighterCategoryChoices.GANGER
    )

    # Vehicles should not
    assert not non_vehicle_group.is_available_for_fighter_category(
        FighterCategoryChoices.VEHICLE
    )


@pytest.mark.django_db
def test_injury_group_conflicting_restrictions():
    """Test when category is in both restricted_to and unavailable_to."""
    # This is weird but unavailable_to should win
    conflicting_group = ContentInjuryGroup.objects.create(
        name="Conflicting Group",
        restricted_to=[FighterCategoryChoices.LEADER],
        unavailable_to=[FighterCategoryChoices.LEADER],
    )

    # unavailable_to wins
    assert not conflicting_group.is_available_for_fighter_category(
        FighterCategoryChoices.LEADER
    )


@pytest.mark.django_db
def test_injury_with_group():
    """Test injury linked to a group."""
    group = ContentInjuryGroup.objects.create(
        name="Spyrer Glitches",
        description="Technical malfunctions for Spyrer suits",
    )

    injury = ContentInjury.objects.create(
        name="Servo Malfunction",
        description="The suit's servos are damaged",
        injury_group=group,
    )

    assert injury.injury_group == group
    assert injury.get_group_name() == "Spyrer Glitches"


@pytest.mark.django_db
def test_injury_get_group_name_fallback():
    """Test get_group_name falls back to legacy group field."""
    # Injury with legacy group field only
    injury1 = ContentInjury.objects.create(
        name="Old Injury",
        group="Legacy Group",
    )
    assert injury1.get_group_name() == "Legacy Group"

    # Injury with neither
    injury2 = ContentInjury.objects.create(
        name="Ungrouped Injury",
    )
    assert injury2.get_group_name() == "Other"

    # Injury with both (injury_group takes precedence)
    new_group = ContentInjuryGroup.objects.create(name="New Group")
    injury3 = ContentInjury.objects.create(
        name="Modern Injury",
        group="Old Group",
        injury_group=new_group,
    )
    assert injury3.get_group_name() == "New Group"
