import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentFighter,
    ContentHouse,
    ContentRule,
    ContentWeaponProfile,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_basic_fighter():
    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger", category=category, house=house
    )

    fighter.save()
    assert fighter.type == "Prospector Digger"
    assert fighter.category.name == FighterCategoryChoices.JUVE


@pytest.mark.django_db
def test_fighter_stats():
    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
        movement='5"',
        weapon_skill="5+",
        ballistic_skill="5+",
        strength="4",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="8+",
        cool="7+",
        willpower="6+",
        intelligence="7+",
    )
    fighter.save()

    assert fighter.statline() == [
        {"name": "M", "value": '5"', "highlight": False, "classes": ""},
        {"name": "WS", "value": "5+", "highlight": False, "classes": ""},
        {"name": "BS", "value": "5+", "highlight": False, "classes": ""},
        {"name": "S", "value": "4", "highlight": False, "classes": ""},
        {"name": "T", "value": "3", "highlight": False, "classes": ""},
        {"name": "W", "value": "1", "highlight": False, "classes": ""},
        {"name": "I", "value": "4+", "highlight": False, "classes": ""},
        {"name": "A", "value": "1", "highlight": False, "classes": ""},
        {"name": "Ld", "value": "8+", "highlight": True, "classes": "border-start"},
        {"name": "Cl", "value": "7+", "highlight": True, "classes": ""},
        {"name": "Wil", "value": "6+", "highlight": True, "classes": ""},
        {"name": "Int", "value": "7+", "highlight": True, "classes": ""},
    ]


@pytest.mark.django_db
def test_fighter_rules():
    r_gang_fighter, _ = ContentRule.objects.get_or_create(name="Gang Fighter (Juve)")
    r_promotion, _ = ContentRule.objects.get_or_create(name="Promotion (Specialist)")
    r_fast_learner, _ = ContentRule.objects.get_or_create(name="Fast Learner")

    category = FighterCategoryChoices.JUVE
    house = ContentHouse.objects.create(
        name="Squat Prospectors",
    )
    fighter = ContentFighter.objects.create(
        type="Prospector Digger",
        category=category,
        house=house,
    )
    fighter.rules.set([r_gang_fighter, r_promotion, r_fast_learner])
    fighter.save()

    assert [rule.name for rule in fighter.rules.all()] == [
        "Fast Learner",
        "Gang Fighter (Juve)",
        "Promotion (Specialist)",
    ]
    assert fighter.ruleline() == [
        "Fast Learner",
        "Gang Fighter (Juve)",
        "Promotion (Specialist)",
    ]


@pytest.mark.django_db
def test_content_weapon_profile_validation():
    equipment = ContentEquipment.objects.create(name="Laser Gun")

    # Test valid profile
    profile = ContentWeaponProfile(
        equipment=equipment,
        name="Standard",
        cost=0,
        cost_sign="",
        rarity="C",
        range_short='12"',
        range_long='24"',
        accuracy_short="+1",
        accuracy_long="0",
        strength="4",
        armour_piercing="-1",
        damage="1",
        ammo="4+",
    )
    profile.clean()  # Should not raise any exception

    # Test invalid profile with negative cost
    profile.cost = -10
    with pytest.raises(ValidationError, match="Cost cannot be negative."):
        profile.clean()

    # Test invalid profile with non-empty cost sign for zero cost
    profile.cost = 0
    profile.cost_sign = "+"
    with pytest.raises(
        ValidationError, match="Cost sign should be empty for zero cost profiles."
    ):
        profile.clean()

    # Test invalid profile with empty name and non-zero cost
    profile.name = ""
    profile.cost = 10
    profile.cost_sign = "+"
    with pytest.raises(
        ValidationError, match="Standard profiles should have zero cost."
    ):
        profile.clean()

    # Test invalid profile with non-standard profile missing cost sign
    profile.name = "Special"
    profile.cost = 10
    profile.cost_sign = ""
    with pytest.raises(
        ValidationError, match="Non-standard profiles should have a cost sign."
    ):
        profile.clean()

    # Test invalid profile with non-standard profile having incorrect cost sign
    profile.cost_sign = "-"
    with pytest.raises(
        ValidationError, match="Non-standard profiles should have a positive cost sign."
    ):
        profile.clean()

    # Test invalid profile with hyphen in name
    profile.name = "-Special"
    with pytest.raises(ValidationError, match="Name should not start with a hyphen."):
        profile.clean()

    # Test invalid profile with "(Standard)" in name
    profile.name = "(Standard)"
    with pytest.raises(ValidationError, match='Name should not be "\(Standard\)".'):
        profile.clean()

    # Test invalid profile with hyphen in specific fields
    profile.name = "Special"
    profile.cost_sign = "+"
    profile.range_short = "-"
    profile.clean()
    assert profile.range_short == ""

    profile.range_short = "4"
    profile.clean()
    assert profile.range_short == '4"'


@pytest.mark.django_db
def test_equipment_with_cost_2D6X10():
    equipment = ContentEquipment.objects.create(
        name="Random Cost Equipment",
        cost="2D6X10",
    )

    assert equipment.cost == "2D6X10"
    assert equipment.cost_int() == 0
    assert equipment.cost_display() == "2D6X10"
