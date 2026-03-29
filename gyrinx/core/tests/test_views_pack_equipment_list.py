"""Tests for pack fighter equipment list views."""

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
from gyrinx.content.models.equipment_list import ContentFighterEquipmentListItem
from gyrinx.content.models.weapon import ContentWeaponProfile
from gyrinx.core.models.pack import CustomContentPack, CustomContentPackItem


@pytest.fixture
def custom_content_group():
    group, _ = Group.objects.get_or_create(name="Custom Content")
    return group


@pytest.fixture
def group_user(user, custom_content_group):
    user.groups.add(custom_content_group)
    return user


@pytest.fixture
def pack(group_user):
    return CustomContentPack.objects.create(
        name="Test Pack",
        summary="A test pack",
        listed=True,
        owner=group_user,
    )


@pytest.fixture
def pack_fighter(pack, make_content_fighter, content_house):
    fighter = make_content_fighter("Pack Fighter", "ganger", content_house, 50)
    ct = ContentType.objects.get_for_model(fighter)
    pack_item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    return fighter, pack_item


@pytest.fixture
def weapon_category():
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons",
        defaults={"group": "Weapons & Ammo"},
    )
    return cat


@pytest.fixture
def gear_category():
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Personal Equipment",
        defaults={"group": "Gear"},
    )
    return cat


@pytest.fixture
def base_weapon(weapon_category):
    weapon = ContentEquipment.objects.create(
        name="Autogun",
        category=weapon_category,
        cost="15",
    )
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",
        range_short="8",
        range_long="24",
        accuracy_short="+1",
        accuracy_long="-",
        strength="3",
        armour_piercing="-",
        damage="1",
        ammo="4+",
        cost=0,
    )
    return weapon


@pytest.fixture
def weapon_with_profiles(weapon_category):
    weapon = ContentEquipment.objects.create(
        name="Combi-weapon",
        category=weapon_category,
        cost="35",
    )
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="",
        range_short="8",
        range_long="24",
        accuracy_short="+1",
        accuracy_long="-",
        strength="3",
        armour_piercing="-",
        damage="1",
        ammo="4+",
        cost=0,
    )
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Grenade Launcher",
        range_short="6",
        range_long="24",
        accuracy_short="-1",
        accuracy_long="-",
        strength="6",
        armour_piercing="-2",
        damage="2",
        ammo="6+",
        cost=15,
    )
    return weapon


@pytest.fixture
def base_gear(gear_category):
    return ContentEquipment.objects.create(
        name="Mesh Armour",
        category=gear_category,
        cost="15",
    )


# -- Fighter edit page shows equipment list section --


@pytest.mark.django_db
def test_edit_page_shows_equipment_list_section(client, group_user, pack, pack_fighter):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert b"Equipment list" in response.content
    assert b"Add weapon" in response.content
    assert b"Add gear" in response.content


@pytest.mark.django_db
def test_edit_page_shows_existing_equipment_list_items(
    client, group_user, pack, pack_fighter, base_weapon, base_gear
):
    fighter, pack_item = pack_fighter
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_gear, cost=0
    )
    client.force_login(group_user)
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert b"Autogun" in response.content
    assert b"Mesh Armour" in response.content


@pytest.mark.django_db
def test_edit_page_shows_equipment_list_cost(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=25
    )
    client.force_login(group_user)
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert "25¢".encode() in response.content


@pytest.mark.django_db
def test_edit_page_shows_paid_profile_when_added(
    client, group_user, pack, pack_fighter, weapon_with_profiles
):
    """A paid profile added to the equipment list should display on the edit page."""
    fighter, pack_item = pack_fighter
    non_standard = ContentWeaponProfile.objects.get(
        equipment=weapon_with_profiles, cost__gt=0
    )
    # Add the base weapon and the paid profile.
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=weapon_with_profiles, weapon_profile=None, cost=35
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter,
        equipment=weapon_with_profiles,
        weapon_profile=non_standard,
        cost=15,
    )
    client.force_login(group_user)
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert b"Combi-weapon" in response.content
    assert b"Grenade Launcher" in response.content


