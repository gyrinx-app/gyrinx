"""
Tests for Equipment List Expansion functionality.
"""

import pytest

from gyrinx.content.models import (
    ContentAttribute,
    ContentAttributeValue,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
)
from gyrinx.content.models import (
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRuleByAttribute,
    ContentEquipmentListExpansionRuleByFighterCategory,
    ContentEquipmentListExpansionRuleByHouse,
    ExpansionRuleInputs,
)
from gyrinx.core.models import List, ListAttributeAssignment
from gyrinx.core.models.list import ListFighter
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
def test_expansion_rule_by_attribute_ignores_archived_assignments():
    """Test that archived ListAttributeAssignments are ignored by expansion rules."""
    # Create attribute and values
    affiliation = ContentAttribute.objects.create(
        name="Affiliation", is_single_select=False
    )
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )
    water_guild = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Water Guild"
    )

    # Create rule that matches Malstrain
    rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    rule.attribute_values.add(malstrain)

    # Create a list with Malstrain affiliation
    house = ContentHouse.objects.create(name="Outcasts")
    gang_list = List.objects.create(name="Test Gang", content_house=house)
    assignment = ListAttributeAssignment.objects.create(
        list=gang_list, attribute_value=malstrain
    )

    # Test match when assignment is active
    inputs = ExpansionRuleInputs(list=gang_list)
    assert rule.match(inputs) is True

    # Archive the assignment directly (bypass save validation)
    ListAttributeAssignment.objects.filter(pk=assignment.pk).update(archived=True)

    # Refresh the assignment object
    assignment.refresh_from_db()

    # Test that rule no longer matches with archived assignment
    assert rule.match(inputs) is False

    # Add a new Water Guild assignment (active)
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=water_guild)

    # Test that rule still doesn't match (has Water Guild, not Malstrain)
    assert rule.match(inputs) is False

    # Unarchive the Malstrain assignment directly
    ListAttributeAssignment.objects.filter(pk=assignment.pk).update(archived=False)

    # Refresh the assignment object
    assignment.refresh_from_db()

    # Now the rule should match again (has active Malstrain assignment)
    assert rule.match(inputs) is True


@pytest.mark.django_db
def test_expansion_rule_by_attribute_any_value_ignores_archived():
    """Test that archived assignments are ignored when matching 'any value' rules."""
    # Create attribute and values (multi-select to allow multiple values)
    affiliation = ContentAttribute.objects.create(
        name="Affiliation", is_single_select=False
    )
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )
    water_guild = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Water Guild"
    )

    # Create rule that matches any affiliation value (no specific values added)
    rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )

    # Create a list
    house = ContentHouse.objects.create(name="Outcasts")
    gang_list = List.objects.create(name="Test Gang", content_house=house)

    # Create an assignment and immediately archive it
    assignment = ListAttributeAssignment.objects.create(
        list=gang_list, attribute_value=malstrain
    )
    ListAttributeAssignment.objects.filter(pk=assignment.pk).update(archived=True)

    # Test that rule doesn't match with only archived assignment
    inputs = ExpansionRuleInputs(list=gang_list)
    assert rule.match(inputs) is False

    # Add an active Water Guild assignment
    water_assignment = ListAttributeAssignment.objects.create(
        list=gang_list, attribute_value=water_guild, archived=False
    )

    # Now rule should match (has an active assignment)
    assert rule.match(inputs) is True

    # Archive the Water Guild assignment too
    ListAttributeAssignment.objects.filter(pk=water_assignment.pk).update(archived=True)

    # Rule shouldn't match when all assignments are archived
    assert rule.match(inputs) is False

    # Unarchive the Malstrain assignment
    ListAttributeAssignment.objects.filter(pk=assignment.pk).update(archived=False)

    # Rule should match again with active assignment
    assert rule.match(inputs) is True


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

    lf_leader = ListFighter.objects.create(
        list=gang_list, content_fighter=leader, name="Leader Fighter"
    )
    lf_champion = ListFighter.objects.create(
        list=gang_list, content_fighter=champion, name="Champion Fighter"
    )
    lf_ganger = ListFighter.objects.create(
        list=gang_list, content_fighter=ganger, name="Ganger Fighter"
    )
    lf_vehicle = ListFighter.objects.create(
        list=gang_list, content_fighter=vehicle, name="Vehicle Fighter"
    )

    # Test match with Leader
    inputs = ExpansionRuleInputs(list=gang_list, fighter=lf_leader)
    assert rule.match(inputs) is True

    # Test match with Champion
    inputs2 = ExpansionRuleInputs(list=gang_list, fighter=lf_champion)
    assert rule.match(inputs2) is True

    # Test non-match with Ganger
    inputs3 = ExpansionRuleInputs(list=gang_list, fighter=lf_ganger)
    assert rule.match(inputs3) is False

    # Test non-match with Vehicle
    inputs4 = ExpansionRuleInputs(list=gang_list, fighter=lf_vehicle)
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

    lf_leader = ListFighter.objects.create(
        list=gang_list, content_fighter=leader, name="Leader Fighter"
    )
    lf_ganger = ListFighter.objects.create(
        list=gang_list, content_fighter=ganger, name="Ganger Fighter"
    )

    # Test: Should apply for Malstrain Leader
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_leader))
        is True
    )

    # Test: Should NOT apply for Malstrain Ganger (wrong fighter category)
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_ganger))
        is False
    )

    # Test: Should NOT apply for non-Malstrain Leader
    gang_list2 = List.objects.create(name="Normal Gang", content_house=outcasts)
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list2, fighter=lf_leader))
        is False
    )


