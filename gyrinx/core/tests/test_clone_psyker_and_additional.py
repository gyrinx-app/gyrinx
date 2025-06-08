import pytest

from gyrinx.content.models import (
    ContentFighterPsykerPowerDefaultAssignment,
    ContentHouseAdditionalRule,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
)
from gyrinx.core.models.list import ListFighter, ListFighterPsykerPowerAssignment


@pytest.mark.django_db
def test_fighter_clone_with_psyker_powers(
    content_fighter, make_list, make_list_fighter
):
    """Test that psyker powers are properly cloned with a fighter."""
    # Set up psyker
    psyker, _ = ContentRule.objects.get_or_create(name="Psyker")
    content_fighter.rules.add(psyker)

    # Create disciplines and powers
    biomancy, _ = ContentPsykerDiscipline.objects.get_or_create(
        name="Biomancy", generic=True
    )
    arachnosis, _ = ContentPsykerPower.objects.get_or_create(
        name="Arachnosis", discipline=biomancy
    )
    freeze_time, _ = ContentPsykerPower.objects.get_or_create(
        name="Freeze Time", discipline=biomancy
    )

    # Create a default psyker power
    default_power = ContentFighterPsykerPowerDefaultAssignment.objects.create(
        fighter=content_fighter, psyker_power=arachnosis
    )

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(
        lst, "Test Fighter", content_fighter=content_fighter
    )

    # Assign an additional psyker power
    ListFighterPsykerPowerAssignment.objects.create(
        list_fighter=fighter, psyker_power=freeze_time
    )

    # Disable the default power
    fighter.disabled_pskyer_default_powers.add(default_power)
    fighter.save()

    # Clone the fighter
    cloned_fighter = fighter.clone(name="Clone Fighter")

    # Check that psyker powers were cloned
    assert cloned_fighter.psyker_powers.count() == 1
    assert cloned_fighter.psyker_powers.first().psyker_power == freeze_time

    # Check that disabled default powers were cloned
    assert cloned_fighter.disabled_pskyer_default_powers.count() == 1
    assert cloned_fighter.disabled_pskyer_default_powers.first() == default_power


@pytest.mark.django_db
def test_fighter_clone_with_additional_rules(
    content_fighter, make_list, make_list_fighter
):
    """Test that additional rules are properly cloned with a fighter."""
    # Create house additional rules
    house = content_fighter.house
    rule1 = ContentHouseAdditionalRule.objects.create(
        house=house,
        name="Test Rule 1",
        description="Description 1",
    )
    rule2 = ContentHouseAdditionalRule.objects.create(
        house=house,
        name="Test Rule 2",
        description="Description 2",
    )

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Add additional rules
    fighter.additional_rules.add(rule1, rule2)

    # Clone the fighter
    cloned_fighter = fighter.clone(name="Clone Fighter")

    # Check that additional rules were cloned
    assert cloned_fighter.additional_rules.count() == 2
    assert rule1 in cloned_fighter.additional_rules.all()
    assert rule2 in cloned_fighter.additional_rules.all()


@pytest.mark.django_db
def test_fighter_clone_with_stat_overrides(
    content_fighter, make_list, make_list_fighter
):
    """Test that stat overrides are properly cloned with a fighter."""
    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Set stat overrides
    fighter.movement_override = "6''"
    fighter.weapon_skill_override = "2+"
    fighter.ballistic_skill_override = "3+"
    fighter.strength_override = "5"
    fighter.toughness_override = "4"
    fighter.wounds_override = "3"
    fighter.initiative_override = "4+"
    fighter.attacks_override = "3"
    fighter.leadership_override = "7"
    fighter.cool_override = "6+"
    fighter.willpower_override = "7+"
    fighter.intelligence_override = "8+"
    fighter.save()

    # Clone the fighter
    cloned_fighter = fighter.clone(name="Clone Fighter")

    # Check that stat overrides were cloned
    assert cloned_fighter.movement_override == "6''"
    assert cloned_fighter.weapon_skill_override == "2+"
    assert cloned_fighter.ballistic_skill_override == "3+"
    assert cloned_fighter.strength_override == "5"
    assert cloned_fighter.toughness_override == "4"
    assert cloned_fighter.wounds_override == "3"
    assert cloned_fighter.initiative_override == "4+"
    assert cloned_fighter.attacks_override == "3"
    assert cloned_fighter.leadership_override == "7"
    assert cloned_fighter.cool_override == "6+"
    assert cloned_fighter.willpower_override == "7+"
    assert cloned_fighter.intelligence_override == "8+"


@pytest.mark.django_db
def test_fighter_clone_with_legacy_content_fighter(
    content_fighter, make_list, make_list_fighter, make_content_fighter
):
    """Test that legacy content fighter is properly cloned."""
    # Create a legacy content fighter
    legacy_fighter = make_content_fighter(
        type="Legacy Fighter", category="GANGER", can_be_legacy=True
    )

    # Create list and fighter
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")
    fighter.content_fighter.can_take_legacy = True
    fighter.content_fighter.save()

    fighter.legacy_content_fighter = legacy_fighter
    fighter.save()

    # Clone the fighter
    cloned_fighter = fighter.clone(name="Clone Fighter")

    # Check that legacy content fighter was cloned
    assert cloned_fighter.legacy_content_fighter == legacy_fighter