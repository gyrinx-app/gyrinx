"""
Tests for Equipment List Expansion functionality.
"""

import pytest

from gyrinx.content.models import (
    ContentAttribute,
    ContentAttributeValue,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRuleByAttribute,
    ContentEquipmentListExpansionRuleByFighterCategory,
    ContentEquipmentListExpansionRuleByHouse,
    ContentFighter,
    ContentHouse,
    ExpansionRuleInputs,
)
from gyrinx.core.models import List, ListAttributeAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_expansion_rule_by_attribute_with_specific_values():
    """Test attribute rule matching with specific values."""
    # Create attribute and values
    affiliation = ContentAttribute.objects.create(name="Affiliation")
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )
    water_guild = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Water Guild"
    )

    # Create a list with Malstrain affiliation
    house = ContentHouse.objects.create(name="Outcasts")
    gang_list = List.objects.create(name="Test Gang", content_house=house)
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=malstrain)

    # Create rule that matches Malstrain
    rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    rule.attribute_values.add(malstrain)

    # Test match
    inputs = ExpansionRuleInputs(list=gang_list)
    assert rule.match(inputs) is True

    # Test non-match with Water Guild list
    gang_list2 = List.objects.create(name="Water Gang", content_house=house)
    ListAttributeAssignment.objects.create(list=gang_list2, attribute_value=water_guild)
    inputs2 = ExpansionRuleInputs(list=gang_list2)
    assert rule.match(inputs2) is False

    # Test non-match with no affiliation
    gang_list3 = List.objects.create(name="No Affiliation Gang", content_house=house)
    inputs3 = ExpansionRuleInputs(list=gang_list3)
    assert rule.match(inputs3) is False


@pytest.mark.django_db
def test_expansion_rule_by_attribute_any_value():
    """Test attribute rule matching with any value (empty attribute_values)."""
    # Create attribute and values
    affiliation = ContentAttribute.objects.create(name="Affiliation")
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )
    water_guild = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Water Guild"
    )

    # Create rule that matches any affiliation value
    rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    # No attribute values added - should match any value

    # Test match with Malstrain
    house = ContentHouse.objects.create(name="Outcasts")
    gang_list = List.objects.create(name="Malstrain Gang", content_house=house)
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=malstrain)
    inputs = ExpansionRuleInputs(list=gang_list)
    assert rule.match(inputs) is True

    # Test match with Water Guild
    gang_list2 = List.objects.create(name="Water Gang", content_house=house)
    ListAttributeAssignment.objects.create(list=gang_list2, attribute_value=water_guild)
    inputs2 = ExpansionRuleInputs(list=gang_list2)
    assert rule.match(inputs2) is True

    # Test non-match with no affiliation
    gang_list3 = List.objects.create(name="No Affiliation", content_house=house)
    inputs3 = ExpansionRuleInputs(list=gang_list3)
    assert rule.match(inputs3) is False


@pytest.mark.django_db
def test_expansion_rule_by_house():
    """Test house rule matching."""
    # Create houses
    delaque = ContentHouse.objects.create(name="Delaque")
    goliath = ContentHouse.objects.create(name="Goliath")

    # Create rule for Delaque
    rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=delaque)

    # Test match with Delaque gang
    gang_list = List.objects.create(name="Delaque Gang", content_house=delaque)
    inputs = ExpansionRuleInputs(list=gang_list)
    assert rule.match(inputs) is True

    # Test non-match with Goliath gang
    gang_list2 = List.objects.create(name="Goliath Gang", content_house=goliath)
    inputs2 = ExpansionRuleInputs(list=gang_list2)
    assert rule.match(inputs2) is False


@pytest.mark.django_db
def test_expansion_rule_by_fighter_category():
    """Test fighter category rule matching."""
    # Create fighters
    leader = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    champion = ContentFighter.objects.create(
        type="Champion", category=FighterCategoryChoices.CHAMPION
    )
    ganger = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER
    )
    vehicle = ContentFighter.objects.create(
        type="Vehicle", category=FighterCategoryChoices.VEHICLE
    )

    # Create rule for Leader and Champion
    rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[
            FighterCategoryChoices.LEADER,
            FighterCategoryChoices.CHAMPION,
        ]
    )

    # Create a dummy list
    house = ContentHouse.objects.create(name="Test House")
    gang_list = List.objects.create(name="Test Gang", content_house=house)

    # Test match with Leader
    inputs = ExpansionRuleInputs(list=gang_list, fighter=leader)
    assert rule.match(inputs) is True

    # Test match with Champion
    inputs2 = ExpansionRuleInputs(list=gang_list, fighter=champion)
    assert rule.match(inputs2) is True

    # Test non-match with Ganger
    inputs3 = ExpansionRuleInputs(list=gang_list, fighter=ganger)
    assert rule.match(inputs3) is False

    # Test non-match with Vehicle
    inputs4 = ExpansionRuleInputs(list=gang_list, fighter=vehicle)
    assert rule.match(inputs4) is False

    # Test non-match with no fighter
    inputs5 = ExpansionRuleInputs(list=gang_list, fighter=None)
    assert rule.match(inputs5) is False