@pytest.mark.django_db
def test_expansion_with_archived_list_attribute_assignment():
    """Test that expansions don't apply when list attributes are archived."""
    # Setup attribute
    affiliation = ContentAttribute.objects.create(
        name="Affiliation", is_single_select=True
    )
    malstrain = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Malstrain Corrupted"
    )

    # Setup equipment
    category = ContentEquipmentCategory.objects.create(name="Special")
    special_item = ContentEquipment.objects.create(
        name="Malstrain Item", category=category, cost=100
    )

    # Create expansion for Malstrain affiliation
    expansion = ContentEquipmentListExpansion.objects.create(name="Malstrain Equipment")

    # Add rule for Malstrain attribute
    attr_rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    attr_rule.attribute_values.add(malstrain)
    expansion.rules.add(attr_rule)

    # Add equipment to expansion
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=special_item,
        cost=75,  # Discounted
    )

    # Create gang with Malstrain affiliation
    house = ContentHouse.objects.create(name="Test House")
    gang_list = List.objects.create(name="Test Gang", content_house=house)
    assignment = ListAttributeAssignment.objects.create(
        list=gang_list, attribute_value=malstrain
    )

    # Create a fighter
    leader = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    lf_leader = ListFighter.objects.create(
        list=gang_list, content_fighter=leader, name="Leader Fighter"
    )

    # Test expansion applies with active assignment
    rule_inputs = ExpansionRuleInputs(list=gang_list, fighter=lf_leader)
    assert expansion.applies_to(rule_inputs) is True

    # Get expansion equipment - should include the special item
    equipment = ContentEquipmentListExpansion.get_expansion_equipment(rule_inputs)
    equipment_names = list(equipment.values_list("name", flat=True))
    assert "Malstrain Item" in equipment_names

    # Archive the assignment
    ListAttributeAssignment.objects.filter(pk=assignment.pk).update(archived=True)

    # Clear cached property and refresh the list
    if "active_attributes_cached" in gang_list.__dict__:
        del gang_list.__dict__["active_attributes_cached"]
    gang_list.refresh_from_db()

    # Create new rule_inputs with refreshed list
    rule_inputs = ExpansionRuleInputs(list=gang_list, fighter=lf_leader)

    # Test expansion no longer applies with archived assignment
    assert expansion.applies_to(rule_inputs) is False

    # Get expansion equipment - should be empty now
    equipment = ContentEquipmentListExpansion.get_expansion_equipment(rule_inputs)
    assert equipment.count() == 0


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

    # Create ListFighter instances
    lf_leader = ListFighter.objects.create(
        list=gang_list, content_fighter=leader, name="Leader Fighter"
    )
    lf_champion = ListFighter.objects.create(
        list=gang_list, content_fighter=champion, name="Champion Fighter"
    )
    lf_ganger = ListFighter.objects.create(
        list=gang_list, content_fighter=ganger, name="Ganger Fighter"
    )

    # Test expansion applies correctly
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_leader))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_champion))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_ganger))
        is False
    )

    # Test getting expansion equipment
    rule_inputs = ExpansionRuleInputs(list=gang_list, fighter=lf_leader)
    applicable_expansions = ContentEquipmentListExpansion.get_applicable_expansions(
        rule_inputs
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

    # Create ListFighter instances
    lf_leader = ListFighter.objects.create(
        list=gang_list, content_fighter=leader, name="Leader Fighter"
    )
    lf_ganger = ListFighter.objects.create(
        list=gang_list, content_fighter=ganger, name="Ganger Fighter"
    )
    lf_juve = ListFighter.objects.create(
        list=gang_list, content_fighter=juve, name="Juve Fighter"
    )

    # Test expansion applies correctly
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_leader))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_ganger))
        is True
    )
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=gang_list, fighter=lf_juve))
        is False
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

    # Create ListFighter instances
    lf_vehicle = ListFighter.objects.create(
        list=delaque_gang, content_fighter=vehicle, name="Vehicle Fighter"
    )
    lf_leader = ListFighter.objects.create(
        list=delaque_gang, content_fighter=leader, name="Leader Fighter"
    )
    lf_goliath_vehicle = ListFighter.objects.create(
        list=goliath_gang, content_fighter=vehicle, name="Goliath Vehicle Fighter"
    )

    # Test expansion applies correctly
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=delaque_gang, fighter=lf_vehicle))
        is True
    )  # Delaque vehicle
    assert (
        expansion.applies_to(ExpansionRuleInputs(list=delaque_gang, fighter=lf_leader))
        is False
    )  # Not a vehicle
    assert (
        expansion.applies_to(
            ExpansionRuleInputs(list=goliath_gang, fighter=lf_goliath_vehicle)
        )
        is False
    )  # Wrong house

    # Test getting expansion equipment for Delaque vehicle
    rule_inputs = ExpansionRuleInputs(list=delaque_gang, fighter=lf_vehicle)
    equipment = ContentEquipmentListExpansion.get_expansion_equipment(rule_inputs)
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
    rule_inputs = ExpansionRuleInputs(list=gang_list)
    equipment = ContentEquipmentListExpansion.get_expansion_equipment(rule_inputs)
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
    rule_inputs = ExpansionRuleInputs(list=gang_list)
    applicable = ContentEquipmentListExpansion.get_applicable_expansions(rule_inputs)
    assert len(applicable) == 2

    # Get expansion equipment - should get both expansions' items
    equipment_qs = ContentEquipmentListExpansion.get_expansion_equipment(rule_inputs)

    # The equipment should appear once, with one of the costs
    # (implementation detail - currently takes the last one found)
    assert equipment_qs.count() == 1


