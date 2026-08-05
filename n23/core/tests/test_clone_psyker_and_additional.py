import pytest

from n23.content.models import (
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
)
from n23.core.models.list import ListFighter, ListFighterPsykerPowerAssignment


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
def test_fighter_clone_with_stat_overrides(
    content_fighter, make_list, make_list_fighter, make_statline, make_stat_override
):
    """Test that stat overrides are properly cloned with a fighter."""
    # Create list and fighter
    make_statline(content_fighter)
    lst = make_list("Test List")
    fighter: ListFighter = make_list_fighter(lst, "Test Fighter")

    # Set stat overrides
    overrides = {
        "movement": "6''",
        "weapon_skill": "2+",
        "ballistic_skill": "3+",
        "strength": "5",
        "toughness": "4",
        "wounds": "3",
        "initiative": "4+",
        "attacks": "3",
        "leadership": "7",
        "cool": "6+",
        "willpower": "7+",
        "intelligence": "8+",
    }
    for field_name, value in overrides.items():
        make_stat_override(fighter, field_name, value)

    # Clone the fighter
    cloned_fighter = fighter.clone(name="Clone Fighter")

    # Check that stat overrides were cloned
    assert {
        override.content_stat.field_name: override.value
        for override in cloned_fighter.stat_overrides.all()
    } == overrides
    # ...and that they reach the clone's card
    assert [stat.value for stat in cloned_fighter.statline] == list(overrides.values())


@pytest.mark.django_db
def test_fighter_clone_with_legacy_content_fighter(
    content_fighter, content_house, make_list, make_list_fighter, make_content_fighter
):
    """Test that legacy content fighter is properly cloned."""
    # Create a legacy content fighter
    legacy_fighter = make_content_fighter(
        type="Legacy Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
        can_be_legacy=True,
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
