import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.base import BaseStorage
from django.test import RequestFactory

from gyrinx.content.actions import copy_selected_to_fighter, copy_selected_to_house
from gyrinx.content.admin import (
    ContentFighterAdmin,
    ContentFighterDefaultAssignmentAdmin,
    ContentFighterEquipmentListItemAdmin,
    ContentFighterEquipmentListUpgradeAdmin,
    ContentFighterEquipmentListWeaponAccessoryAdmin,
)
from gyrinx.content.models import (
    ContentFighter,
    ContentFighterDefaultAssignment,
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
    ContentHouse,
    ContentWeaponAccessory,
)

User = get_user_model()


@pytest.fixture
def admin_site():
    return AdminSite()


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser(
        username="admin", email="admin@test.com", password="testpass"
    )


@pytest.fixture
def test_houses(db, content_books):
    house1 = ContentHouse.objects.create(name="Test House 1")
    house2 = ContentHouse.objects.create(name="Test House 2")
    house3 = ContentHouse.objects.create(name="Legacy House", legacy=True)
    return house1, house2, house3


@pytest.fixture
def test_fighters(db, test_houses, content_equipment_categories):
    house1, house2, _ = test_houses
    fighter1 = ContentFighter.objects.create(
        type="Fighter 1", category="LEADER", house=house1, base_cost=100
    )
    fighter2 = ContentFighter.objects.create(
        type="Fighter 2", category="GANGER", house=house2, base_cost=50
    )
    fighter3 = ContentFighter.objects.create(
        type="Fighter 3", category="PROSPECT", house=house1, base_cost=30
    )
    return fighter1, fighter2, fighter3


@pytest.fixture
def test_equipment_items(
    db, test_fighters, make_equipment, make_weapon_profile, content_equipment_categories
):
    fighter1, fighter2, _ = test_fighters
    equipment1 = make_equipment(name="Test Weapon 1", cost=10)
    equipment2 = make_equipment(name="Test Weapon 2", cost=20)
    weapon_profile1 = make_weapon_profile(equipment=equipment1)
    weapon_profile2 = make_weapon_profile(equipment=equipment2)

    item1 = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter1, equipment=equipment1, weapon_profile=weapon_profile1
    )
    item2 = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter1, equipment=equipment2, weapon_profile=weapon_profile2
    )
    return item1, item2, equipment1, equipment2, weapon_profile1, weapon_profile2


