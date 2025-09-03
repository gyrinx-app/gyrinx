"""Tests for smart quote validation in content admin forms."""

import pytest

from gyrinx.content.admin import ContentStatlineStatForm, ContentWeaponProfileAdminForm
from gyrinx.models import SMART_QUOTES


@pytest.mark.django_db
def test_content_weapon_profile_admin_form_rejects_smart_quotes(
    content_books, make_equipment
):
    """Test that ContentWeaponProfileAdminForm rejects smart quotes in stat fields."""
    equipment = make_equipment("Test Equipment", category="Test Category")
    # Test with left double smart quote
    form_data = {
        "equipment": equipment.id,
        "name": "Test Weapon",
        "cost": "100",
        "range_short": f"12{SMART_QUOTES['LEFT_DOUBLE']}",  # Smart quote (left double)
        "range_long": '24"',
        "accuracy_short": "+1",
        "accuracy_long": "-1",
        "strength": "4",
        "armour_piercing": "-1",
        "damage": "1",
        "ammo": "4+",
        "traits": [],
    }
    form = ContentWeaponProfileAdminForm(data=form_data)
    assert not form.is_valid()
    assert "range_short" in form.errors
    assert "Smart quotes are not allowed" in str(form.errors["range_short"])

    # Test with right double smart quote
    form_data["range_short"] = (
        f"12{SMART_QUOTES['RIGHT_DOUBLE']}"  # Smart quote (right double)
    )
    form = ContentWeaponProfileAdminForm(data=form_data)
    assert not form.is_valid()
    assert "range_short" in form.errors

    # Test with left single smart quote
    form_data["range_short"] = (
        f"12{SMART_QUOTES['LEFT_SINGLE']}"  # Smart quote (left single)
    )
    form = ContentWeaponProfileAdminForm(data=form_data)
    assert not form.is_valid()
    assert "range_short" in form.errors

    # Test with right single smart quote
    form_data["range_short"] = (
        f"12{SMART_QUOTES['RIGHT_SINGLE']}"  # Smart quote (right single)
    )
    form = ContentWeaponProfileAdminForm(data=form_data)
    assert not form.is_valid()
    assert "range_short" in form.errors


@pytest.mark.django_db
def test_content_weapon_profile_admin_form_accepts_simple_quotes(
    content_books, make_equipment
):
    """Test that ContentWeaponProfileAdminForm accepts simple quotes."""
    equipment = make_equipment("Test Equipment", category="Test Category")
    form_data = {
        "equipment": equipment.id,
        "name": "Test Weapon",
        "cost": "100",
        "range_short": '12"',  # Simple quote
        "range_long": '24"',
        "accuracy_short": "+1",
        "accuracy_long": "-1",
        "strength": "4",
        "armour_piercing": "-1",
        "damage": "1",
        "ammo": "4+",
        "traits": [],
    }
    form = ContentWeaponProfileAdminForm(data=form_data)
    # Note: Form may not be valid due to other required fields,
    # but it shouldn't have smart quote errors
    if not form.is_valid():
        assert "range_short" not in form.errors or "Smart quotes" not in str(
            form.errors.get("range_short", "")
        )


@pytest.mark.django_db
def test_content_weapon_profile_admin_form_checks_multiple_fields(
    content_books, make_equipment
):
    """Test that all stat fields are checked for smart quotes."""
    equipment = make_equipment("Test Equipment", category="Test Category")
    fields_to_check = [
        "range_short",
        "range_long",
        "accuracy_short",
        "accuracy_long",
        "strength",
        "armour_piercing",
        "damage",
        "ammo",
    ]

    for field_name in fields_to_check:
        form_data = {
            "equipment": equipment.id,
            "name": "Test Weapon",
            "cost": "100",
            "range_short": "12",
            "range_long": "24",
            "accuracy_short": "+1",
            "accuracy_long": "-1",
            "strength": "4",
            "armour_piercing": "-1",
            "damage": "1",
            "ammo": "4+",
            "traits": [],
        }
        # Add smart quote to specific field
        form_data[field_name] = (
            f"{SMART_QUOTES['LEFT_DOUBLE']}test{SMART_QUOTES['RIGHT_DOUBLE']}"
        )
        form = ContentWeaponProfileAdminForm(data=form_data)
        assert not form.is_valid()
        assert field_name in form.errors
        assert "Smart quotes are not allowed" in str(form.errors[field_name])


@pytest.mark.django_db
def test_content_weapon_profile_admin_form_handles_non_string_values(
    content_books, make_equipment
):
    """Test that form handles non-string values without crashing."""
    equipment = make_equipment("Test Equipment", category="Test Category")
    form_data = {
        "equipment": equipment.id,
        "name": "Test Weapon",
        "cost": "100",
        "range_short": None,  # None value
        "range_long": 24,  # Integer value
        "accuracy_short": "+1",
        "accuracy_long": "-1",
        "strength": "4",
        "armour_piercing": "-1",
        "damage": "1",
        "ammo": "4+",
        "traits": [],
    }
    form = ContentWeaponProfileAdminForm(data=form_data)
    # Should not raise TypeError when checking for smart quotes
    form.is_valid()  # This should not crash


@pytest.mark.django_db
def test_content_statline_stat_form_rejects_smart_quotes():
    """Test that ContentStatlineStatForm rejects smart quotes in value field."""
    # Test with left double smart quote
    form_data = {
        "value": f"6{SMART_QUOTES['LEFT_DOUBLE']}",  # Smart quote (left double)
    }
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()
    assert "value" in form.errors
    assert "Smart quotes are not allowed" in str(form.errors["value"])

    # Test with right double smart quote
    form_data["value"] = (
        f"6{SMART_QUOTES['RIGHT_DOUBLE']}"  # Smart quote (right double)
    )
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()
    assert "value" in form.errors

    # Test with left single smart quote
    form_data["value"] = f"6{SMART_QUOTES['LEFT_SINGLE']}"  # Smart quote (left single)
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()
    assert "value" in form.errors

    # Test with right single smart quote
    form_data["value"] = (
        f"6{SMART_QUOTES['RIGHT_SINGLE']}'"  # Smart quote (right single)
    )
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()
    assert "value" in form.errors


@pytest.mark.django_db
def test_content_statline_stat_form_accepts_simple_quotes():
    """Test that ContentStatlineStatForm accepts simple quotes."""
    form_data = {
        "value": '6"',  # Simple quote
    }
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()
    # Should not have smart quote error
    if "value" in form.errors:
        assert "Smart quotes" not in str(form.errors["value"])


@pytest.mark.django_db
def test_content_statline_stat_form_handles_non_string_values():
    """Test that form handles non-string values without crashing."""
    # Test with None
    form_data = {"value": None}
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()  # Should not raise TypeError

    # Test with integer (though this would normally be converted to string)
    form_data = {"value": 42}
    form = ContentStatlineStatForm(data=form_data)
    form.is_valid()  # Should not raise TypeError