@pytest.mark.django_db
def test_expansion_applies_with_multiple_rules():
    """Test expansion with multiple rules (AND logic)."""
    # Create attribute and house
    affiliation = ContentAttribute.objects.create(name="Affiliation")
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )
    outcasts = ContentHouse.objects.create(name="Outcasts")

    # Create expansion with two rules
    expansion = ContentEquipmentListExpansion.objects.create(
        name="Malstrain Outcasts Leaders"
    )

    # Rule 1: Must be Malstrain Corrupted
    attr_rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    attr_rule.attribute_values.add(malstrain)

    # Rule 2: Must be Leader or Champion
    fighter_rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[
            FighterCategoryChoices.LEADER,
            FighterCategoryChoices.CHAMPION,
        ]
    )

    expansion.rules.add(attr_rule, fighter_rule)

    # Create gang with Malstrain affiliation
    gang_list = List.objects.create(name="Malstrain Gang", content_house=outcasts)
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=malstrain)

    # Create fighters
    leader = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    ganger = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER
    )

    # Test: Should apply for Malstrain Leader
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=leader))
        is True
    )

    # Test: Should NOT apply for Malstrain Ganger (wrong fighter category)
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=ganger))
        is False
    )

    # Test: Should NOT apply for non-Malstrain Leader
    gang_list2 = List.objects.create(name="Normal Gang", content_house=outcasts)
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list2, fighter=leader))
        is False
    )


@pytest.mark.django_db
def test_example_1_malstrain_corrupted():
    """
    Example 1: Malstrain Corrupted affiliation
    - Leaders and Champions get special equipment
    """
    # Setup attribute
    affiliation = ContentAttribute.objects.create(name="Affiliation")
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )

    # Setup equipment
    category = ContentEquipmentCategory.objects.create(name="Psyker")
    tyremite = ContentEquipment.objects.create(
        name="Malstrain Tyremite", category=category, cost=50
    )
    psychic_power = ContentEquipment.objects.create(
        name="Non-sanctioned Psyker", category=category, cost=30
    )

    # Create expansion for Malstrain Leaders/Champions
    expansion = ContentEquipmentListExpansion.objects.create(
        name="Malstrain Leader/Champion Equipment"
    )

    # Add rules
    attr_rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    attr_rule.attribute_values.add(malstrain)

    fighter_rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[
            FighterCategoryChoices.LEADER,
            FighterCategoryChoices.CHAMPION,
        ]
    )

    expansion.rules.add(attr_rule, fighter_rule)

    # Add equipment to expansion
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=tyremite,
        cost=None,  # Use base cost
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=psychic_power,
        cost=30,  # Override cost
    )

    # Create Malstrain gang
    house = ContentHouse.objects.create(name="Outcasts")
    gang_list = List.objects.create(name="Malstrain Gang", content_house=house)
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=malstrain)

    # Create fighters
    leader = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    champion = ContentFighter.objects.create(
        type="Champion", category=FighterCategoryChoices.CHAMPION
    )
    ganger = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER
    )

    # Test expansion applies correctly
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=leader))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=champion))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=ganger))
        is False
    )

    # Test getting expansion equipment
    applicable_expansions = ContentEquipmentListExpansion.get_applicable_expansions(
        gang_list, leader
    )
    assert len(applicable_expansions) == 1
    assert applicable_expansions[0] == expansion


@pytest.mark.django_db
def test_example_2_water_guild_outcasts():
    """
    Example 2: Water Guild Outcasts
    - Leaders, Champions, and Gangers get access to special equipment
    """
    # Setup attribute
    affiliation = ContentAttribute.objects.create(name="Affiliation")
    water_guild = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Water Guild"
    )

    # Setup equipment
    category = ContentEquipmentCategory.objects.create(name="Special")
    water_blade = ContentEquipment.objects.create(
        name="Water Blade", category=category, cost=100
    )
    aqua_respirator = ContentEquipment.objects.create(
        name="Aqua Respirator", category=category, cost=50
    )

    # Create expansion for Water Guild
    expansion = ContentEquipmentListExpansion.objects.create(
        name="Water Guild Equipment"
    )

    # Add rules
    attr_rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    attr_rule.attribute_values.add(water_guild)

    fighter_rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[
            FighterCategoryChoices.LEADER,
            FighterCategoryChoices.CHAMPION,
            FighterCategoryChoices.GANGER,
        ]
    )

    expansion.rules.add(attr_rule, fighter_rule)

    # Add equipment to expansion with cost overrides
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=water_blade,
        cost=75,  # Discounted
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=aqua_respirator,
        cost=None,  # Base cost
    )

    # Create Water Guild gang
    house = ContentHouse.objects.create(name="Outcasts")
    gang_list = List.objects.create(name="Water Guild Gang", content_house=house)
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=water_guild)

    # Create fighters
    leader = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    ganger = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER
    )
    juve = ContentFighter.objects.create(
        type="Juve", category=FighterCategoryChoices.JUVE
    )

    # Test expansion applies correctly
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=leader))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=ganger))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=juve)) is False
    )  # Juves don't get access