@pytest.mark.django_db
def test_copy_selected_to_fighter_form_rendering(
    admin_site, request_factory, admin_user, test_equipment_items
):
    item1, item2, *_ = test_equipment_items
    queryset = ContentFighterEquipmentListItem.objects.filter(
        pk__in=[item1.pk, item2.pk]
    )

    request = request_factory.get("/admin/")
    request.user = admin_user

    model_admin = ContentFighterEquipmentListItemAdmin(
        ContentFighterEquipmentListItem, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is not None
    assert response.status_code == 200
    assert b"Copy items to another ContentFighter?" in response.content
    assert b"Test Weapon 1" in response.content
    assert b"Test Weapon 2" in response.content


@pytest.mark.django_db
def test_copy_selected_to_fighter_successful_copy(
    admin_site, request_factory, admin_user, test_equipment_items, test_fighters
):
    item1, item2, *_ = test_equipment_items
    _, fighter2, fighter3 = test_fighters
    queryset = ContentFighterEquipmentListItem.objects.filter(
        pk__in=[item1.pk, item2.pk]
    )

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_fighters": [fighter2.pk, fighter3.pk],
            "_selected_action": [item1.pk, item2.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterEquipmentListItemAdmin(
        ContentFighterEquipmentListItem, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is None

    # Check that items were copied to both fighters
    fighter2_items = ContentFighterEquipmentListItem.objects.filter(fighter=fighter2)
    fighter3_items = ContentFighterEquipmentListItem.objects.filter(fighter=fighter3)

    assert fighter2_items.count() == 2
    assert fighter3_items.count() == 2

    # Verify equipment was copied correctly
    fighter2_equipment = set(fighter2_items.values_list("equipment__name", flat=True))
    assert "Test Weapon 1" in fighter2_equipment
    assert "Test Weapon 2" in fighter2_equipment


@pytest.mark.django_db
def test_copy_selected_to_fighter_error_handling(
    admin_site, request_factory, admin_user, test_equipment_items
):
    item1, item2, *_ = test_equipment_items
    queryset = ContentFighterEquipmentListItem.objects.filter(
        pk__in=[item1.pk, item2.pk]
    )

    # Test with invalid fighter ID
    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_fighters": ["invalid_id"],
            "_selected_action": [item1.pk, item2.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterEquipmentListItemAdmin(
        ContentFighterEquipmentListItem, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is None


@pytest.mark.django_db
def test_copy_selected_to_fighter_with_default_assignments(
    admin_site, request_factory, admin_user, test_fighters, make_equipment
):
    fighter1, fighter2, _ = test_fighters
    equipment = make_equipment(name="Default Equipment", cost=15)

    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter1, equipment=equipment
    )

    queryset = ContentFighterDefaultAssignment.objects.filter(pk=assignment.pk)

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_fighters": [fighter2.pk],
            "_selected_action": [assignment.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterDefaultAssignmentAdmin(
        ContentFighterDefaultAssignment, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is None

    # Check that assignment was copied
    fighter2_assignments = ContentFighterDefaultAssignment.objects.filter(
        fighter=fighter2
    )
    assert fighter2_assignments.count() == 1
    assert fighter2_assignments.first().equipment == equipment


@pytest.mark.django_db
def test_copy_selected_to_fighter_with_weapon_accessories(
    admin_site,
    request_factory,
    admin_user,
    test_fighters,
    db,
    content_equipment_categories,
):
    fighter1, fighter2, _ = test_fighters
    accessory = ContentWeaponAccessory.objects.create(name="Weapon Accessory", cost=5)

    weapon_accessory = ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter1, weapon_accessory=accessory
    )

    queryset = ContentFighterEquipmentListWeaponAccessory.objects.filter(
        pk=weapon_accessory.pk
    )

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_fighters": [fighter2.pk],
            "_selected_action": [weapon_accessory.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterEquipmentListWeaponAccessoryAdmin(
        ContentFighterEquipmentListWeaponAccessory, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is None

    # Check that accessory was copied
    fighter2_accessories = ContentFighterEquipmentListWeaponAccessory.objects.filter(
        fighter=fighter2
    )
    assert fighter2_accessories.count() == 1
    assert fighter2_accessories.first().weapon_accessory == accessory


@pytest.mark.django_db
def test_copy_selected_to_fighter_with_upgrades(
    admin_site, request_factory, admin_user, test_fighters, make_equipment
):
    fighter1, fighter2, _ = test_fighters
    equipment = make_equipment(name="Upgradeable Equipment", cost=25)
    upgrade = equipment.upgrades.create(name="Test Upgrade", cost=10)

    equipment_upgrade = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=fighter1, upgrade=upgrade
    )

    queryset = ContentFighterEquipmentListUpgrade.objects.filter(
        pk=equipment_upgrade.pk
    )

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_fighters": [fighter2.pk],
            "_selected_action": [equipment_upgrade.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterEquipmentListUpgradeAdmin(
        ContentFighterEquipmentListUpgrade, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is None

    # Check that upgrade was copied
    fighter2_upgrades = ContentFighterEquipmentListUpgrade.objects.filter(
        fighter=fighter2
    )
    assert fighter2_upgrades.count() == 1
    assert fighter2_upgrades.first().upgrade == upgrade


@pytest.mark.django_db
def test_copy_selected_to_house_form_rendering(
    admin_site, request_factory, admin_user, test_fighters, test_houses
):
    fighter1, fighter2, _ = test_fighters
    queryset = ContentFighter.objects.filter(pk__in=[fighter1.pk, fighter2.pk])

    request = request_factory.get("/admin/")
    request.user = admin_user

    model_admin = ContentFighterAdmin(ContentFighter, admin_site)
    response = copy_selected_to_house(model_admin, request, queryset)

    assert response is not None
    assert response.status_code == 200
    assert b"Copy items to another ContentHouse?" in response.content
    assert b"Fighter 1" in response.content
    assert b"Fighter 2" in response.content


@pytest.mark.django_db
def test_copy_selected_to_house_successful_copy(
    admin_site, request_factory, admin_user, test_fighters, test_houses
):
    fighter1, _, _ = test_fighters
    _, house2, house3 = test_houses

    # Add some skills and rules to fighter1 to test the copy_to_house method
    fighter1.save()

    queryset = ContentFighter.objects.filter(pk=fighter1.pk)

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_houses": [house2.pk, house3.pk],
            "_selected_action": [fighter1.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterAdmin(ContentFighter, admin_site)
    response = copy_selected_to_house(model_admin, request, queryset)

    assert response is None

    # Check that fighters were copied to both houses
    house2_fighters = ContentFighter.objects.filter(house=house2)
    house3_fighters = ContentFighter.objects.filter(house=house3)

    # Should have the original fighter2 plus the copied fighter1
    assert house2_fighters.count() == 2
    # Should have only the copied fighter1
    assert house3_fighters.count() == 1

    # Verify fighter properties were copied
    copied_to_house2 = house2_fighters.exclude(type="Fighter 2").first()
    assert copied_to_house2.type == "Fighter 1"
    assert copied_to_house2.category == "LEADER"
    assert copied_to_house2.base_cost == 100


@pytest.mark.django_db
def test_copy_selected_to_house_error_handling(
    admin_site, request_factory, admin_user, test_fighters
):
    fighter1, _, _ = test_fighters
    queryset = ContentFighter.objects.filter(pk=fighter1.pk)

    # Test with invalid house ID
    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_houses": ["99999"],  # Non-existent ID
            "_selected_action": [fighter1.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterAdmin(ContentFighter, admin_site)
    response = copy_selected_to_house(model_admin, request, queryset)

    assert response is None


@pytest.mark.django_db
def test_copy_selected_to_house_with_equipment_and_assignments(
    admin_site,
    request_factory,
    admin_user,
    test_fighters,
    test_houses,
    make_equipment,
    make_weapon_profile,
):
    fighter1, _, _ = test_fighters
    _, house2, _ = test_houses

    # Add equipment and assignments to fighter1
    equipment = make_equipment(name="Fighter Equipment", cost=30)
    weapon_profile = make_weapon_profile(equipment=equipment)

    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter1, equipment=equipment, weapon_profile=weapon_profile
    )

    ContentFighterDefaultAssignment.objects.create(
        fighter=fighter1, equipment=equipment
    )

    accessory = ContentWeaponAccessory.objects.create(name="Fighter Accessory", cost=5)
    ContentFighterEquipmentListWeaponAccessory.objects.create(
        fighter=fighter1, weapon_accessory=accessory
    )

    queryset = ContentFighter.objects.filter(pk=fighter1.pk)

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_houses": [house2.pk],
            "_selected_action": [fighter1.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterAdmin(ContentFighter, admin_site)
    response = copy_selected_to_house(model_admin, request, queryset)

    assert response is None

    # Check that the fighter and all its related data were copied
    copied_fighter = ContentFighter.objects.filter(
        house=house2, type="Fighter 1"
    ).first()
    assert copied_fighter is not None

    # Check equipment list items were copied
    equipment_items = ContentFighterEquipmentListItem.objects.filter(
        fighter=copied_fighter
    )
    assert equipment_items.count() == 1
    assert equipment_items.first().equipment == equipment

    # Check default assignments were copied
    default_assignments = ContentFighterDefaultAssignment.objects.filter(
        fighter=copied_fighter
    )
    assert default_assignments.count() == 1
    assert default_assignments.first().equipment == equipment

    # Check weapon accessories were copied
    accessories = ContentFighterEquipmentListWeaponAccessory.objects.filter(
        fighter=copied_fighter
    )
    assert accessories.count() == 1
    assert accessories.first().weapon_accessory == accessory


@pytest.mark.django_db
def test_copy_selected_to_house_transaction_rollback(
    admin_site, request_factory, admin_user, test_fighters, monkeypatch
):
    fighter1, _, _ = test_fighters
    queryset = ContentFighter.objects.filter(pk=fighter1.pk)

    # Mock copy_to_house to raise an exception
    def mock_copy_to_house(self, house):
        raise Exception("Test exception")

    monkeypatch.setattr(ContentFighter, "copy_to_house", mock_copy_to_house)

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_houses": ["99999"],  # This will cause ContentHouse.DoesNotExist
            "_selected_action": [fighter1.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterAdmin(ContentFighter, admin_site)
    response = copy_selected_to_house(model_admin, request, queryset)

    assert response is None

    # Verify original fighter is unchanged
    fighter1.refresh_from_db()
    assert ContentFighter.objects.filter(pk=fighter1.pk).exists()


@pytest.mark.django_db
def test_copy_selected_to_fighter_multiple_items_multiple_targets(
    admin_site, request_factory, admin_user, test_equipment_items, test_fighters
):
    item1, item2, *_ = test_equipment_items
    _, fighter2, fighter3 = test_fighters

    # Get both items
    queryset = ContentFighterEquipmentListItem.objects.filter(
        pk__in=[item1.pk, item2.pk]
    )

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_fighters": [fighter2.pk, fighter3.pk],
            "_selected_action": [item1.pk, item2.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterEquipmentListItemAdmin(
        ContentFighterEquipmentListItem, admin_site
    )
    response = copy_selected_to_fighter(model_admin, request, queryset)

    assert response is None

    # Each fighter should get 2 items (2 items × 2 fighters = 4 new items total)
    assert ContentFighterEquipmentListItem.objects.filter(fighter=fighter2).count() == 2
    assert ContentFighterEquipmentListItem.objects.filter(fighter=fighter3).count() == 2

    # Total items should be original 2 + 4 new = 6
    assert ContentFighterEquipmentListItem.objects.count() == 6


@pytest.mark.django_db
def test_copy_selected_to_house_multiple_fighters(
    admin_site, request_factory, admin_user, test_fighters, test_houses
):
    fighter1, _, fighter3 = test_fighters
    _, house2, _ = test_houses

    queryset = ContentFighter.objects.filter(pk__in=[fighter1.pk, fighter3.pk])

    initial_fighter_count = ContentFighter.objects.count()

    request = request_factory.post(
        "/admin/",
        {
            "post": "yes",
            "to_houses": [house2.pk],
            "_selected_action": [fighter1.pk, fighter3.pk],
        },
    )
    request.user = admin_user
    request._messages = BaseStorage(request)

    model_admin = ContentFighterAdmin(ContentFighter, admin_site)
    response = copy_selected_to_house(model_admin, request, queryset)

    assert response is None

    # Should have 2 new fighters in house2
    house2_fighters = ContentFighter.objects.filter(house=house2)
    # Original Fighter 2 + copied Fighter 1 and Fighter 3
    assert house2_fighters.count() == 3

    # Total fighters increased by 2
    assert ContentFighter.objects.count() == initial_fighter_count + 2