@pytest.mark.django_db
def test_with_expansion_cost_for_fighter():
    """Test the with_expansion_cost_for_fighter queryset method."""
    from gyrinx.content.models import ContentFighterEquipmentListItem
    from gyrinx.content.models import ExpansionRuleInputs

    # Setup
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(name="Weapons")

    # Create equipment with base costs
    item1 = ContentEquipment.objects.create(name="Sword", category=category, cost=50)
    item2 = ContentEquipment.objects.create(name="Axe", category=category, cost=100)
    item3 = ContentEquipment.objects.create(name="Bow", category=category, cost=75)

    # Create a content fighter
    fighter = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )

    # Create normal equipment list item with cost override for item1
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter,
        equipment=item1,
        cost=40,  # Discounted from 50
    )

    # Create expansion with fighter category rule
    expansion = ContentEquipmentListExpansion.objects.create(name="Leader Expansion")
    fighter_rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[FighterCategoryChoices.LEADER]
    )
    expansion.rules.add(fighter_rule)

    # Add items to expansion with cost overrides
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item1,
        cost=30,  # Even better discount from expansion
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item2,
        cost=80,  # Discounted from 100
    )
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item3,
        cost=None,  # Use base cost
    )

    # Create gang and list fighter
    gang_list = List.objects.create(name="Test Gang", content_house=house)
    list_fighter = ListFighter.objects.create(
        list=gang_list, content_fighter=fighter, name="Test Leader"
    )

    # Create rule inputs for the expansion check
    rule_inputs = ExpansionRuleInputs(list=gang_list, fighter=list_fighter)

    # Get equipment with expansion costs
    equipment_qs = ContentEquipment.objects.filter(
        id__in=[item1.id, item2.id, item3.id]
    ).with_expansion_cost_for_fighter(fighter, rule_inputs)

    # Convert to dict for easier testing
    equipment_dict = {eq.name: eq for eq in equipment_qs}

    # Test annotations
    assert len(equipment_dict) == 3

    # Item1: Has both equipment list cost (40) and expansion cost (30)
    # Should use expansion cost as it takes priority
    assert equipment_dict["Sword"].equipment_list_cost == 40
    assert equipment_dict["Sword"].expansion_cost == 30
    assert equipment_dict["Sword"].cost_for_fighter == 30  # Expansion wins
    assert equipment_dict["Sword"].from_expansion is True

    # Item2: Only has expansion cost (80), no equipment list cost
    assert equipment_dict["Axe"].equipment_list_cost is None
    assert equipment_dict["Axe"].expansion_cost == 80
    assert equipment_dict["Axe"].cost_for_fighter == 80
    assert equipment_dict["Axe"].from_expansion is True

    # Item3: Has expansion but with null cost, should use base cost
    assert equipment_dict["Bow"].equipment_list_cost is None
    assert equipment_dict["Bow"].expansion_cost is None
    assert equipment_dict["Bow"].cost_for_fighter == 75  # Base cost
    assert equipment_dict["Bow"].from_expansion is True


