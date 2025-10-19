import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.models import List, ListFighter, ListFighterEquipmentAssignment

User = get_user_model()


@pytest.fixture
def campaign_list_with_credits(db, user, house, campaign):
    lst = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        credits_current=1000,
        credits_earned=1000,
    )
    return lst


@pytest.fixture
def campaign_list_low_credits(db, user, house, campaign):
    lst = List.objects.create(
        name="Poor Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        credits_current=50,
        credits_earned=50,
    )
    return lst


@pytest.fixture
def list_building_list(db, user, house):
    lst = List.objects.create(
        name="List Building Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
        credits_current=1000,
        credits_earned=1000,
    )
    return lst


@pytest.fixture
def fighter_in_campaign(user, campaign_list_with_credits, content_fighter):
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=campaign_list_with_credits,
        owner=user,
    )
    return fighter


@pytest.fixture
def fighter_in_low_credit_campaign(user, campaign_list_low_credits, content_fighter):
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=campaign_list_low_credits,
        owner=user,
    )
    return fighter


@pytest.fixture
def fighter_in_list_building(user, list_building_list, content_fighter):
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=list_building_list,
        owner=user,
    )
    return fighter


@pytest.fixture
def weapon_equipment(content_equipment_categories):
    weapon_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons",
        defaults={"group": "Weapons & Ammo"},
    )
    return ContentEquipment.objects.create(
        name="Autogun",
        cost="15",
        category=weapon_cat,
    )


@pytest.fixture
def gear_equipment(content_equipment_categories):
    gear_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Armour",
        defaults={"group": "Gear"},
    )
    return ContentEquipment.objects.create(
        name="Flak Armour",
        cost="10",
        category=gear_cat,
    )


@pytest.fixture
def weapon_profile(weapon_equipment, make_weapon_profile):
    return make_weapon_profile(
        equipment=weapon_equipment,
        name="Long-las Profile",
        cost=5,
    )


@pytest.fixture
def weapon_accessory(make_weapon_accessory):
    return make_weapon_accessory(
        name="Telescopic Sight",
        cost=10,
    )


@pytest.fixture
def equipment_upgrade(weapon_equipment):
    return ContentEquipmentUpgrade.objects.create(
        name="Master-crafted",
        equipment=weapon_equipment,
        cost=20,
        position=1,
    )


@pytest.mark.django_db
def test_add_weapon_in_campaign_spends_credits(
    client, user, campaign_list_with_credits, fighter_in_campaign, weapon_equipment
):
    client.login(username="testuser", password="password")
    initial_credits = campaign_list_with_credits.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapons-edit",
            args=(campaign_list_with_credits.id, fighter_in_campaign.id),
        ),
        {
            "content_equipment": weapon_equipment.id,
        },
    )

    assert response.status_code == 302

    campaign_list_with_credits.refresh_from_db()
    assert (
        campaign_list_with_credits.credits_current
        == initial_credits - weapon_equipment.cost_int()
    )

    assert ListFighterEquipmentAssignment.objects.filter(
        list_fighter=fighter_in_campaign,
        content_equipment=weapon_equipment,
    ).exists()


@pytest.mark.django_db
def test_add_weapon_insufficient_credits(
    client,
    user,
    campaign_list_low_credits,
    fighter_in_low_credit_campaign,
    weapon_equipment,
):
    client.login(username="testuser", password="password")

    weapon_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Special Weapons",
        defaults={"group": "Weapons & Ammo"},
    )
    expensive_weapon = ContentEquipment.objects.create(
        name="Expensive Gun",
        cost="100",
        category=weapon_cat,
    )

    response = client.post(
        reverse(
            "core:list-fighter-weapons-edit",
            args=(campaign_list_low_credits.id, fighter_in_campaign.id),
        ),
        {
            "content_equipment": expensive_weapon.id,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Insufficient credits" in content

    campaign_list_low_credits.refresh_from_db()
    assert campaign_list_low_credits.credits_current == 50

    assert not ListFighterEquipmentAssignment.objects.filter(
        list_fighter=fighter_in_low_credit_campaign,
        content_equipment=expensive_weapon,
    ).exists()


@pytest.mark.django_db
def test_add_weapon_in_list_building_no_credit_check(
    client, user, list_building_list, fighter_in_list_building, weapon_equipment
):
    client.login(username="testuser", password="password")
    initial_credits = list_building_list.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapons-edit",
            args=(list_building_list.id, fighter_in_list_building.id),
        ),
        {
            "content_equipment": weapon_equipment.id,
        },
    )

    assert response.status_code == 302

    list_building_list.refresh_from_db()
    assert list_building_list.credits_current == initial_credits

    assert ListFighterEquipmentAssignment.objects.filter(
        list_fighter=fighter_in_list_building,
        content_equipment=weapon_equipment,
    ).exists()


