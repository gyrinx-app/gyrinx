import pytest

from gyrinx.content.models import (
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentSkill,
    ContentSkillCategory,
)


@pytest.mark.django_db
def test_content_injury_creation():
    """Test basic ContentInjury model creation and attributes."""
    injury = ContentInjury.objects.create(
        name="Spinal Injury",
        description="Recovery, -1 Strength",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    assert injury.name == "Spinal Injury"
    assert injury.description == "Recovery, -1 Strength"
    assert injury.phase == ContentInjuryDefaultOutcome.RECOVERY
    assert injury.get_phase_display() == "Recovery"
    assert str(injury) == "Spinal Injury"


@pytest.mark.django_db
def test_injury_phases():
    """Test all injury default outcome choices."""
    phases = [
        (ContentInjuryDefaultOutcome.NO_CHANGE, "No Change"),
        (ContentInjuryDefaultOutcome.ACTIVE, "Active"),
        (ContentInjuryDefaultOutcome.RECOVERY, "Recovery"),
        (ContentInjuryDefaultOutcome.CONVALESCENCE, "Convalescence"),
        (ContentInjuryDefaultOutcome.DEAD, "Dead"),
    ]

    for phase_value, phase_display in phases:
        injury = ContentInjury.objects.create(
            name=f"Test {phase_display}",
            phase=phase_value,
        )
        assert injury.phase == phase_value
        assert injury.get_phase_display() == phase_display


@pytest.mark.django_db
def test_injury_with_stat_modifiers():
    """Test injury with fighter stat modifiers."""
    injury = ContentInjury.objects.create(
        name="Humiliated",
        description="Convalescence, -1 Leadership, -1 Cool",
        phase=ContentInjuryDefaultOutcome.CONVALESCENCE,
    )

    # Create stat modifiers
    leadership_mod = ContentModFighterStat.objects.create(
        stat="leadership",
        mode="worsen",
        value="1",
    )
    cool_mod = ContentModFighterStat.objects.create(
        stat="cool",
        mode="worsen",
        value="1",
    )

    # Add modifiers to injury
    injury.modifiers.add(leadership_mod, cool_mod)

    # Verify modifiers
    mods = list(injury.modifiers.all())
    assert len(mods) == 2
    assert leadership_mod in mods
    assert cool_mod in mods


@pytest.mark.django_db
def test_injury_with_skill_modifiers():
    """Test injury with skill modifiers."""
    # Create a skill category and skill
    category, _ = ContentSkillCategory.objects.get_or_create(name="Combat")
    skill, _ = ContentSkill.objects.get_or_create(
        name="Iron Jaw",
        category=category,
    )

    injury = ContentInjury.objects.create(
        name="Toughened",
        description="Gains Iron Jaw skill",
        phase=ContentInjuryDefaultOutcome.ACTIVE,
    )

    # Create skill modifier
    skill_mod = ContentModFighterSkill.objects.create(
        skill=skill,
        mode="add",
    )

    # Add modifier to injury
    injury.modifiers.add(skill_mod)

    # Verify modifier
    assert injury.modifiers.count() == 1
    assert injury.modifiers.first() == skill_mod


@pytest.mark.django_db
def test_injury_unique_name():
    """Test that injury names must be unique."""
    ContentInjury.objects.create(
        name="Critical Injury",
        phase=ContentInjuryDefaultOutcome.ACTIVE,
    )

    # Try to create another with the same name
    with pytest.raises(Exception):  # IntegrityError
        ContentInjury.objects.create(
            name="Critical Injury",
            phase=ContentInjuryDefaultOutcome.RECOVERY,
        )


@pytest.mark.django_db
def test_injury_ordering():
    """Test that injuries are ordered by injury_group then name."""
    # Create injury groups
    from gyrinx.content.models import ContentInjuryGroup

    group_a = ContentInjuryGroup.objects.create(name="Group A")
    group_b = ContentInjuryGroup.objects.create(name="Group B")

    # Create injuries in non-alphabetical order
    injury3 = ContentInjury.objects.create(
        name="Zebra Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
        injury_group=group_a,
    )
    injury1 = ContentInjury.objects.create(
        name="Alpha Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
        injury_group=group_a,
    )
    injury2 = ContentInjury.objects.create(
        name="Beta Injury",
        phase=ContentInjuryDefaultOutcome.ACTIVE,
        injury_group=group_b,
    )
    injury4 = ContentInjury.objects.create(
        name="Gamma Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
        injury_group=None,  # No group
    )

    # Get all injuries in order
    injuries = list(ContentInjury.objects.all())

    # Should be ordered by injury_group (null groups last), then by name
    assert injuries[0] == injury1  # Group A, Alpha
    assert injuries[1] == injury3  # Group A, Zebra
    assert injuries[2] == injury2  # Group B, Beta
    assert injuries[3] == injury4  # No group, Gamma


@pytest.mark.django_db
def test_injury_blank_description():
    """Test that injury description can be blank."""
    injury = ContentInjury.objects.create(
        name="Mystery Injury",
        description="",
        phase=ContentInjuryDefaultOutcome.ACTIVE,
    )

    assert injury.description == ""
    injury.full_clean()  # Should not raise validation error


@pytest.mark.django_db
def test_injury_history_tracking():
    """Test that injury model has history tracking."""
    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Check that history is tracked
    assert hasattr(injury, "history")
    assert injury.history.count() == 1

    # Update the injury
    injury.description = "Updated description"
    injury.save()

    # Check history was updated
    assert injury.history.count() == 2
    latest_history = injury.history.first()
    assert latest_history.description == "Updated description"
