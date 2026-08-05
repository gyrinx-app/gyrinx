"""Tests for smart quote validation in core forms."""

import pytest

from n23.core.forms.list import EditListFighterStatsForm
from n23.core.models import List, ListFighter
from gyrinx.models import SMART_QUOTES


@pytest.fixture
def fighter_with_statline(user, content_fighter, house, make_statline):
    """A fighter whose template has a statline, so the stats form has fields.

    Overrides are rows keyed to a statline's stats (#1861 Track C2), so a
    template without one gives the form nothing to validate.
    """
    make_statline(content_fighter)
    lst = List.objects.create(name="Test List", owner=user, content_house=house)
    return ListFighter.objects.create(
        list=lst,
        content_fighter=content_fighter,
        name="Test Fighter",
    )


def field_for(fighter, field_name):
    """The stats form's field name for one stat, e.g. "stat_<uuid>"."""
    type_stat = fighter.content_fighter.custom_statline.statline_type.stats.get(
        stat__field_name=field_name
    )
    return f"stat_{type_stat.id}"


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_rejects_smart_quotes(fighter_with_statline):
    """Test that EditListFighterStatsForm rejects smart quotes in stat fields."""
    fighter = fighter_with_statline
    movement = field_for(fighter, "movement")

    # Test with left double smart quote in movement
    form_data = {
        movement: f"6{SMART_QUOTES['LEFT_DOUBLE']}",  # Smart quote (left double)
        field_for(fighter, "weapon_skill"): "3+",
        field_for(fighter, "ballistic_skill"): "4+",
        field_for(fighter, "strength"): "3",
        field_for(fighter, "toughness"): "3",
        field_for(fighter, "wounds"): "1",
        field_for(fighter, "initiative"): "4",
        field_for(fighter, "attacks"): "1",
        field_for(fighter, "leadership"): "7",
        field_for(fighter, "cool"): "7",
        field_for(fighter, "willpower"): "7",
        field_for(fighter, "intelligence"): "7",
    }
    form = EditListFighterStatsForm(data=form_data, fighter=fighter)
    assert not form.is_valid()
    assert movement in form.errors
    assert "Smart quotes are not allowed" in str(form.errors[movement])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_rejects_various_smart_quotes(
    fighter_with_statline,
):
    """Test that form rejects all types of smart quotes."""
    fighter = fighter_with_statline
    movement = field_for(fighter, "movement")

    # Test different smart quote types
    smart_quotes_to_test = SMART_QUOTES.values()

    for smart_quote in smart_quotes_to_test:
        form_data = {
            movement: f"6{smart_quote}",
        }
        form = EditListFighterStatsForm(data=form_data, fighter=fighter)
        assert not form.is_valid()
        assert movement in form.errors
        assert "Smart quotes are not allowed" in str(form.errors[movement])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_accepts_simple_quotes(fighter_with_statline):
    """Test that EditListFighterStatsForm accepts simple quotes."""
    fighter = fighter_with_statline
    movement = field_for(fighter, "movement")
    weapon_skill = field_for(fighter, "weapon_skill")

    form_data = {
        movement: '6"',  # Simple double quote
        weapon_skill: "3'",  # Simple single quote
    }
    form = EditListFighterStatsForm(data=form_data, fighter=fighter)
    form.is_valid()
    # Should not have smart quote errors
    for field_name in [movement, weapon_skill]:
        if field_name in form.errors:
            assert "Smart quotes" not in str(form.errors[field_name])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_checks_all_stat_fields(fighter_with_statline):
    """Test that every stat field is checked for smart quotes."""
    fighter = fighter_with_statline

    stats_to_check = [
        "movement",
        "weapon_skill",
        "ballistic_skill",
        "strength",
        "toughness",
        "wounds",
        "initiative",
        "attacks",
        "leadership",
        "cool",
        "willpower",
        "intelligence",
    ]

    for stat in stats_to_check:
        field_name = field_for(fighter, stat)
        form_data = {
            field_name: f"{SMART_QUOTES['LEFT_DOUBLE']}test{SMART_QUOTES['RIGHT_DOUBLE']}"
        }  # Using smart quotes
        form = EditListFighterStatsForm(data=form_data, fighter=fighter)
        assert not form.is_valid()
        assert field_name in form.errors
        assert "Smart quotes are not allowed" in str(form.errors[field_name])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_handles_non_string_values(
    fighter_with_statline,
):
    """Test that form handles non-string values without crashing."""
    fighter = fighter_with_statline

    # Test with None values
    form_data = {
        field_for(fighter, "movement"): None,
        field_for(fighter, "weapon_skill"): None,
        field_for(fighter, "strength"): None,
    }
    form = EditListFighterStatsForm(data=form_data, fighter=fighter)
    form.is_valid()  # Should not raise TypeError

    # Test with integer values (though form fields usually convert to string)
    form_data = {
        field_for(fighter, "movement"): 6,
        field_for(fighter, "wounds"): 1,
        field_for(fighter, "attacks"): 2,
    }
    form = EditListFighterStatsForm(data=form_data, fighter=fighter)
    form.is_valid()  # Should not raise TypeError


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_shows_user_friendly_field_names(
    fighter_with_statline,
):
    """Test that error messages use user-friendly field names when available."""
    fighter = fighter_with_statline
    movement = field_for(fighter, "movement")

    form_data = {
        movement: f"{SMART_QUOTES['LEFT_DOUBLE']}6{SMART_QUOTES['RIGHT_DOUBLE']}",  # Smart quotes
    }
    form = EditListFighterStatsForm(data=form_data, fighter=fighter)
    assert not form.is_valid()
    # Check that the error message is associated with the correct field
    assert movement in form.errors
    # The message names the stat, not the opaque field id
    assert "Movement" in str(form.errors[movement])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_with_mixed_content(fighter_with_statline):
    """Test form with mix of valid and invalid values."""
    fighter = fighter_with_statline
    movement = field_for(fighter, "movement")
    weapon_skill = field_for(fighter, "weapon_skill")
    ballistic_skill = field_for(fighter, "ballistic_skill")
    strength = field_for(fighter, "strength")

    form_data = {
        movement: '6"',  # Simple quote - valid
        weapon_skill: "3+",  # Valid
        ballistic_skill: f"{SMART_QUOTES['LEFT_DOUBLE']}4+{SMART_QUOTES['RIGHT_DOUBLE']}",  # Smart quotes - invalid
        strength: "3",  # Valid
    }
    form = EditListFighterStatsForm(data=form_data, fighter=fighter)
    assert not form.is_valid()
    # Should have errors for fields with smart quotes
    assert ballistic_skill in form.errors
    # Should not have errors for valid fields
    assert movement not in form.errors
    assert weapon_skill not in form.errors
    assert strength not in form.errors
