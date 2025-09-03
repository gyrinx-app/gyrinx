"""Tests for smart quote validation in core forms."""

import pytest

from gyrinx.core.forms.list import EditListFighterStatsForm
from gyrinx.core.models import List, ListFighter


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_rejects_smart_quotes(user, content_fighter):
    """Test that EditListFighterStatsForm rejects smart quotes in stat override fields."""
    # Create a list and fighter
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    # Test with left double smart quote in movement_override
    form_data = {
        "movement_override": '6"',  # Smart quote (left double)
        "weapon_skill_override": "3+",
        "ballistic_skill_override": "4+",
        "strength_override": "3",
        "toughness_override": "3",
        "wounds_override": "1",
        "initiative_override": "4",
        "attacks_override": "1",
        "leadership_override": "7",
        "save_override": "5+",
        "invulnerable_save_override": "",
        "cool_override": "7",
        "willpower_override": "7",
        "intelligence_override": "7",
    }
    form = EditListFighterStatsForm(data=form_data, instance=fighter)
    assert not form.is_valid()
    assert "movement_override" in form.errors
    assert "Smart quotes are not allowed" in str(form.errors["movement_override"])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_rejects_various_smart_quotes(
    user, content_fighter
):
    """Test that form rejects all types of smart quotes."""
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    # Test different smart quote types
    smart_quotes_to_test = [
        '"',  # Left double quotation mark
        '"',  # Right double quotation mark
        "'",  # Left single quotation mark
        "'",  # Right single quotation mark
    ]

    for smart_quote in smart_quotes_to_test:
        form_data = {
            "movement_override": f"6{smart_quote}",
        }
        form = EditListFighterStatsForm(data=form_data, instance=fighter)
        assert not form.is_valid()
        assert "movement_override" in form.errors
        assert "Smart quotes are not allowed" in str(form.errors["movement_override"])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_accepts_simple_quotes(user, content_fighter):
    """Test that EditListFighterStatsForm accepts simple quotes."""
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    form_data = {
        "movement_override": '6"',  # Simple double quote
        "save_override": "5+",  # Simple plus sign
        "weapon_skill_override": "3'",  # Simple single quote
    }
    form = EditListFighterStatsForm(data=form_data, instance=fighter)
    form.is_valid()
    # Should not have smart quote errors
    for field_name in ["movement_override", "save_override", "weapon_skill_override"]:
        if field_name in form.errors:
            assert "Smart quotes" not in str(form.errors[field_name])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_checks_all_override_fields(user, content_fighter):
    """Test that all stat override fields are checked for smart quotes."""
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    # List of fields that should be checked
    fields_to_check = [
        "movement_override",
        "weapon_skill_override",
        "ballistic_skill_override",
        "strength_override",
        "toughness_override",
        "wounds_override",
        "initiative_override",
        "attacks_override",
        "leadership_override",
        "save_override",
        "invulnerable_save_override",
        "cool_override",
        "willpower_override",
        "intelligence_override",
    ]

    for field_name in fields_to_check:
        form_data = {field_name: '"test"'}  # Using smart quotes
        form = EditListFighterStatsForm(data=form_data, instance=fighter)
        assert not form.is_valid()
        assert field_name in form.errors
        assert "Smart quotes are not allowed" in str(form.errors[field_name])


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_handles_non_string_values(user, content_fighter):
    """Test that form handles non-string values without crashing."""
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    # Test with None values
    form_data = {
        "movement_override": None,
        "weapon_skill_override": None,
        "strength_override": None,
    }
    form = EditListFighterStatsForm(data=form_data, instance=fighter)
    form.is_valid()  # Should not raise TypeError

    # Test with integer values (though form fields usually convert to string)
    form_data = {
        "movement_override": 6,
        "wounds_override": 1,
        "attacks_override": 2,
    }
    form = EditListFighterStatsForm(data=form_data, instance=fighter)
    form.is_valid()  # Should not raise TypeError


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_shows_user_friendly_field_names(
    user, content_fighter
):
    """Test that error messages use user-friendly field names when available."""
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    form_data = {
        "movement_override": '"6"',  # Smart quotes
    }
    form = EditListFighterStatsForm(data=form_data, instance=fighter)
    assert not form.is_valid()
    # Check that the error message is associated with the correct field
    assert "movement_override" in form.errors


@pytest.mark.django_db
def test_edit_list_fighter_stats_form_with_mixed_content(user, content_fighter):
    """Test form with mix of valid and invalid values."""
    lst = List.objects.create(name="Test List", owner=user)
    fighter = ListFighter.objects.create(
        list=lst,
        fighter_template=content_fighter,
        name="Test Fighter",
    )

    form_data = {
        "movement_override": '6"',  # Simple quote - valid
        "weapon_skill_override": "3+",  # Valid
        "ballistic_skill_override": '"4+"',  # Smart quotes - invalid
        "strength_override": "3",  # Valid
        "save_override": '5"',  # Smart quote - invalid
    }
    form = EditListFighterStatsForm(data=form_data, instance=fighter)
    assert not form.is_valid()
    # Should have errors for fields with smart quotes
    assert "ballistic_skill_override" in form.errors
    assert "save_override" in form.errors
    # Should not have errors for valid fields
    assert "movement_override" not in form.errors
    assert "weapon_skill_override" not in form.errors
    assert "strength_override" not in form.errors