@pytest.mark.django_db
def test_add_accessory_in_campaign_spends_credits(
    client,
    user,
    campaign_list_with_credits,
    fighter_in_campaign,
    weapon_equipment,
    weapon_accessory,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_campaign,
        content_equipment=weapon_equipment,
    )

    initial_credits = campaign_list_with_credits.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapon-accessories-edit",
            args=(campaign_list_with_credits.id, fighter_in_campaign.id, assignment.id),
        ),
        {
            "accessory_id": weapon_accessory.id,
        },
    )

    assert response.status_code == 302

    campaign_list_with_credits.refresh_from_db()
    assert (
        campaign_list_with_credits.credits_current
        == initial_credits - weapon_accessory.cost_int()
    )

    assignment.refresh_from_db()
    assert weapon_accessory in assignment.weapon_accessories_field.all()


@pytest.mark.django_db
def test_add_accessory_insufficient_credits(
    client,
    user,
    campaign_list_low_credits,
    fighter_in_low_credit_campaign,
    weapon_equipment,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_low_credit_campaign,
        content_equipment=weapon_equipment,
    )

    expensive_accessory = ContentWeaponAccessory.objects.create(
        name="Expensive Scope",
        cost=100,
    )

    response = client.post(
        reverse(
            "core:list-fighter-weapon-accessories-edit",
            args=(campaign_list_low_credits.id, fighter_in_campaign.id, assignment.id),
        ),
        {
            "accessory_id": expensive_accessory.id,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Insufficient credits" in content

    campaign_list_low_credits.refresh_from_db()
    assert campaign_list_low_credits.credits_current == 50

    assignment.refresh_from_db()
    assert expensive_accessory not in assignment.weapon_accessories_field.all()


@pytest.mark.django_db
def test_add_accessory_in_list_building_no_credit_check(
    client,
    user,
    list_building_list,
    fighter_in_list_building,
    weapon_equipment,
    weapon_accessory,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_list_building,
        content_equipment=weapon_equipment,
    )

    initial_credits = list_building_list.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapon-accessories-edit",
            args=(list_building_list.id, fighter_in_list_building.id, assignment.id),
        ),
        {
            "accessory_id": weapon_accessory.id,
        },
    )

    assert response.status_code == 302

    list_building_list.refresh_from_db()
    assert list_building_list.credits_current == initial_credits

    assignment.refresh_from_db()
    assert weapon_accessory in assignment.weapon_accessories_field.all()


@pytest.mark.django_db
def test_add_weapon_profile_in_campaign_spends_credits(
    client,
    user,
    campaign_list_with_credits,
    fighter_in_campaign,
    weapon_equipment,
    weapon_profile,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_campaign,
        content_equipment=weapon_equipment,
    )

    initial_credits = campaign_list_with_credits.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapon-edit",
            args=(campaign_list_with_credits.id, fighter_in_campaign.id, assignment.id),
        ),
        {
            "profile_id": weapon_profile.id,
        },
    )

    assert response.status_code == 302

    campaign_list_with_credits.refresh_from_db()
    assert (
        campaign_list_with_credits.credits_current
        == initial_credits - weapon_profile.cost_int()
    )

    assignment.refresh_from_db()
    assert weapon_profile in assignment.weapon_profiles_field.all()


