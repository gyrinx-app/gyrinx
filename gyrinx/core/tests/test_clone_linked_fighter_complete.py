"""
Tests for complete cloning of linked fighters with all attributes.
"""

import pytest

from gyrinx.content.models import (
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
    ContentHouseAdditionalRule,
    ContentHouseAdditionalRuleTree,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models.list import (
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_clone_linked_fighter_with_skills_and_rules(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """
    Test that when cloning a list, skills and rules on linked fighters are also cloned.
    """
    # Setup
    house = make_content_house("Test House")

    # Create the main fighter
    gang_member_cf = make_content_fighter(
        type="Gang Member",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create a vehicle fighter that will be auto-generated
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=200,
    )

    # Create equipment that generates the vehicle fighter
    vehicle_equipment = make_equipment(
        "Vehicle Key",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=150,
    )

    # Link the vehicle fighter to the equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_cf,
    )

    # Create skills and rules
    skill_category = ContentSkillCategory.objects.create(
        name="Vehicle Skills", restricted=False
    )
    skill1 = ContentSkill.objects.create(name="Fast Driver", category=skill_category)
    skill2 = ContentSkill.objects.create(
        name="Expert Mechanic", category=skill_category
    )

    # Create additional rules (house-specific)
    rule_tree = ContentHouseAdditionalRuleTree.objects.create(
        house=house, name="Vehicle Rules"
    )
    additional_rule1 = ContentHouseAdditionalRule.objects.create(
        tree=rule_tree, name="Armored"
    )
    additional_rule2 = ContentHouseAdditionalRule.objects.create(
        tree=rule_tree, name="All-Terrain"
    )

    # Create custom and disabled rules (generic)
    custom_rule = ContentRule.objects.create(name="Turbo Boost")
    disabled_rule = ContentRule.objects.create(name="Fragile")

    # Create the list and add the gang member
    original_list = make_list("Original List", content_house=house, owner=user)
    gang_member_lf = make_list_fighter(
        original_list, "Gang Member", content_fighter=gang_member_cf, owner=user
    )

    # Assign the vehicle equipment to the gang member
    vehicle_assignment = ListFighterEquipmentAssignment(
        list_fighter=gang_member_lf,
        content_equipment=vehicle_equipment,
    )
    vehicle_assignment.save()

    # Get the auto-created vehicle
    vehicle_lf = vehicle_assignment.linked_fighter
    assert vehicle_lf is not None

    # Add skills and rules to the vehicle
    vehicle_lf.skills.add(skill1, skill2)
    vehicle_lf.additional_rules.add(additional_rule1, additional_rule2)
    vehicle_lf.custom_rules.add(custom_rule)
    vehicle_lf.disabled_rules.add(disabled_rule)

    # Verify the vehicle has the skills and rules
    assert vehicle_lf.skills.count() == 2
    assert vehicle_lf.additional_rules.count() == 2
    assert vehicle_lf.custom_rules.count() == 1
    assert vehicle_lf.disabled_rules.count() == 1

    # Clone the list
    cloned_list = original_list.clone(name="Cloned List")

    # Find the cloned vehicle
    cloned_gang_member = (
        cloned_list.fighters().filter(content_fighter=gang_member_cf).first()
    )
    cloned_vehicle_assignment = (
        cloned_gang_member._direct_assignments()
        .filter(content_equipment=vehicle_equipment)
        .first()
    )
    cloned_vehicle = cloned_vehicle_assignment.linked_fighter

    # THESE SHOULD PASS: The cloned vehicle should have the same skills and rules
    assert cloned_vehicle.skills.count() == 2, (
        f"Expected cloned vehicle to have 2 skills, "
        f"but found {cloned_vehicle.skills.count()}"
    )
    assert set(cloned_vehicle.skills.all()) == {skill1, skill2}

    assert cloned_vehicle.additional_rules.count() == 2, (
        f"Expected cloned vehicle to have 2 additional rules, "
        f"but found {cloned_vehicle.additional_rules.count()}"
    )
    assert set(cloned_vehicle.additional_rules.all()) == {
        additional_rule1,
        additional_rule2,
    }

    assert cloned_vehicle.custom_rules.count() == 1, (
        f"Expected cloned vehicle to have 1 custom rule, "
        f"but found {cloned_vehicle.custom_rules.count()}"
    )
    assert set(cloned_vehicle.custom_rules.all()) == {custom_rule}

    assert cloned_vehicle.disabled_rules.count() == 1, (
        f"Expected cloned vehicle to have 1 disabled rule, "
        f"but found {cloned_vehicle.disabled_rules.count()}"
    )
    assert set(cloned_vehicle.disabled_rules.all()) == {disabled_rule}


@pytest.mark.django_db
def test_clone_linked_fighter_with_xp_and_overrides(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """
    Test that when cloning a list, XP and stat overrides on linked fighters are also cloned.
    """
    # Setup
    house = make_content_house("Test House")

    # Create the main fighter
    gang_member_cf = make_content_fighter(
        type="Gang Member",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create a beast fighter that will be auto-generated
    beast_cf = make_content_fighter(
        type="Exotic Beast",
        category=FighterCategoryChoices.EXOTIC_BEAST,
        house=house,
        base_cost=150,
    )

    # Create equipment that generates the beast fighter
    beast_equipment = make_equipment(
        "Beast Handler Kit",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=100,
    )

    # Link the beast fighter to the equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_equipment,
        content_fighter=beast_cf,
    )

    # Create the list and add the gang member
    original_list = make_list("Original List", content_house=house, owner=user)
    gang_member_lf = make_list_fighter(
        original_list, "Gang Member", content_fighter=gang_member_cf, owner=user
    )

    # Assign the beast equipment to the gang member
    beast_assignment = ListFighterEquipmentAssignment(
        list_fighter=gang_member_lf,
        content_equipment=beast_equipment,
    )
    beast_assignment.save()

    # Get the auto-created beast
    beast_lf = beast_assignment.linked_fighter
    assert beast_lf is not None

    # Set XP and stat overrides on the beast
    beast_lf.xp_current = 10
    beast_lf.xp_total = 25
    beast_lf.movement_override = "8"
    beast_lf.toughness_override = "5"
    beast_lf.wounds_override = "3"
    beast_lf.attacks_override = "4"
    beast_lf.narrative = "A fierce creature from the wastes"
    beast_lf.save()

    # Clone the list
    cloned_list = original_list.clone(name="Cloned List")

    # Find the cloned beast
    cloned_gang_member = (
        cloned_list.fighters().filter(content_fighter=gang_member_cf).first()
    )
    cloned_beast_assignment = (
        cloned_gang_member._direct_assignments()
        .filter(content_equipment=beast_equipment)
        .first()
    )
    cloned_beast = cloned_beast_assignment.linked_fighter

    # THESE SHOULD PASS: The cloned beast should have the same XP and overrides
    assert cloned_beast.xp_current == 10, (
        f"Expected cloned beast to have 10 current XP, "
        f"but found {cloned_beast.xp_current}"
    )
    assert cloned_beast.xp_total == 25, (
        f"Expected cloned beast to have 25 total XP, but found {cloned_beast.xp_total}"
    )
    assert cloned_beast.movement_override == "8"
    assert cloned_beast.toughness_override == "5"
    assert cloned_beast.wounds_override == "3"
    assert cloned_beast.attacks_override == "4"
    assert cloned_beast.narrative == "A fierce creature from the wastes"


@pytest.mark.django_db
def test_clone_linked_fighter_with_advancements(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """
    Test that when cloning a list, advancements on linked fighters are also cloned.
    """
    # Setup
    house = make_content_house("Test House")

    # Create the main fighter
    gang_member_cf = make_content_fighter(
        type="Gang Member",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create a vehicle fighter that will be auto-generated
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=200,
    )

    # Create equipment that generates the vehicle fighter
    vehicle_equipment = make_equipment(
        "Vehicle Key",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=150,
    )

    # Link the vehicle fighter to the equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_cf,
    )

    # Create skills for advancement
    skill_category = ContentSkillCategory.objects.create(
        name="Vehicle Skills", restricted=False
    )
    skill = ContentSkill.objects.create(name="Ram", category=skill_category)

    # Create the list and add the gang member
    original_list = make_list("Original List", content_house=house, owner=user)
    gang_member_lf = make_list_fighter(
        original_list, "Gang Member", content_fighter=gang_member_cf, owner=user
    )

    # Assign the vehicle equipment to the gang member
    vehicle_assignment = ListFighterEquipmentAssignment(
        list_fighter=gang_member_lf,
        content_equipment=vehicle_equipment,
    )
    vehicle_assignment.save()

    # Get the auto-created vehicle
    vehicle_lf = vehicle_assignment.linked_fighter
    assert vehicle_lf is not None

    # Add advancements to the vehicle
    ListFighterAdvancement.objects.create(
        fighter=vehicle_lf,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="toughness",
        xp_cost=6,
        cost_increase=5,
        owner=user,
    )

    ListFighterAdvancement.objects.create(
        fighter=vehicle_lf,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        xp_cost=3,
        cost_increase=2,
        owner=user,
    )

    ListFighterAdvancement.objects.create(
        fighter=vehicle_lf,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
        description="Custom upgrade: Nitro boost",
        xp_cost=4,
        cost_increase=10,
        owner=user,
    )

    # Verify the vehicle has the advancements
    assert vehicle_lf.advancements.count() == 3

    # Clone the list
    cloned_list = original_list.clone(name="Cloned List")

    # Find the cloned vehicle
    cloned_gang_member = (
        cloned_list.fighters().filter(content_fighter=gang_member_cf).first()
    )
    cloned_vehicle_assignment = (
        cloned_gang_member._direct_assignments()
        .filter(content_equipment=vehicle_equipment)
        .first()
    )
    cloned_vehicle = cloned_vehicle_assignment.linked_fighter

    # THESE SHOULD PASS: The cloned vehicle should have the same advancements
    assert cloned_vehicle.advancements.count() == 3, (
        f"Expected cloned vehicle to have 3 advancements, "
        f"but found {cloned_vehicle.advancements.count()}"
    )

    cloned_advancements = list(cloned_vehicle.advancements.all())

    # Check stat advancement
    stat_advancement = next(
        (
            a
            for a in cloned_advancements
            if a.advancement_type == ListFighterAdvancement.ADVANCEMENT_STAT
        ),
        None,
    )
    assert stat_advancement is not None, "Stat advancement not found in cloned vehicle"
    assert stat_advancement.stat_increased == "toughness"
    assert stat_advancement.xp_cost == 6
    assert stat_advancement.cost_increase == 5

    # Check skill advancement
    skill_advancement = next(
        (
            a
            for a in cloned_advancements
            if a.advancement_type == ListFighterAdvancement.ADVANCEMENT_SKILL
        ),
        None,
    )
    assert skill_advancement is not None, (
        "Skill advancement not found in cloned vehicle"
    )
    assert skill_advancement.skill == skill
    assert skill_advancement.xp_cost == 3
    assert skill_advancement.cost_increase == 2

    # Check other advancement
    other_advancement = next(
        (
            a
            for a in cloned_advancements
            if a.advancement_type == ListFighterAdvancement.ADVANCEMENT_OTHER
        ),
        None,
    )
    assert other_advancement is not None, (
        "Other advancement not found in cloned vehicle"
    )
    assert other_advancement.description == "Custom upgrade: Nitro boost"
    assert other_advancement.xp_cost == 4
    assert other_advancement.cost_increase == 10


@pytest.mark.django_db
def test_clone_linked_fighter_with_nested_links(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
    make_equipment,
):
    """
    Test that cloning works with nested linked fighters (e.g., vehicle with mounted weapon that creates a gunner).
    """
    # Setup
    house = make_content_house("Test House")

    # Create the main fighter
    gang_member_cf = make_content_fighter(
        type="Gang Member",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create a vehicle fighter
    vehicle_cf = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=house,
        base_cost=200,
    )

    # Create a gunner fighter
    gunner_cf = make_content_fighter(
        type="Gunner",
        category=FighterCategoryChoices.CREW,
        house=house,
        base_cost=50,
    )

    # Create equipment that generates the vehicle
    vehicle_equipment = make_equipment(
        "Vehicle Key",
        category=ContentEquipmentCategory.objects.get(name="Status Items"),
        cost=150,
    )

    # Create equipment that generates a gunner (mounted on vehicle)
    mounted_gun = make_equipment(
        "Mounted Heavy Weapon",
        category=ContentEquipmentCategory.objects.get(name="Heavy Weapons"),
        cost=100,
    )

    # Link the vehicle fighter to the vehicle equipment
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_cf,
    )

    # Link the gunner fighter to the mounted gun
    ContentEquipmentFighterProfile.objects.create(
        equipment=mounted_gun,
        content_fighter=gunner_cf,
    )

    # Create the list and add the gang member
    original_list = make_list("Original List", content_house=house, owner=user)
    gang_member_lf = make_list_fighter(
        original_list, "Gang Member", content_fighter=gang_member_cf, owner=user
    )

    # Assign the vehicle equipment to the gang member
    vehicle_assignment = ListFighterEquipmentAssignment(
        list_fighter=gang_member_lf,
        content_equipment=vehicle_equipment,
    )
    vehicle_assignment.save()

    # Get the auto-created vehicle
    vehicle_lf = vehicle_assignment.linked_fighter
    assert vehicle_lf is not None

    # Add the mounted gun to the vehicle (which should create a gunner)
    gun_assignment = ListFighterEquipmentAssignment(
        list_fighter=vehicle_lf,
        content_equipment=mounted_gun,
    )
    gun_assignment.save()

    # Get the auto-created gunner
    gunner_lf = gun_assignment.linked_fighter
    assert gunner_lf is not None

    # Add some equipment to the gunner
    gunner_armor = make_equipment(
        "Gunner Armor",
        category=ContentEquipmentCategory.objects.get(name="Armor"),
        cost=25,
    )
    gunner_armor_assignment = ListFighterEquipmentAssignment(
        list_fighter=gunner_lf,
        content_equipment=gunner_armor,
    )
    gunner_armor_assignment.save()

    # Add XP to both vehicle and gunner
    vehicle_lf.xp_current = 5
    vehicle_lf.xp_total = 10
    vehicle_lf.save()

    gunner_lf.xp_current = 3
    gunner_lf.xp_total = 8
    gunner_lf.save()

    # Clone the list
    cloned_list = original_list.clone(name="Cloned List")

    # Find the cloned gang member
    cloned_gang_member = (
        cloned_list.fighters().filter(content_fighter=gang_member_cf).first()
    )

    # Find the cloned vehicle
    cloned_vehicle_assignment = (
        cloned_gang_member._direct_assignments()
        .filter(content_equipment=vehicle_equipment)
        .first()
    )
    cloned_vehicle = cloned_vehicle_assignment.linked_fighter

    # Find the cloned gunner through the vehicle's mounted gun
    cloned_gun_assignment = (
        cloned_vehicle._direct_assignments()
        .filter(content_equipment=mounted_gun)
        .first()
    )
    cloned_gunner = cloned_gun_assignment.linked_fighter

    # THESE SHOULD PASS: Check the entire chain is properly cloned
    assert cloned_vehicle is not None, "Cloned vehicle not found"
    assert cloned_gunner is not None, "Cloned gunner not found"

    # Check vehicle XP
    assert cloned_vehicle.xp_current == 5
    assert cloned_vehicle.xp_total == 10

    # Check gunner XP
    assert cloned_gunner.xp_current == 3
    assert cloned_gunner.xp_total == 8

    # Check gunner has equipment
    assert cloned_gunner.equipment.count() == 1
    assert cloned_gunner.equipment.first().name == "Gunner Armor"
