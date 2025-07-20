import pytest

from gyrinx.content.models import (
    ContentWeaponAccessory,
)


@pytest.mark.django_db
def test_weapon_accessory_without_cost_expression():
    """Test that accessories without cost expressions use the base cost."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
    )

    # Should use base cost when no expression
    assert accessory.calculate_cost_for_weapon(100) == 25
    assert accessory.cost_int() == 25


@pytest.mark.django_db
def test_weapon_accessory_with_simple_expression():
    """Test that accessories with simple cost expressions calculate correctly."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="cost_int * 2",
    )

    # Should calculate based on expression
    assert accessory.calculate_cost_for_weapon(100) == 200
    assert accessory.calculate_cost_for_weapon(50) == 100


@pytest.mark.django_db
def test_weapon_accessory_with_percentage_expression():
    """Test that accessories with percentage expressions calculate correctly."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="cost_int * 0.25",
    )

    # Should calculate 25% of base cost
    assert accessory.calculate_cost_for_weapon(100) == 25
    assert accessory.calculate_cost_for_weapon(200) == 50


@pytest.mark.django_db
def test_weapon_accessory_with_round_function():
    """Test that accessories can use the round function."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="round(cost_int * 0.15)",
    )

    # Should round to nearest integer
    assert accessory.calculate_cost_for_weapon(100) == 15  # 15.0
    assert (
        accessory.calculate_cost_for_weapon(110) == 16
    )  # 16.5 rounds to 16 (banker's rounding)


@pytest.mark.django_db
def test_weapon_accessory_master_crafted_expression():
    """Test the master crafted expression: 25% rounded up to nearest 5."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Master Crafted",
        cost=0,
        cost_expression="ceil(cost_int * 0.25 / 5) * 5",
    )

    # Test various weapon costs
    assert accessory.calculate_cost_for_weapon(100) == 25  # 25.0 -> 25
    assert accessory.calculate_cost_for_weapon(110) == 30  # 27.5 -> 30
    assert accessory.calculate_cost_for_weapon(120) == 30  # 30.0 -> 30
    assert accessory.calculate_cost_for_weapon(130) == 35  # 32.5 -> 35
    assert accessory.calculate_cost_for_weapon(140) == 35  # 35.0 -> 35
    assert accessory.calculate_cost_for_weapon(150) == 40  # 37.5 -> 40


@pytest.mark.django_db
def test_weapon_accessory_with_ceil_function():
    """Test that accessories can use the ceil function."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="ceil(cost_int * 0.15)",
    )

    # Should round up to nearest integer
    assert accessory.calculate_cost_for_weapon(100) == 15  # 15.0
    assert accessory.calculate_cost_for_weapon(110) == 17  # 16.5 rounds up to 17


@pytest.mark.django_db
def test_weapon_accessory_with_floor_function():
    """Test that accessories can use the floor function."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="floor(cost_int * 0.15)",
    )

    # Should round down to nearest integer
    assert accessory.calculate_cost_for_weapon(100) == 15  # 15.0
    assert accessory.calculate_cost_for_weapon(110) == 16  # 16.5 rounds down to 16


@pytest.mark.django_db
def test_weapon_accessory_with_invalid_expression():
    """Test that accessories with invalid expressions fall back to base cost."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="invalid python code!",
    )

    # Should fall back to base cost
    assert accessory.calculate_cost_for_weapon(100) == 25


@pytest.mark.django_db
def test_weapon_accessory_expression_returns_float():
    """Test that expressions returning floats are converted to integers."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
        cost_expression="cost_int * 0.333",  # Returns float
    )

    # Should convert float to int
    assert accessory.calculate_cost_for_weapon(100) == 33  # 33.3 -> 33
    assert isinstance(accessory.calculate_cost_for_weapon(100), int)


@pytest.mark.django_db
def test_weapon_accessory_cost_expression_field_is_optional():
    """Test that the cost_expression field is optional."""
    # Should create without error
    accessory = ContentWeaponAccessory.objects.create(
        name="Test Accessory",
        cost=25,
    )

    assert accessory.cost_expression == ""
    assert accessory.calculate_cost_for_weapon(100) == 25