@pytest.mark.django_db
def test_add_weapon_profile_insufficient_credits(
    client,
    user,
    campaign_list_low_credits,
    fighter_in_low_credit_campaign,
    weapon_equipment,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_low_credit_campaign,
        content_equipment=weapon_equipment,
    )

    expensive_profile = ContentWeaponProfile.objects.create(
        name="Expensive Profile",
        equipment=weapon_equipment,
        cost=100,
    )

    response = client.post(
        reverse(
            "core:list-fighter-weapon-edit",
            args=(campaign_list_low_credits.id, fighter_in_campaign.id, assignment.id),
        ),
        {
            "profile_id": expensive_profile.id,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Insufficient credits" in content

    campaign_list_low_credits.refresh_from_db()
    assert campaign_list_low_credits.credits_current == 50

    assignment.refresh_from_db()
    assert expensive_profile not in assignment.weapon_profiles_field.all()


@pytest.mark.django_db
def test_add_weapon_profile_in_list_building_no_credit_check(
    client,
    user,
    list_building_list,
    fighter_in_list_building,
    weapon_equipment,
    weapon_profile,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_list_building,
        content_equipment=weapon_equipment,
    )

    initial_credits = list_building_list.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapon-edit",
            args=(list_building_list.id, fighter_in_list_building.id, assignment.id),
        ),
        {
            "profile_id": weapon_profile.id,
        },
    )

    assert response.status_code == 302

    list_building_list.refresh_from_db()
    assert list_building_list.credits_current == initial_credits

    assignment.refresh_from_db()
    assert weapon_profile in assignment.weapon_profiles_field.all()


@pytest.mark.django_db
def test_add_equipment_upgrade_in_campaign_spends_credits(
    client,
    user,
    campaign_list_with_credits,
    fighter_in_campaign,
    weapon_equipment,
    equipment_upgrade,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_campaign,
        content_equipment=weapon_equipment,
    )

    initial_credits = campaign_list_with_credits.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapon-upgrade-edit",
            args=(
                campaign_list_with_credits.id,
                fighter_in_campaign.id,
                assignment.id,
            ),
        ),
        {
            "upgrades_field": [equipment_upgrade.id],
        },
    )

    assert response.status_code == 302

    campaign_list_with_credits.refresh_from_db()
    assert (
        campaign_list_with_credits.credits_current
        == initial_credits - equipment_upgrade.cost_int()
    )

    assignment.refresh_from_db()
    assert equipment_upgrade in assignment.upgrades_field.all()


@pytest.mark.django_db
def test_add_equipment_upgrade_insufficient_credits(
    client,
    user,
    campaign_list_low_credits,
    fighter_in_low_credit_campaign,
    weapon_equipment,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_low_credit_campaign,
        content_equipment=weapon_equipment,
    )

    expensive_upgrade = ContentEquipmentUpgrade.objects.create(
        name="Expensive Upgrade",
        equipment=weapon_equipment,
        cost=100,
        position=1,
    )

    response = client.post(
        reverse(
            "core:list-fighter-weapon-upgrade-edit",
            args=(
                campaign_list_low_credits.id,
                fighter_in_campaign.id,
                assignment.id,
                "core:list-fighter-weapons-edit",
                "core:list-fighter-weapon-upgrade-edit",
            ),
        ),
        {
            "upgrades_field": [expensive_upgrade.id],
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Insufficient credits" in content

    campaign_list_low_credits.refresh_from_db()
    assert campaign_list_low_credits.credits_current == 50

    assignment.refresh_from_db()
    assert expensive_upgrade not in assignment.upgrades_field.all()


@pytest.mark.django_db
def test_add_equipment_upgrade_in_list_building_no_credit_check(
    client,
    user,
    list_building_list,
    fighter_in_list_building,
    weapon_equipment,
    equipment_upgrade,
):
    client.login(username="testuser", password="password")

    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter_in_list_building,
        content_equipment=weapon_equipment,
    )

    initial_credits = list_building_list.credits_current

    response = client.post(
        reverse(
            "core:list-fighter-weapon-upgrade-edit",
            args=(
                list_building_list.id,
                fighter_in_list_building.id,
                assignment.id,
            ),
        ),
        {
            "upgrades_field": [equipment_upgrade.id],
        },
    )

    assert response.status_code == 302

    list_building_list.refresh_from_db()
    assert list_building_list.credits_current == initial_credits

    assignment.refresh_from_db()
    assert equipment_upgrade in assignment.upgrades_field.all()