@pytest.mark.django_db
def test_with_expansion_cost_for_fighter_no_expansion():
    """Test with_expansion_cost_for_fighter when no expansion applies."""
    from gyrinx.content.models import ContentFighterEquipmentListItem
    from gyrinx.content.models import ExpansionRuleInputs

    # Setup
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(name="Weapons")

    # Create equipment
    item1 = ContentEquipment.objects.create(name="Mace", category=category, cost=60)

    # Create a content fighter
    fighter = ContentFighter.objects.create(
        type="Ganger", category=FighterCategoryChoices.GANGER
    )

    # Create normal equipment list item with cost override
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter,
        equipment=item1,
        cost=55,  # Discounted
    )

    # Create expansion that won't apply (different fighter category)
    expansion = ContentEquipmentListExpansion.objects.create(name="Leader Only")
    fighter_rule = ContentEquipmentListExpansionRuleByFighterCategory.objects.create(
        fighter_categories=[FighterCategoryChoices.LEADER]  # Not GANGER
    )
    expansion.rules.add(fighter_rule)

    # Add item to expansion
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=item1,
        cost=40,  # Won't be used
    )

    # Create gang and list fighter
    gang_list = List.objects.create(name="Test Gang", content_house=house)
    list_fighter = ListFighter.objects.create(
        list=gang_list, content_fighter=fighter, name="Test Ganger"
    )

    # Create rule inputs
    rule_inputs = ExpansionRuleInputs(list=gang_list, fighter=list_fighter)

    # Get equipment with expansion costs
    equipment_qs = ContentEquipment.objects.filter(
        id=item1.id
    ).with_expansion_cost_for_fighter(fighter, rule_inputs)

    equipment = equipment_qs.first()

    # Test annotations - expansion shouldn't apply
    assert equipment.equipment_list_cost == 55
    assert equipment.expansion_cost is None  # No expansion applies
    assert equipment.cost_for_fighter == 55  # Uses equipment list cost
    assert equipment.from_expansion is False


