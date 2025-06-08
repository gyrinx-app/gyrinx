import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentModFighterStat,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter, ListFighterInjury
from gyrinx.models import FighterCategoryChoices


def create_base_test_data():
    """Create basic test data for modification tests."""
    user = User.objects.create_user(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
        # Base stats
        movement="5",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    return user, fighter


@pytest.mark.django_db
def test_injury_stat_modification_single():
    """Test that a single injury stat modification is applied correctly."""
    user, fighter = create_base_test_data()

    # Create injury with -1 Strength
    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Spinal Injury Mod",
        defaults={
            "description": "Recovery, -1 Strength",
            "phase": ContentInjuryDefaultOutcome.RECOVERY,
        },
    )

    # Create stat modifier
    strength_mod = ContentModFighterStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    )
    injury.modifiers.add(strength_mod)

    # Apply injury to fighter
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    # Refresh fighter to ensure injury is loaded
    fighter.refresh_from_db()

    # Get fighter's effective stats
    statline = fighter.statline
    strength_stat = next(s for s in statline if s.field_name == "strength")

    # Base strength is 3, with -1 should be 2
    assert strength_stat.value == "2"
    assert strength_stat.modded is True


@pytest.mark.django_db
def test_injury_stat_modification_multiple():
    """Test multiple stat modifications from a single injury."""
    user, fighter = create_base_test_data()

    # Create injury with multiple stat mods
    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Humiliated",
        defaults={
            "description": "Convalescence, -1 Leadership, -1 Cool",
            "phase": ContentInjuryDefaultOutcome.CONVALESCENCE,
        },
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
    injury.modifiers.add(leadership_mod, cool_mod)

    # Apply injury to fighter
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    # Refresh fighter to ensure injury is loaded
    fighter.refresh_from_db()

    # Get fighter's effective stats
    statline = fighter.statline
    leadership_stat = next(s for s in statline if s.field_name == "leadership")
    cool_stat = next(s for s in statline if s.field_name == "cool")

    # Base leadership is 7+, with worsen by 1 should be 8+
    assert leadership_stat.value == "8+"
    assert leadership_stat.modded is True

    # Base cool is 7+, with worsen by 1 should be 8+
    assert cool_stat.value == "8+"
    assert cool_stat.modded is True


@pytest.mark.django_db
def test_multiple_injuries_stat_stacking():
    """Test that multiple injuries stack their stat modifications."""
    user, fighter = create_base_test_data()

    # Create two injuries that both modify strength
    injury1, _ = ContentInjury.objects.get_or_create(
        name="Test Spinal Stack",
        defaults={"phase": ContentInjuryPhase.RECOVERY},
    )
    injury2, _ = ContentInjury.objects.get_or_create(
        name="Test Enfeebled Stack",
        defaults={"phase": ContentInjuryPhase.RECOVERY},
    )

    # Both reduce strength by 1
    strength_mod1 = ContentModFighterStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    )
    strength_mod2 = ContentModFighterStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    )

    injury1.modifiers.add(strength_mod1)
    injury2.modifiers.add(strength_mod2)

    # Apply both injuries
    ListFighterInjury.objects.create(fighter=fighter, injury=injury1, owner=user)
    ListFighterInjury.objects.create(fighter=fighter, injury=injury2, owner=user)

    # Refresh fighter to ensure injuries are loaded
    fighter.refresh_from_db()

    # Get fighter's effective stats
    statline = fighter.statline
    strength_stat = next(s for s in statline if s.field_name == "strength")

    # Base strength is 3, with -2 total should be 1
    assert strength_stat.value == "1"
    assert strength_stat.modded is True


@pytest.mark.django_db
def test_injury_movement_modification():
    """Test movement stat modification (uses inches)."""
    user, fighter = create_base_test_data()

    # Create injury with -1 Movement
    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Hobbled",
        defaults={
            "description": "Recovery, -1 Movement",
            "phase": ContentInjuryDefaultOutcome.RECOVERY,
        },
    )

    movement_mod = ContentModFighterStat.objects.create(
        stat="movement",
        mode="worsen",
        value="1",
    )
    injury.modifiers.add(movement_mod)

    # Apply injury
    ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)

    # Refresh fighter to ensure injury is loaded
    fighter.refresh_from_db()

    # Get fighter's effective stats
    statline = fighter.statline
    movement_stat = next(s for s in statline if s.field_name == "movement")

    # Base movement is 5, with -1 should be 4"
    assert movement_stat.value == '4"'
    assert movement_stat.modded is True


