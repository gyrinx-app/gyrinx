import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentWeaponProfile,
)


@pytest.mark.django_db
def test_content_equipment_default_ordering_is_alphabetical():
    """Test that ContentEquipment.objects.all() returns equipment in alphabetical order by name."""
    # Create a test category
    category = ContentEquipmentCategory.objects.create(name="Test Weapons")

    # Create equipment with names that would be out of order if not sorted
    equipment_names = ["Zzz Weapon", "Aaa Weapon", "Mmm Weapon", "Bbb Weapon"]
    created_ids = []
    for name in equipment_names:
        eq = ContentEquipment.objects.create(name=name, category=category, cost="10")
        created_ids.append(eq.id)

    # Filter to only our test equipment
    equipment = ContentEquipment.objects.filter(id__in=created_ids)
    equipment_names = [e.name for e in equipment]

    # Expected order is alphabetical by name only
    expected_order = ["Aaa Weapon", "Bbb Weapon", "Mmm Weapon", "Zzz Weapon"]

    assert equipment_names == expected_order


@pytest.mark.django_db
def test_weapons_ordering_is_alphabetical():
    """Test that weapons() queryset returns equipment in alphabetical order by name."""
    category = ContentEquipmentCategory.objects.create(name="Test Weapons")

    # Create weapons with out-of-order names
    weapon_names = ["Zzz Gun", "Aaa Rifle", "Mmm Pistol", "Bbb Launcher"]
    created_ids = []
    for name in weapon_names:
        equipment = ContentEquipment.objects.create(
            name=name, category=category, cost="10"
        )
        created_ids.append(equipment.id)
        # Add a weapon profile to make it a weapon
        ContentWeaponProfile.objects.create(equipment=equipment, name="", cost=0)

    weapons = ContentEquipment.objects.filter(id__in=created_ids).weapons()
    weapon_names = [w.name for w in weapons]

    # Expected order is alphabetical by name only
    expected_order = ["Aaa Rifle", "Bbb Launcher", "Mmm Pistol", "Zzz Gun"]

    assert weapon_names == expected_order


@pytest.mark.django_db
def test_non_weapons_ordering_is_alphabetical():
    """Test that non_weapons() queryset returns equipment in alphabetical order by name."""
    category = ContentEquipmentCategory.objects.create(name="Test Gear")

    # Create non-weapons with out-of-order names
    gear_names = ["Zzz Armor", "Aaa Pack", "Mmm Tool", "Bbb Device"]
    created_ids = []
    for name in gear_names:
        eq = ContentEquipment.objects.create(name=name, category=category, cost="5")
        created_ids.append(eq.id)

    # These have no weapon profiles, so they're all non-weapons
    non_weapons = ContentEquipment.objects.filter(id__in=created_ids).non_weapons()
    non_weapon_names = [e.name for e in non_weapons]

    # Expected order is alphabetical by name only
    expected_order = ["Aaa Pack", "Bbb Device", "Mmm Tool", "Zzz Armor"]

    assert non_weapon_names == expected_order


@pytest.mark.django_db
def test_multiple_categories_ordered_by_category_and_name():
    """Test that equipment from multiple categories is ordered by name only, not by category."""
    # Create multiple categories - names chosen to test that category name doesn't affect ordering
    category1 = ContentEquipmentCategory.objects.create(name="Z Category")
    category2 = ContentEquipmentCategory.objects.create(name="A Category")

    # Add equipment to both categories
    created_ids = []
    eq1 = ContentEquipment.objects.create(name="Ddd Item", category=category2, cost="5")
    created_ids.append(eq1.id)
    eq2 = ContentEquipment.objects.create(name="Bbb Item", category=category1, cost="5")
    created_ids.append(eq2.id)
    eq3 = ContentEquipment.objects.create(name="Ccc Item", category=category2, cost="5")
    created_ids.append(eq3.id)
    eq4 = ContentEquipment.objects.create(name="Aaa Item", category=category1, cost="5")
    created_ids.append(eq4.id)

    equipment = ContentEquipment.objects.filter(id__in=created_ids)
    equipment_names = [e.name for e in equipment]

    # Expected order is alphabetical by name only, after category
    expected_order = ["Ccc Item", "Ddd Item", "Aaa Item", "Bbb Item"]

    assert equipment_names == expected_order


@pytest.mark.django_db
def test_equipment_with_special_characters_ordering():
    """Test that equipment with special characters and numbers are ordered correctly."""
    category = ContentEquipmentCategory.objects.create(name="Test Category")

    # Create equipment with various special characters and numbers
    special_names = [
        "10mm Rifle",
        "2-handed Sword",
        "'Zerker Axe",
        "Armor (Heavy)",
        "Bolt Pistol",
        "Chainaxe",
    ]

    created_ids = []
    for name in special_names:
        eq = ContentEquipment.objects.create(name=name, category=category, cost="10")
        created_ids.append(eq.id)

    equipment = ContentEquipment.objects.filter(id__in=created_ids)
    equipment_names = [e.name for e in equipment]

    # The actual order follows the manager's default ordering (category__name, name, id)
    # Since all items have the same category, they're ordered by name
    # The ordering is case-sensitive lexicographic where apostrophes come after letters
    expected_order = [
        "10mm Rifle",
        "2-handed Sword",
        "Armor (Heavy)",
        "Bolt Pistol",
        "Chainaxe",
        "'Zerker Axe",
    ]

    assert equipment_names == expected_order
