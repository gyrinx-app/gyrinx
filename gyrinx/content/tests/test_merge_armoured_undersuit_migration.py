import pytest
from django.apps import apps

from gyrinx.core.models import ListFighterEquipmentAssignment, List, ListFighter


@pytest.mark.django_db
def test_merge_armoured_undersuit_migration():
    """
    Test the merge_armoured_undersuit migration properly merges equipment entries.
    """
    # Get models using the app registry to ensure we have the right versions
    ContentEquipment = apps.get_model("content", "ContentEquipment")
    ContentFighterEquipmentListItem = apps.get_model(
        "content", "ContentFighterEquipmentListItem"
    )
    ContentHouse = apps.get_model("content", "ContentHouse")
    ContentFighter = apps.get_model("content", "ContentFighter")
    ContentEquipmentCategory = apps.get_model("content", "ContentEquipmentCategory")

    # Create test data
    # First, create the category for equipment
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Armor",
        defaults={"group": "Equipment"},
    )

    # Create correctly spelled equipment
    correct_equipment = ContentEquipment.objects.create(
        name="Armoured undersuit",
        category=category,
        cost="25",
        rarity="C",
    )

    # Create incorrectly spelled equipment
    incorrect_equipment = ContentEquipment.objects.create(
        name="Armoured Undersuit",  # Capital U
        category=category,
        cost="25",
        rarity="C",
    )

    # Create a house and fighter for testing references
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Leader",
        house=house,
    )

    # Create equipment list item pointing to incorrect equipment
    equipment_list_item = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter,
        equipment=incorrect_equipment,
        cost="25",
    )

    # Create user list and fighter
    user_list = List.objects.create(
        name="Test List",
        status=List.CAMPAIGN_MODE,
        content_house=house,
    )
    list_fighter = ListFighter.objects.create(
        list=user_list,
        content_fighter=fighter,
        name="Test List Fighter",
    )

    # Create equipment assignment pointing to incorrect equipment
    equipment_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=incorrect_equipment,
    )

    # Store IDs for verification
    correct_id = correct_equipment.id
    incorrect_id = incorrect_equipment.id

    # Run the migration
    import importlib

    migration_module = importlib.import_module(
        "gyrinx.content.migrations.0118_merge_armoured_undersuit"
    )
    migration_module.merge_armoured_undersuit(apps, None)

    # Verify results
    # 1. Incorrect equipment should be deleted
    assert not ContentEquipment.objects.filter(id=incorrect_id).exists()

    # 2. Correct equipment should still exist
    assert ContentEquipment.objects.filter(id=correct_id).exists()

    # 3. All references should point to correct equipment
    equipment_list_item.refresh_from_db()
    assert equipment_list_item.equipment_id == correct_id

    equipment_assignment.refresh_from_db()
    assert equipment_assignment.content_equipment_id == correct_id


@pytest.mark.django_db
def test_merge_armoured_undersuit_migration_no_incorrect():
    """
    Test the migration handles the case where no incorrect equipment exists.
    """
    ContentEquipment = apps.get_model("content", "ContentEquipment")
    ContentEquipmentCategory = apps.get_model("content", "ContentEquipmentCategory")

    # Create only correctly spelled equipment
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Armor",
        defaults={"group": "Equipment"},
    )

    correct_equipment = ContentEquipment.objects.create(
        name="Armoured undersuit",
        category=category,
        cost="25",
        rarity="C",
    )

    # Run the migration - should complete without errors
    import importlib

    migration_module = importlib.import_module(
        "gyrinx.content.migrations.0118_merge_armoured_undersuit"
    )
    migration_module.merge_armoured_undersuit(apps, None)

    # Verify correct equipment still exists
    assert ContentEquipment.objects.filter(id=correct_equipment.id).exists()


@pytest.mark.django_db
def test_merge_armoured_undersuit_migration_no_correct():
    """
    Test the migration handles the case where no correct equipment exists.
    """
    ContentEquipment = apps.get_model("content", "ContentEquipment")
    ContentEquipmentCategory = apps.get_model("content", "ContentEquipmentCategory")

    # Create only incorrectly spelled equipment
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Armor",
        defaults={"group": "Equipment"},
    )

    incorrect_equipment = ContentEquipment.objects.create(
        name="Armoured Undersuit",
        category=category,
        cost="25",
        rarity="C",
    )

    # Run the migration - should complete without errors (skip processing)
    import importlib

    migration_module = importlib.import_module(
        "gyrinx.content.migrations.0118_merge_armoured_undersuit"
    )
    migration_module.merge_armoured_undersuit(apps, None)

    # Verify incorrect equipment still exists (not deleted since no correct one to merge into)
    assert ContentEquipment.objects.filter(id=incorrect_equipment.id).exists()


@pytest.mark.django_db
def test_merge_armoured_undersuit_migration_american_spelling():
    """
    Test the migration handles American spelling (Armored vs Armoured).
    """
    ContentEquipment = apps.get_model("content", "ContentEquipment")
    ContentEquipmentCategory = apps.get_model("content", "ContentEquipmentCategory")

    # Create category
    category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Armor",
        defaults={"group": "Equipment"},
    )

    # Create American spelling (correct)
    correct_equipment = ContentEquipment.objects.create(
        name="Armored undersuit",  # American spelling
        category=category,
        cost="25",
        rarity="C",
    )

    # Create incorrect American spelling
    incorrect_equipment = ContentEquipment.objects.create(
        name="Armored Undersuit",  # American spelling with capital U
        category=category,
        cost="25",
        rarity="C",
    )

    correct_id = correct_equipment.id
    incorrect_id = incorrect_equipment.id

    # Run the migration
    import importlib

    migration_module = importlib.import_module(
        "gyrinx.content.migrations.0118_merge_armoured_undersuit"
    )
    migration_module.merge_armoured_undersuit(apps, None)

    # Verify results
    assert not ContentEquipment.objects.filter(id=incorrect_id).exists()
    assert ContentEquipment.objects.filter(id=correct_id).exists()