@pytest.mark.django_db
def test_edit_list_fighter_equipment_view_includes_expansions():
    """Test that the edit_list_fighter_equipment view includes expansion equipment."""
    from django.contrib.auth import get_user_model
    from django.test import Client
    from django.urls import reverse

    from gyrinx.content.models import ContentFighterEquipmentListItem

    User = get_user_model()

    # Setup test data
    user = User.objects.create_user(username="testuser", password="testpass")
    client = Client()
    client.login(username="testuser", password="testpass")

    # Create house and list
    house = ContentHouse.objects.create(name="Test House")
    gang_list = List.objects.create(name="Test Gang", content_house=house, owner=user)

    # Create attribute and value for expansion
    affiliation = ContentAttribute.objects.create(name="Affiliation")
    special_guild = ContentAttributeValue.objects.create(
        attribute=affiliation, name="Special Guild"
    )

    # Assign attribute to the gang
    ListAttributeAssignment.objects.create(
        list=gang_list, attribute_value=special_guild
    )

    # Create equipment category for gear (non-weapons)
    gear_cat = ContentEquipmentCategory.objects.create(
        name="Test Gear Category", group="Gear"
    )

    # Create gear equipment
    normal_armor = ContentEquipment.objects.create(
        name="Normal Armor", category=gear_cat, cost=30
    )
    expansion_shield = ContentEquipment.objects.create(
        name="Expansion Shield", category=gear_cat, cost=75
    )

    # Create content fighter
    leader_fighter = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )

    # Add normal armor to fighter's equipment list
    ContentFighterEquipmentListItem.objects.create(
        fighter=leader_fighter,
        equipment=normal_armor,
        cost=25,  # Discounted
    )

    # Create expansion with attribute rule
    expansion = ContentEquipmentListExpansion.objects.create(
        name="Special Guild Equipment"
    )

    attr_rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=affiliation
    )
    attr_rule.attribute_values.add(special_guild)

    expansion.rules.add(attr_rule)

    # Add expansion item
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion,
        equipment=expansion_shield,
        cost=60,  # Discounted from 75
    )

    # Create list fighter
    list_fighter = ListFighter.objects.create(
        list=gang_list, content_fighter=leader_fighter, name="Test Leader", owner=user
    )

    # Test gear view with equipment list filter
    gear_url = reverse(
        "core:list-fighter-gear-edit", args=[gang_list.id, list_fighter.id]
    )
    response = client.get(gear_url + "?filter=equipment_list")

    assert response.status_code == 200

    # Check gear includes both equipment list and expansion items
    equipment = response.context["equipment"]
    equipment_names = [eq.name for eq in equipment]

    # Both should appear - one from equipment list, one from expansion
    assert "Normal Armor" in equipment_names  # From equipment list
    assert "Expansion Shield" in equipment_names  # From expansion

    # Check that costs are correctly set
    equipment_dict = {eq.name: eq for eq in equipment}
    assert (
        equipment_dict["Normal Armor"].cost_for_fighter == 25
    )  # Equipment list override
    assert (
        equipment_dict["Expansion Shield"].cost_for_fighter == 60
    )  # Expansion override