@pytest.mark.django_db
def test_edit_page_shows_pack_weapon_profile_in_equipment_list(
    client, group_user, pack, pack_fighter, weapon_category
):
    """A pack-created weapon profile should display when added to equipment list."""
    fighter, pack_item = pack_fighter
    # Create a base-game weapon.
    weapon = ContentEquipment.objects.create(
        name="Combat Shotgun", category=weapon_category, cost="60"
    )
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Scatter",
        cost=0,
        range_short="4",
        range_long="12",
        accuracy_short="-",
        accuracy_long="-",
        strength="2",
        armour_piercing="-",
        damage="1",
        ammo="4+",
    )
    ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Slug",
        cost=0,
        range_short="4",
        range_long="24",
        accuracy_short="-",
        accuracy_long="-",
        strength="4",
        armour_piercing="-1",
        damage="2",
        ammo="4+",
    )
    # Create a PACK profile for this weapon.
    pack_profile = ContentWeaponProfile.objects.create(
        equipment=weapon,
        name="Executioner",
        cost=20,
        range_short="4",
        range_long="12",
        accuracy_short="-",
        accuracy_long="-",
        strength="5",
        armour_piercing="-2",
        damage="2",
        ammo="5+",
    )
    # Register the pack profile as a pack item.
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    CustomContentPackItem.objects.create(
        pack=pack, content_type=profile_ct, object_id=pack_profile.pk, owner=pack.owner
    )
    # Add to equipment list: base weapon + pack profile.
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=weapon, weapon_profile=None, cost=60
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=weapon, weapon_profile=pack_profile, cost=20
    )
    client.force_login(group_user)
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert b"Combat Shotgun" in response.content
    # Simplified display shows profile names for non-standard profiles only.
    assert b"Executioner" in response.content
    # Cost values should be visible.
    assert "60¢".encode() in response.content
    assert "20¢".encode() in response.content


# -- Add equipment list weapon --


