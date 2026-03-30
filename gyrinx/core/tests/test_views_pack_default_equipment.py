"""Tests for pack fighter default equipment views."""

import pytest
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models.default_assignment import ContentFighterDefaultAssignment
from gyrinx.content.models.equipment import ContentEquipment, ContentEquipmentCategory
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


# -- Fighter edit page shows default equipment --


@pytest.mark.django_db
def test_default_equipment_tab_shows_section(client, group_user, pack, pack_fighter):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    response = client.get(
        reverse("core:pack-item-default-equipment", args=(pack.id, pack_item.id))
    )
    assert response.status_code == 200
    assert b"Default equipment" in response.content
    assert b"Add weapon" in response.content
    assert b"Add gear" in response.content


@pytest.mark.django_db
def test_default_equipment_tab_shows_existing_defaults(
    client, group_user, pack, pack_fighter, base_weapon, base_gear
):
    fighter, pack_item = pack_fighter
    ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_gear, cost=0
    )
    client.force_login(group_user)
    response = client.get(
        reverse("core:pack-item-default-equipment", args=(pack.id, pack_item.id))
    )
    assert response.status_code == 200
    assert b"Autogun" in response.content
    assert b"Mesh Armour" in response.content


# -- Add default weapon --


@pytest.mark.django_db
def test_add_default_weapon_get(client, group_user, pack, pack_fighter, base_weapon):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Add default weapon" in response.content
    assert b"Autogun" in response.content


@pytest.mark.django_db
def test_add_default_weapon_post(client, group_user, pack, pack_fighter, base_weapon):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id))
    response = client.post(url, {"content_equipment": str(base_weapon.pk)})
    assert response.status_code == 302
    assert ContentFighterDefaultAssignment.objects.filter(
        fighter=fighter, equipment=base_weapon
    ).exists()


@pytest.mark.django_db
def test_add_default_weapon_with_profiles(
    client, group_user, pack, pack_fighter, weapon_with_profiles
):
    fighter, pack_item = pack_fighter
    non_standard = ContentWeaponProfile.objects.filter(
        equipment=weapon_with_profiles, cost__gt=0
    ).first()
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id))
    response = client.post(
        url,
        {
            "content_equipment": str(weapon_with_profiles.pk),
            "weapon_profiles_field": [str(non_standard.pk)],
        },
    )
    assert response.status_code == 302
    assignment = ContentFighterDefaultAssignment.objects.get(
        fighter=fighter, equipment=weapon_with_profiles
    )
    assert non_standard in assignment.weapon_profiles_field.all()


@pytest.mark.django_db
def test_add_default_weapon_duplicate_rejected(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id))
    response = client.post(url, {"content_equipment": str(base_weapon.pk)})
    assert response.status_code == 200
    assert b"already assigned" in response.content
    assert (
        ContentFighterDefaultAssignment.objects.filter(
            fighter=fighter, equipment=base_weapon
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_add_default_weapon_search(client, group_user, pack, pack_fighter, base_weapon):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id))
    response = client.get(url, {"q": "Autogun"})
    assert response.status_code == 200
    assert b"Autogun" in response.content


# -- Add default gear --


@pytest.mark.django_db
def test_add_default_gear_get(client, group_user, pack, pack_fighter, base_gear):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-gear-add", args=(pack.id, pack_item.id))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Add default gear" in response.content
    assert b"Mesh Armour" in response.content


@pytest.mark.django_db
def test_add_default_gear_post(client, group_user, pack, pack_fighter, base_gear):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-gear-add", args=(pack.id, pack_item.id))
    response = client.post(url, {"content_equipment": str(base_gear.pk)})
    assert response.status_code == 302
    assert ContentFighterDefaultAssignment.objects.filter(
        fighter=fighter, equipment=base_gear
    ).exists()


@pytest.mark.django_db
def test_add_default_gear_duplicate_rejected(
    client, group_user, pack, pack_fighter, base_gear
):
    fighter, pack_item = pack_fighter
    ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_gear, cost=0
    )
    client.force_login(group_user)
    url = reverse("core:pack-fighter-default-gear-add", args=(pack.id, pack_item.id))
    response = client.post(url, {"content_equipment": str(base_gear.pk)})
    assert response.status_code == 200
    assert b"already assigned" in response.content


# -- Remove default assignment --


@pytest.mark.django_db
def test_remove_default_assignment_get(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-default-assignment-remove",
        args=(pack.id, pack_item.id, assignment.id),
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Autogun" in response.content
    assert b"Warning" in response.content
    assert b"immediately affect" in response.content


@pytest.mark.django_db
def test_remove_default_assignment_post(
    client, group_user, pack, pack_fighter, base_weapon
):
    fighter, pack_item = pack_fighter
    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    client.force_login(group_user)
    url = reverse(
        "core:pack-fighter-default-assignment-remove",
        args=(pack.id, pack_item.id, assignment.id),
    )
    response = client.post(url)
    assert response.status_code == 302
    assert not ContentFighterDefaultAssignment.objects.filter(pk=assignment.pk).exists()


# -- Permission checks --


@pytest.mark.django_db
def test_non_owner_cannot_access_add_weapon(
    client, make_user, pack, pack_fighter, custom_content_group
):
    fighter, pack_item = pack_fighter
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse("core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id))
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
    url = reverse("core:pack-fighter-default-gear-add", args=(pack.id, pack_item.id))
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_non_owner_cannot_remove_assignment(
    client, make_user, pack, pack_fighter, base_weapon, custom_content_group
):
    fighter, pack_item = pack_fighter
    assignment = ContentFighterDefaultAssignment.objects.create(
        fighter=fighter, equipment=base_weapon, cost=0
    )
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse(
        "core:pack-fighter-default-assignment-remove",
        args=(pack.id, pack_item.id, assignment.id),
    )
    response = client.post(url)
    assert response.status_code == 404
    assert ContentFighterDefaultAssignment.objects.filter(pk=assignment.pk).exists()


# -- Default equipment tab --


@pytest.mark.django_db
def test_default_equipment_tab_requires_login(client, pack, pack_fighter):
    fighter, pack_item = pack_fighter
    url = reverse("core:pack-item-default-equipment", args=(pack.id, pack_item.id))
    response = client.get(url)
    assert response.status_code == 302
    assert "/accounts/login/" in response.url


@pytest.mark.django_db
def test_default_equipment_tab_requires_pack_owner(
    client, pack, pack_fighter, make_user, custom_content_group
):
    fighter, pack_item = pack_fighter
    other_user = make_user("other", "password")
    other_user.groups.add(custom_content_group)
    client.force_login(other_user)
    url = reverse("core:pack-item-default-equipment", args=(pack.id, pack_item.id))
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_edit_page_shows_tabs_for_fighter(client, group_user, pack, pack_fighter):
    fighter, pack_item = pack_fighter
    client.force_login(group_user)
    response = client.get(reverse("core:pack-edit-item", args=(pack.id, pack_item.id)))
    assert response.status_code == 200
    assert b"Default equipment" in response.content
    assert b"Equipment list" in response.content
    assert b"Details" in response.content