@pytest.mark.django_db
def test_example_3_delaque_vehicles():
    """
    Example 3: Delaque Vehicles
    - Vehicles in Delaque gangs get special equipment
    """
    # Setup house
    delaque = ContentHouse.objects.create(name="Delaque")
    goliath = ContentHouse.objects.create(name="Goliath")

    # Setup equipment
    category = ContentEquipmentCategory.objects.create(name="Vehicle")
    shadow_projector = ContentEquipment.objects.create(
        name="Shadow Projector", category=category, cost=200
    )
    ghost_drive = ContentEquipment.objects.create(
        name="Ghost Drive", category=category, cost=150
    )

    # Create expansion for Delaque vehicles
    expansion = ContentEquipmentListExpansion.objects.create(
        name="Delaque Vehicle Equipment"
    )

    # Add rules
    house_rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=delaque)

    fighter_rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[FighterCategoryChoices.VEHICLE]
    )

    expansion.rules.add(house_rule, fighter_rule)

    # Add equipment to expansion
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion, equipment=shadow_projector, cost=None
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=ghost_drive,
        cost=100,  # Discounted
    )

    # Create Delaque gang
    delaque_gang = List.objects.create(name="Delaque Gang", content_house=delaque)

    # Create Goliath gang
    goliath_gang = List.objects.create(name="Goliath Gang", content_house=goliath)

    # Create fighters
    vehicle = ContentFighter.objects.create(
        type="Ridge Runner", category=FighterCategoryChoices.VEHICLE
    )
    leader = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )

    # Test expansion applies correctly
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=delaque_gang, fighter=vehicle))
        is True
    )  # Delaque vehicle
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=delaque_gang, fighter=leader))
        is False
    )  # Not a vehicle
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=goliath_gang, fighter=vehicle))
        is False
    )  # Wrong house

    # Test getting expansion equipment for Delaque vehicle
    equipment = ContentEquipmentListExpansion.get_expansion_equipment(
        delaque_gang, vehicle
    )
    equipment_names = list(equipment.values_list("name", flat=True))
    assert "Shadow Projector" in equipment_names
    assert "Ghost Drive" in equipment_names


@pytest.mark.django_db
def test_get_expansion_equipment_with_cost_overrides():
    """Test that get_expansion_equipment returns correct cost overrides."""
    # Setup
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(name="Test")

    # Create equipment with base costs
    item1 = ContentEquipment.objects.create(name="Item 1", category=category, cost=100)
    item2 = ContentEquipment.objects.create(name="Item 2", category=category, cost=200)
    item3 = ContentEquipment.objects.create(name="Item 3", category=category, cost=300)

    # Create expansion with house rule
    expansion = ContentEquipmentListExpansion.objects.create(name="Test Expansion")
    house_rule = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion.rules.add(house_rule)

    # Add items with different cost scenarios
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item1,
        cost=50,  # Override to 50
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item2,
        cost=None,  # Use base cost
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item3,
        cost=0,  # Free!
    )

    # Create gang
    gang_list = List.objects.create(name="Test Gang", content_house=house)

    # Get expansion equipment
    equipment = ContentEquipmentListExpansion.get_expansion_equipment(gang_list)
    equipment_dict = {eq.name: eq for eq in equipment}

    # Check equipment is returned
    assert len(equipment_dict) == 3

    # Check cost overrides
    assert equipment_dict["Item 1"].expansion_cost_override == 50
    assert equipment_dict["Item 2"].expansion_cost_override == 200  # Base cost
    assert equipment_dict["Item 3"].expansion_cost_override == 0


@pytest.mark.django_db
def test_multiple_expansions_for_same_equipment():
    """Test when multiple expansions provide the same equipment."""
    # Setup
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(name="Test")
    equipment = ContentEquipment.objects.create(
        name="Shared Item", category=category, cost=100
    )

    # Create two expansions that both provide the same equipment
    expansion1 = ContentEquipmentListExpansion.objects.create(name="Expansion 1")
    expansion2 = ContentEquipmentListExpansion.objects.create(name="Expansion 2")

    # Both use house rule
    house_rule1 = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    house_rule2 = ContentEquipmentListExpansionRuleByHouse.objects.create(house=house)
    expansion1.rules.add(house_rule1)
    expansion2.rules.add(house_rule2)

    # Add same equipment with different costs
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion1, equipment=equipment, cost=75
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion2,
        equipment=equipment,
        cost=50,  # Better deal
    )

    # Create gang
    gang_list = List.objects.create(name="Test Gang", content_house=house)

    # Get applicable expansions
    applicable = ContentEquipmentListExpansion.get_applicable_expansions(gang_list)
    assert len(applicable) == 2

    # Get expansion equipment - should get both expansions' items
    equipment_qs = ContentEquipmentListExpansion.get_expansion_equipment(gang_list)

    # The equipment should appear once, with one of the costs
    # (implementation detail - currently takes the last one found)
    assert equipment_qs.count() == 1