@pytest.mark.django_db
def test_add_equipment_list_weapon_get(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Configure equipment list" in response.content
    assert b"Autogun" in response.content


@pytest.mark.django_db
def test_add_equipment_list_weapon_post(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.post(
        url,
        {"equipment": [str(base_weapon.pk)], f"cost_{base_weapon.pk}": "20"},
    )
    assert response.status_code == 302
    eli = ContentFighterEquipmentListItem.objects.get(
        fighter=fighter, equipment=base_weapon, weapon_profile=None
    )
    assert eli.cost == 20


@pytest.mark.django_db
def test_add_equipment_list_weapon_with_profiles(
    client, group_user, pack, pack_fighter, weapon_with_profiles
):
    fighter, pack_item = pack_fighter
    non_standard = ContentWeaponProfile.objects.get(
        equipment=weapon_with_profiles, cost__gt=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.post(
        url,
        {
            "equipment": [str(weapon_with_profiles.pk)],
            f"cost_{weapon_with_profiles.pk}": "35",
            "profiles": [str(non_standard.pk)],
            f"profile_cost_{non_standard.pk}": "15",
        },
    )
    assert response.status_code == 302
    # Base weapon entry.
    base_eli = ContentFighterEquipmentListItem.objects.get(
        fighter=fighter, equipment=weapon_with_profiles, weapon_profile=None
    )
    assert base_eli.cost == 35
    # Profile entry.
    profile_eli = ContentFighterEquipmentListItem.objects.get(
        fighter=fighter, equipment=weapon_with_profiles, weapon_profile=non_standard
    )
    assert profile_eli.cost == 15


@pytest.mark.django_db
def test_add_equipment_list_weapon_duplicate_rejected(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.post(url, {"equipment": [str(base_weapon.pk)]})
    assert response.status_code == 200
    assert b"already in the available equipment list" in response.content
    assert (
        ContentFighterEquipmentListItem.objects.filter(
            fighter=fighter, equipment=base_weapon
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_add_equipment_list_weapon_page_shows_all_weapons(
    client, group_user, pack, pack_fighter, base_weapon, weapon_with_profiles
):
    """All weapons appear on the page (filtering is client-side)."""
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Autogun" in response.content
    assert b"Combi-weapon" in response.content


@pytest.mark.django_db
def test_add_equipment_list_weapon_bulk(
    client, group_user, pack, pack_fighter, base_weapon, weapon_with_profiles
):
    """Bulk-adding multiple weapons at once."""
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.post(
        url,
        {
            "equipment": [str(base_weapon.pk), str(weapon_with_profiles.pk)],
            f"cost_{base_weapon.pk}": "10",
            f"cost_{weapon_with_profiles.pk}": "30",
        },
    )
    assert response.status_code == 302
    assert ContentFighterEquipmentListItem.objects.filter(
        fighter=fighter, equipment=base_weapon
    ).exists()
    assert ContentFighterEquipmentListItem.objects.filter(
        fighter=fighter, equipment=weapon_with_profiles
    ).exists()


# -- Add equipment list gear --


@pytest.mark.django_db
def test_add_equipment_list_gear_get(client, group_user, pack, pack_fighter, base_gear):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-gear-add", args=(pack.id, pack_item.id)
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Configure equipment list" in response.content
    assert b"Mesh Armour" in response.content


@pytest.mark.django_db
def test_add_equipment_list_gear_post(
    client, group_user, pack, pack_fighter, base_gear
):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-gear-add", args=(pack.id, pack_item.id)
    )
    response = client.post(
        url,
        {"equipment": [str(base_gear.pk)], f"cost_{base_gear.pk}": "10"},
    )
    assert response.status_code == 302
    eli = ContentFighterEquipmentListItem.objects.get(
        fighter=fighter, equipment=base_gear
    )
    assert eli.cost == 10


@pytest.mark.django_db
def test_add_equipment_list_gear_duplicate_rejected(
    client, group_user, pack, pack_fighter, base_gear
):
    fighter, pack_item = pack_fighter
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_gear, cost=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-gear-add", args=(pack.id, pack_item.id)
    )
    response = client.post(url, {"equipment": [str(base_gear.pk)]})
    assert response.status_code == 200
    assert b"already in the available equipment list" in response.content


# -- Remove equipment list item --


@pytest.mark.django_db
def test_remove_equipment_list_item_get(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-item-remove",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Autogun" in response.content
    assert b"Remove" in response.content


@pytest.mark.django_db
def test_remove_equipment_list_item_shows_sibling_profiles(
    client, group_user, pack, pack_fighter, base_weapon
):
    """Removal confirmation shows weapon profiles that will also be removed."""
    fighter, pack_item = pack_fighter
    # Base weapon entry (no profile)
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    # Add a non-standard profile entry
    profile = ContentWeaponProfile.objects.create(
        equipment=base_weapon,
        name="Focused beam",
        range_short="12",
        range_long="24",
        accuracy_short="+1",
        accuracy_long="-",
        strength="4",
        armour_piercing="-1",
        damage="2",
        ammo="4+",
        cost=5,
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, weapon_profile=profile, cost=5
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-item-remove",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Focused beam" in response.content


@pytest.mark.django_db
def test_remove_equipment_list_item_post(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-item-remove",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.post(url)
    assert response.status_code == 302
    assert not ContentFighterEquipmentListItem.objects.filter(pk=eli.pk).exists()


# -- Edit equipment list item --


@pytest.mark.django_db
def test_edit_equipment_list_item_get(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=15
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-edit",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Autogun" in response.content
    assert b'value="15"' in response.content


@pytest.mark.django_db
def test_edit_equipment_list_item_post(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=15
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-edit",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.post(url, {f"cost_{eli.pk}": "25"})
    assert response.status_code == 302
    eli.refresh_from_db()
    assert eli.cost == 25


@pytest.mark.django_db
def test_edit_equipment_list_weapon_group(
    client, group_user, pack, pack_fighter, weapon_with_profiles
):
    """Editing a weapon group updates costs for base and profile items."""
    fighter, pack_item = pack_fighter
    non_standard = ContentWeaponProfile.objects.get(
        equipment=weapon_with_profiles, cost__gt=0
    )
    base_eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=weapon_with_profiles, weapon_profile=None, cost=35
    )
    profile_eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter,
        equipment=weapon_with_profiles,
        weapon_profile=non_standard,
        cost=15,
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-equipment-list-edit",
        args=(pack.id, pack_item.id, base_eli.id),
    )
    response = client.post(
        url, {f"cost_{base_eli.pk}": "40", f"cost_{profile_eli.pk}": "20"}
    )
    assert response.status_code == 302
    base_eli.refresh_from_db()
    profile_eli.refresh_from_db()
    assert base_eli.cost == 40
    assert profile_eli.cost == 20


# -- Permission checks --


@pytest.mark.django_db
def test_non_owner_cannot_access_add_weapon(
    client, make_user, pack, pack_fighter, custom_content_group
):
    fighter, pack_item = pack_fighter
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_non_owner_cannot_access_add_gear(
    client, make_user, pack, pack_fighter, custom_content_group
):
    fighter, pack_item = pack_fighter
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse(
        "core:pack-fighter-equipment-list-gear-add", args=(pack.id, pack_item.id)
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_non_owner_cannot_remove_item(
    client, make_user, pack, pack_fighter, base_weapon, custom_content_group
):
    fighter, pack_item = pack_fighter
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse(
        "core:pack-fighter-equipment-list-item-remove",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.post(url)
    assert response.status_code == 404
    assert ContentFighterEquipmentListItem.objects.filter(pk=eli.pk).exists()


@pytest.mark.django_db
def test_non_owner_cannot_edit_item(
    client, make_user, pack, pack_fighter, base_weapon, custom_content_group
):
    fighter, pack_item = pack_fighter
    eli = ContentFighterEquipmentListItem.objects.create(
        fighter=fighter, equipment=base_weapon, cost=10
    )
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse(
        "core:pack-fighter-equipment-list-edit",
        args=(pack.id, pack_item.id, eli.id),
    )
    response = client.get(url)
    assert response.status_code == 404
    response = client.post(url, {f"cost_{eli.pk}": "99"})
    assert response.status_code == 404
    eli.refresh_from_db()
    assert eli.cost == 10
