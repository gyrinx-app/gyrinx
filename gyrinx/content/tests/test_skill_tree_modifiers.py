"""Tests for skill tree access modifiers on equipment."""

import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentModSkillTreeAccess,
    ContentSkillCategory,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment


@pytest.mark.django_db
def test_equipment_can_add_primary_skill_category():
    """Test that equipment can add a primary skill category to a fighter."""
    # Create basic setup
    user = get_user_model().objects.create_user("test@example.com", "password")
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="wargear"
    )

    # Create skill categories
    muscle_skill = ContentSkillCategory.objects.create(name="Muscle")
    agility_skill = ContentSkillCategory.objects.create(name="Agility")

    # Create content fighter with only Muscle as primary
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.primary_skill_categories.add(muscle_skill)

    # Create equipment with a modifier to add Agility as primary
    equipment = ContentEquipment.objects.create(
        name="Agility Enhancer",
        category=category,
    )

    # Create the skill tree modifier
    modifier = ContentModSkillTreeAccess.objects.create(
        skill_category=agility_skill,
        mode="add_primary",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        name="Fighter 1",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Initially should only have Muscle as primary
    primary_categories = list_fighter.get_primary_skill_categories()
    assert muscle_skill in primary_categories
    assert agility_skill not in primary_categories

    # Assign equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Clear cached properties to ensure fresh data
    if hasattr(list_fighter, "_mods"):
        del list_fighter._mods
    if hasattr(list_fighter, "assignments_cached"):
        del list_fighter.assignments_cached

    # Now should have both Muscle and Agility as primary
    primary_categories = list_fighter.get_primary_skill_categories()
    assert muscle_skill in primary_categories
    assert agility_skill in primary_categories


@pytest.mark.django_db
def test_equipment_can_remove_primary_skill_category():
    """Test that equipment can remove a primary skill category from a fighter."""
    # Create basic setup
    user = get_user_model().objects.create_user("test@example.com", "password")
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="wargear"
    )

    # Create skill categories
    muscle_skill = ContentSkillCategory.objects.create(name="Muscle")
    agility_skill = ContentSkillCategory.objects.create(name="Agility")

    # Create content fighter with both Muscle and Agility as primary
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.primary_skill_categories.add(muscle_skill)
    content_fighter.primary_skill_categories.add(agility_skill)

    # Create equipment with a modifier to remove Muscle as primary
    equipment = ContentEquipment.objects.create(
        name="Muscle Inhibitor",
        category=category,
    )

    # Create the skill tree modifier
    modifier = ContentModSkillTreeAccess.objects.create(
        skill_category=muscle_skill,
        mode="remove_primary",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        name="Fighter 1",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Initially should have both as primary
    primary_categories = list_fighter.get_primary_skill_categories()
    assert muscle_skill in primary_categories
    assert agility_skill in primary_categories

    # Assign equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Clear cached properties to ensure fresh data
    if hasattr(list_fighter, "_mods"):
        del list_fighter._mods
    if hasattr(list_fighter, "assignments_cached"):
        del list_fighter.assignments_cached

    # Now should only have Agility as primary
    primary_categories = list_fighter.get_primary_skill_categories()
    assert muscle_skill not in primary_categories
    assert agility_skill in primary_categories


@pytest.mark.django_db
def test_equipment_can_add_secondary_skill_category():
    """Test that equipment can add a secondary skill category to a fighter."""
    # Create basic setup
    user = get_user_model().objects.create_user("test@example.com", "password")
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="wargear"
    )

    # Create skill categories
    cunning_skill = ContentSkillCategory.objects.create(name="Cunning")
    shooting_skill = ContentSkillCategory.objects.create(name="Shooting")

    # Create content fighter with only Cunning as secondary
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.secondary_skill_categories.add(cunning_skill)

    # Create equipment with a modifier to add Shooting as secondary
    equipment = ContentEquipment.objects.create(
        name="Marksman Sight",
        category=category,
    )

    # Create the skill tree modifier
    modifier = ContentModSkillTreeAccess.objects.create(
        skill_category=shooting_skill,
        mode="add_secondary",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        name="Fighter 1",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Initially should only have Cunning as secondary
    secondary_categories = list_fighter.get_secondary_skill_categories()
    assert cunning_skill in secondary_categories
    assert shooting_skill not in secondary_categories

    # Assign equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Clear cached properties to ensure fresh data
    if hasattr(list_fighter, "_mods"):
        del list_fighter._mods
    if hasattr(list_fighter, "assignments_cached"):
        del list_fighter.assignments_cached

    # Now should have both Cunning and Shooting as secondary
    secondary_categories = list_fighter.get_secondary_skill_categories()
    assert cunning_skill in secondary_categories
    assert shooting_skill in secondary_categories


@pytest.mark.django_db
def test_equipment_can_disable_skill_category_access():
    """Test that equipment can completely disable access to a skill category."""
    # Create basic setup
    user = get_user_model().objects.create_user("test@example.com", "password")
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="wargear"
    )

    # Create skill categories
    muscle_skill = ContentSkillCategory.objects.create(name="Muscle")
    agility_skill = ContentSkillCategory.objects.create(name="Agility")

    # Create content fighter with Muscle as primary and Agility as secondary
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.primary_skill_categories.add(muscle_skill)
    content_fighter.secondary_skill_categories.add(agility_skill)

    # Create equipment with a modifier to disable Muscle entirely
    equipment = ContentEquipment.objects.create(
        name="Muscle Blocker",
        category=category,
    )

    # Create the skill tree modifier
    modifier = ContentModSkillTreeAccess.objects.create(
        skill_category=muscle_skill,
        mode="disable",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        name="Fighter 1",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Initially should have Muscle as primary and Agility as secondary
    primary_categories = list_fighter.get_primary_skill_categories()
    secondary_categories = list_fighter.get_secondary_skill_categories()
    assert muscle_skill in primary_categories
    assert agility_skill in secondary_categories

    # Assign equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Clear cached properties to ensure fresh data
    if hasattr(list_fighter, "_mods"):
        del list_fighter._mods
    if hasattr(list_fighter, "assignments_cached"):
        del list_fighter.assignments_cached

    # Now Muscle should be disabled from both primary and secondary
    primary_categories = list_fighter.get_primary_skill_categories()
    secondary_categories = list_fighter.get_secondary_skill_categories()
    assert muscle_skill not in primary_categories
    assert muscle_skill not in secondary_categories
    assert agility_skill in secondary_categories


@pytest.mark.django_db
def test_multiple_equipment_modifiers_stack():
    """Test that multiple equipment items with skill tree modifiers stack correctly."""
    # Create basic setup
    user = get_user_model().objects.create_user("test@example.com", "password")
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="wargear"
    )

    # Create skill categories
    muscle_skill = ContentSkillCategory.objects.create(name="Muscle")
    agility_skill = ContentSkillCategory.objects.create(name="Agility")
    cunning_skill = ContentSkillCategory.objects.create(name="Cunning")

    # Create content fighter with only Muscle as primary
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
    )
    content_fighter.primary_skill_categories.add(muscle_skill)

    # Create first equipment that adds Agility as primary
    equipment1 = ContentEquipment.objects.create(
        name="Agility Enhancer",
        category=category,
    )
    modifier1 = ContentModSkillTreeAccess.objects.create(
        skill_category=agility_skill,
        mode="add_primary",
    )
    equipment1.modifiers.add(modifier1)

    # Create second equipment that adds Cunning as secondary
    equipment2 = ContentEquipment.objects.create(
        name="Cunning Device",
        category=category,
    )
    modifier2 = ContentModSkillTreeAccess.objects.create(
        skill_category=cunning_skill,
        mode="add_secondary",
    )
    equipment2.modifiers.add(modifier2)

    # Create list and fighter
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        name="Fighter 1",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Initially should only have Muscle as primary
    primary_categories = list_fighter.get_primary_skill_categories()
    secondary_categories = list_fighter.get_secondary_skill_categories()
    assert muscle_skill in primary_categories
    assert agility_skill not in primary_categories
    assert len(secondary_categories) == 0

    # Assign both equipment
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment1,
    )
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment2,
    )

    # Clear cached properties to ensure fresh data
    if hasattr(list_fighter, "_mods"):
        del list_fighter._mods
    if hasattr(list_fighter, "assignments_cached"):
        del list_fighter.assignments_cached

    # Now should have Muscle and Agility as primary, and Cunning as secondary
    primary_categories = list_fighter.get_primary_skill_categories()
    secondary_categories = list_fighter.get_secondary_skill_categories()
    assert muscle_skill in primary_categories
    assert agility_skill in primary_categories
    assert cunning_skill in secondary_categories