@pytest.mark.django_db
def test_has_house_additional_gear_with_expansions():
    """Test that has_house_additional_gear includes expansion equipment."""
    # Setup
    house = ContentHouse.objects.create(name="Test House")

    # Create categories - one restricted, one not
    restricted_cat = ContentEquipmentCategory.objects.create(
        name="Restricted Category", group="Gear"
    )
    restricted_cat.restricted_to.add(house)

    # Create a normal category for contrast (not used but validates the setup)
    ContentEquipmentCategory.objects.create(name="Normal Category", group="Gear")

    # Create equipment in the restricted category
    restricted_equipment = ContentEquipment.objects.create(
        name="Restricted Item", category=restricted_cat, cost=100
    )

    # Create gang and fighter
    gang_list = List.objects.create(name="Test Gang", content_house=house)

    content_fighter = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    content_fighter.house = house
    content_fighter.save()

    list_fighter = ListFighter.objects.create(
        list=gang_list, content_fighter=content_fighter, name="Test Leader"
    )

    # Test 1: Fighter has house additional gear from restricted categories
    assert list_fighter.has_house_additional_gear is True

    # Test 2: Fighter without restricted categories but with expansion
    house2 = ContentHouse.objects.create(name="House Without Restrictions")
    gang_list2 = List.objects.create(name="Gang 2", content_house=house2)

    content_fighter2 = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    content_fighter2.house = house2
    content_fighter2.save()

    list_fighter2 = ListFighter.objects.create(
        list=gang_list2, content_fighter=content_fighter2, name="Leader 2"
    )

    # Initially no house additional gear
    assert list_fighter2.has_house_additional_gear is False

    # Add attribute and expansion
    attribute = ContentAttribute.objects.create(name="Test Attribute")
    attr_value = ContentAttributeValue.objects.create(
        attribute=attribute, name="Test Value"
    )
    ListAttributeAssignment.objects.create(list=gang_list2, attribute_value=attr_value)

    # Create expansion with equipment
    expansion = ContentEquipmentListExpansion.objects.create(name="Test Expansion")

    rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=attribute
    )
    rule.attribute_values.add(attr_value)
    expansion.rules.add(rule)

    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion, equipment=restricted_equipment, cost=80
    )

    # Refresh the list to ensure it has the latest attribute assignments
    gang_list2 = List.objects.with_related_data(with_fighters=True).get(
        id=gang_list2.id
    )
    list_fighter2 = ListFighter.objects.with_related_data().get(id=list_fighter2.id)

    # Now should have house additional gear from expansion
    assert list_fighter2.has_house_additional_gear is True


@pytest.mark.django_db
def test_has_house_additional_gear_with_actual_assigned_gear():
    """Test that has_house_additional_gear returns True when fighter has assigned gear from restricted categories."""
    # Create two houses
    house1 = ContentHouse.objects.create(name="House One")
    house2 = ContentHouse.objects.create(name="House Two")

    # Create a restricted category (restricted to house2, not house1)
    restricted_cat = ContentEquipmentCategory.objects.create(
        name="Special Gear", group="Gear"
    )
    restricted_cat.restricted_to.add(house2)

    # Create equipment in the restricted category
    special_equipment = ContentEquipment.objects.create(
        name="Special Item", category=restricted_cat, cost=100
    )

    # Create a gang in house1 (which doesn't have access to the category normally)
    gang_list = List.objects.create(name="House One Gang", content_house=house1)

    content_fighter = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    content_fighter.house = house1
    content_fighter.save()

    list_fighter = ListFighter.objects.create(
        list=gang_list, content_fighter=content_fighter, name="Test Leader"
    )

    # Initially should not have house additional gear (house1 has no restricted categories)
    assert list_fighter.has_house_additional_gear is False

    # Now assign the special equipment to this fighter
    # (This simulates equipment being added through special rules, rewards, etc.)
    from gyrinx.core.models.list import ListFighterEquipmentAssignment

    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter, content_equipment=special_equipment
    )

    # Clear cached properties
    if "has_house_additional_gear" in list_fighter.__dict__:
        del list_fighter.__dict__["has_house_additional_gear"]
    if "assignments_cached" in list_fighter.__dict__:
        del list_fighter.__dict__["assignments_cached"]

    # Should now return True because the fighter has gear from a restricted category
    assert list_fighter.has_house_additional_gear is True


