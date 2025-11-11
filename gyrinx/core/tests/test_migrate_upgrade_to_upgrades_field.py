import importlib

import pytest
from django.apps import apps

from gyrinx.core.models.list import ListFighterEquipmentAssignment


@pytest.fixture
def setup_data(
    user,
    content_house,
    make_equipment,
    make_equipment_upgrade,
    content_fighter,
    make_list,
    make_list_fighter,
    content_equipment_categories,
):
    """Create basic test data for migration tests."""
    # Create equipment with 3 upgrades
    equipment = make_equipment(
        name="Test Migration Weapon",
        cost=10,
        rarity="C",
        category=content_equipment_categories[0],
    )

    upgrade1 = make_equipment_upgrade(equipment, "Upgrade 1", 5)
    upgrade2 = make_equipment_upgrade(equipment, "Upgrade 2", 10)
    upgrade3 = make_equipment_upgrade(equipment, "Upgrade 3", 15)

    # Create list and fighter
    lst = make_list("Test Migration List")
    list_fighter = make_list_fighter(lst, "Test Migration Fighter")

    return {
        "user": user,
        "house": content_house,
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