@pytest.mark.django_db
def test_injury_skill_addition():
    """Test injury that adds a skill."""
    user, fighter = create_base_test_data()

    # Create a skill
    category, _ = ContentSkillCategory.objects.get_or_create(name="Test Ferocity")
    skill, _ = ContentSkill.objects.get_or_create(
        name="Test Berserker",
        defaults={
            "category": category,
        },
    )

    # Create injury that grants skill
    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Battle Hardened",
        defaults={
            "description": "Gains Berserker skill",
            "phase": ContentInjuryDefaultOutcome.ACTIVE,
        },
    )

    skill_mod = ContentModFighterSkill.objects.create(
        skill=skill,
        mode="add",
    )
    injury.modifiers.add(skill_mod)

    # Apply injury
    ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)

    # Fighter should have the skill through injury
    # Note: This would need to be implemented in the fighter model
    # to actually apply injury skill mods, but we can test the setup
    fighter_injuries = fighter.injuries.all()
    assert fighter_injuries.count() == 1

    injury_mods = list(fighter_injuries[0].injury.modifiers.all())
    assert len(injury_mods) == 1
    assert injury_mods[0] == skill_mod


@pytest.mark.django_db
def test_injury_rule_addition():
    """Test injury that adds a rule."""
    user, fighter = create_base_test_data()

    # Create a rule
    rule, _ = ContentRule.objects.get_or_create(
        name="Test Fearsome",
    )

    # Create injury that grants rule
    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Horrific Scars",
        defaults={
            "description": "Gains Fearsome rule",
            "phase": ContentInjuryDefaultOutcome.ACTIVE,
        },
    )

    rule_mod = ContentModFighterRule.objects.create(
        rule=rule,
        mode="add",
    )
    injury.modifiers.add(rule_mod)

    # Apply injury
    ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)

    # Check the injury has the rule modifier
    fighter_injuries = fighter.injuries.all()
    assert fighter_injuries.count() == 1

    injury_mods = list(fighter_injuries[0].injury.modifiers.all())
    assert len(injury_mods) == 1
    assert injury_mods[0] == rule_mod


@pytest.mark.django_db
def test_injury_with_no_modifiers():
    """Test injury without any stat modifiers."""
    user, fighter = create_base_test_data()

    # Create injury with no modifiers
    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Out Cold",
        defaults={
            "description": "Miss rest of battle, no long-term effects",
            "phase": ContentInjuryPhase.OUT_COLD,
        },
    )

    # Apply injury
    ListFighterInjury.objects.create(fighter=fighter, injury=injury, owner=user)

    # Refresh fighter to ensure injury is loaded
    fighter.refresh_from_db()

    # Get fighter's effective stats - should be unchanged
    statline = fighter.statline

    # Check a few stats are unmodified
    strength_stat = next(s for s in statline if s.field_name == "strength")
    assert strength_stat.value == "3"
    assert strength_stat.modded is False

    movement_stat = next(s for s in statline if s.field_name == "movement")
    # Movement might be displayed as "5" or "5"" depending on formatting
    assert movement_stat.value in ("5", '5"')
    assert movement_stat.modded is False


@pytest.mark.django_db
def test_injury_phase_display():
    """Test that injuries display their phase correctly."""
    user, fighter = create_base_test_data()

    phases = [
        (ContentInjuryPhase.RECOVERY, "Recovery"),
        (ContentInjuryPhase.CONVALESCENCE, "Convalescence"),
        (ContentInjuryPhase.PERMANENT, "Permanent"),
        (ContentInjuryPhase.OUT_COLD, "Out Cold"),
    ]

    for phase_value, expected_display in phases:
        injury, _ = ContentInjury.objects.get_or_create(
            name=f"Test {expected_display} Phase",
            defaults={"phase": phase_value},
        )

        fighter_injury = ListFighterInjury.objects.create(
            fighter=fighter,
            injury=injury,
            owner=user,
        )

        # Check phase display
        assert fighter_injury.injury.get_phase_display() == expected_display

        # Clean up for next iteration
        fighter_injury.delete()


@pytest.mark.django_db
def test_injury_stat_mod_display():
    """Test the string representation of injury stat modifiers."""
    # Create stat modifiers and check their string representation
    worsen_mod = ContentModFighterStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    )
    assert str(worsen_mod) == "Worsen fighter Strength by 1"

    improve_mod = ContentModFighterStat.objects.create(
        stat="ballistic_skill",
        mode="improve",
        value="1",
    )
    assert str(improve_mod) == "Improve fighter Ballistic Skill by 1"

    set_mod = ContentModFighterStat.objects.create(
        stat="wounds",
        mode="set",
        value="3",
    )
    assert str(set_mod) == "Set fighter Wounds by 3"
