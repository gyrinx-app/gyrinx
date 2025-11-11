import importlib

import pytest
from django.apps import apps
from django.contrib.auth import get_user_model

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment

User = get_user_model()


@pytest.fixture
def setup_data():
    """Create basic test data for migration tests."""
    # Create user
    user = User.objects.create_user(username="test_migration_user", password="testpass")

    # Create house
    house = ContentHouse.objects.create(name="Test Migration House", generic=True)

    # Create equipment category
    category = ContentEquipmentCategory.objects.create(name="Test Migration Weapons")

    # Create equipment
    equipment = ContentEquipment.objects.create(
        name="Test Migration Weapon", category=category, cost=10, rarity="C"
    )

    # Create upgrades
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Upgrade 1", cost=5
    )
    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Upgrade 2", cost=10
    )
    upgrade3 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment, name="Upgrade 3", cost=15
    )

    # Create fighter type
    fighter_type = ContentFighter.objects.create(
        house=house,
        type="Test Migration Fighter",
        category="GANGER",
        base_cost=50,
        movement="4",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
    )

    # Create list and fighter
    lst = List.objects.create(
        name="Test Migration List", content_house=house, owner=user
    )

    list_fighter = ListFighter.objects.create(
        name="Test Migration Fighter",
        content_fighter=fighter_type,
        list=lst,
        owner=user,
    )

    return {
        "user": user,
        "house": house,
        "equipment": equipment,
        "upgrade1": upgrade1,
        "upgrade2": upgrade2,
        "upgrade3": upgrade3,
        "list_fighter": list_fighter,
    }


@pytest.mark.django_db
def test_migrate_upgrade_to_upgrades_field_migration(setup_data):
    """
    Test that the migration properly moves upgrade to upgrades_field.
    """
    # Create assignment with upgrade set (no items in upgrades_field)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=setup_data["list_fighter"],
        content_equipment=setup_data["equipment"],
        upgrade=setup_data["upgrade1"],
    )

    # Verify initial state
    assert assignment.upgrade == setup_data["upgrade1"]
    assert assignment.upgrades_field.count() == 0

    # Run the migration
    migration_module = importlib.import_module(
        "gyrinx.core.migrations.0113_migrate_upgrade_to_upgrades_field"
    )
    migration_module.migrate_upgrade_to_upgrades_field(apps, None)

    # Refresh from database
    assignment.refresh_from_db()

    # Verify results
    assert assignment.upgrade is None
    assert assignment.upgrades_field.count() == 1
    assert assignment.upgrades_field.first() == setup_data["upgrade1"]


@pytest.mark.django_db
def test_migrate_upgrade_already_in_upgrades_field(setup_data):
    """
    Test that the migration handles the case where upgrade is already in upgrades_field.
    Should not create duplicates.
    """
    # Create assignment with upgrade set AND that same upgrade already in upgrades_field
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=setup_data["list_fighter"],
        content_equipment=setup_data["equipment"],
        upgrade=setup_data["upgrade1"],
    )
    assignment.upgrades_field.add(setup_data["upgrade1"])

    # Verify initial state
    assert assignment.upgrade == setup_data["upgrade1"]
    assert assignment.upgrades_field.count() == 1

    # Run the migration
    migration_module = importlib.import_module(
        "gyrinx.core.migrations.0113_migrate_upgrade_to_upgrades_field"
    )
    migration_module.migrate_upgrade_to_upgrades_field(apps, None)

    # Refresh from database
    assignment.refresh_from_db()

    # Verify results - no duplicates
    assert assignment.upgrade is None
    assert assignment.upgrades_field.count() == 1
    assert assignment.upgrades_field.first() == setup_data["upgrade1"]


@pytest.mark.django_db
def test_migrate_upgrade_with_other_upgrades(setup_data):
    """
    Test that the migration preserves other upgrades in upgrades_field.
    """
    # Create assignment with upgrade set AND other different upgrades in upgrades_field
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=setup_data["list_fighter"],
        content_equipment=setup_data["equipment"],
        upgrade=setup_data["upgrade1"],
    )
    assignment.upgrades_field.add(setup_data["upgrade2"])
    assignment.upgrades_field.add(setup_data["upgrade3"])

    # Verify initial state
    assert assignment.upgrade == setup_data["upgrade1"]
    assert assignment.upgrades_field.count() == 2

    # Run the migration
    migration_module = importlib.import_module(
        "gyrinx.core.migrations.0113_migrate_upgrade_to_upgrades_field"
    )
    migration_module.migrate_upgrade_to_upgrades_field(apps, None)

    # Refresh from database
    assignment.refresh_from_db()

    # Verify results - all upgrades present
    assert assignment.upgrade is None
    assert assignment.upgrades_field.count() == 3
    assert set(assignment.upgrades_field.all()) == {
        setup_data["upgrade1"],
        setup_data["upgrade2"],
        setup_data["upgrade3"],
    }


@pytest.mark.django_db
def test_migrate_no_upgrade_set(setup_data):
    """
    Test that the migration handles assignments with no upgrade set.
    Should not change anything.
    """
    # Create assignment with upgrade = None
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=setup_data["list_fighter"],
        content_equipment=setup_data["equipment"],
        upgrade=None,
    )

    # Verify initial state
    assert assignment.upgrade is None
    assert assignment.upgrades_field.count() == 0

    # Run the migration
    migration_module = importlib.import_module(
        "gyrinx.core.migrations.0113_migrate_upgrade_to_upgrades_field"
    )
    migration_module.migrate_upgrade_to_upgrades_field(apps, None)

    # Refresh from database
    assignment.refresh_from_db()

    # Verify results - no changes
    assert assignment.upgrade is None
    assert assignment.upgrades_field.count() == 0