@pytest.mark.django_db
def test_house_additional_gearline_display_with_expansions():
    """Test that house_additional_gearline_display includes expansion categories."""
    # Setup
    house = ContentHouse.objects.create(name="Test House")

    # Create categories
    restricted_cat = ContentEquipmentCategory.objects.create(
        name="House Restricted", group="Gear"
    )
    restricted_cat.restricted_to.add(house)

    expansion_cat = ContentEquipmentCategory.objects.create(
        name="Expansion Category", group="Gear"
    )
    expansion_cat.restricted_to.add(house)  # Make it restricted

    visible_only_cat = ContentEquipmentCategory.objects.create(
        name="Visible Only If In List",
        group="Gear",
        visible_only_if_in_equipment_list=True,
    )
    visible_only_cat.restricted_to.add(house)

    # Create equipment
    # House equipment (created for completeness, not directly tested)
    ContentEquipment.objects.create(name="House Item", category=restricted_cat, cost=50)
    expansion_equipment = ContentEquipment.objects.create(
        name="Expansion Item", category=expansion_cat, cost=100
    )
    visible_equipment = ContentEquipment.objects.create(
        name="Visible Item", category=visible_only_cat, cost=75
    )

    # Create gang and fighter
    gang_list = List.objects.create(name="Test Gang", content_house=house)

    content_fighter = ContentFighter.objects.create(
        type="Leader", category=FighterCategoryChoices.LEADER
    )
    content_fighter.house = house
    content_fighter.save()

    list_fighter = ListFighter.objects.create(
        list=gang_list, content_fighter=content_fighter, name="Test Leader"
    )

    # Test 1: Basic house restricted category appears
    gearlines = list_fighter.house_additional_gearline_display
    assert any(gl["category"] == "House Restricted" for gl in gearlines)

    # Test 2: visible_only_if_in_equipment_list doesn't appear without equipment
    assert not any(gl["category"] == "Visible Only If In List" for gl in gearlines)

    # Add attribute and expansion
    attribute = ContentAttribute.objects.create(name="Gang Attribute")
    attr_value = ContentAttributeValue.objects.create(
        attribute=attribute, name="Special"
    )
    ListAttributeAssignment.objects.create(list=gang_list, attribute_value=attr_value)

    # Create expansion with equipment in expansion_cat
    expansion = ContentEquipmentListExpansion.objects.create(name="Test Expansion")

    rule = ContentEquipmentListExpansionRuleByAttribute.objects.create(
        attribute=attribute
    )
    rule.attribute_values.add(attr_value)
    expansion.rules.add(rule)

    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion, equipment=expansion_equipment, cost=80
    )

    # Also add visible equipment to expansion
    ContentEquipmentListExpansionItem.objects.create(
        expansion=expansion, equipment=visible_equipment, cost=60
    )

    # Refresh the list to ensure it has the latest attribute assignments
    gang_list = List.objects.with_related_data(with_fighters=True).get(id=gang_list.id)
    list_fighter = ListFighter.objects.with_related_data().get(id=list_fighter.id)

    # Test 3: Expansion category now appears
    gearlines = list_fighter.house_additional_gearline_display
    assert any(gl["category"] == "Expansion Category" for gl in gearlines)

    # Test 4: visible_only_if_in_equipment_list appears because expansion provides equipment
    assert any(gl["category"] == "Visible Only If In List" for gl in gearlines)

    # Test 5: Check filter flags
    for gl in gearlines:
        if gl["category"] == "Visible Only If In List":
            assert gl["filter"] == "equipment-list"
        elif gl["category"] in ["House Restricted", "Expansion Category"]:
            assert gl["filter"] == "all"
