"""Tests for customising existing (library) weapons in content packs."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
)
from gyrinx.content.models.default_assignment import ContentFighterDefaultAssignment
from gyrinx.content.models.weapon import ContentWeaponProfile
from gyrinx.core.models.list import ListFighter
from gyrinx.core.models.pack import CustomContentPackItem


def _add_to_pack(pack, obj):
    """Helper to associate a content object with a pack."""
    ct = ContentType.objects.get_for_model(type(obj))
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=obj.pk, owner=pack.owner
    )


@pytest.fixture
def weapon_category():
    return ContentEquipmentCategory.objects.create(
        name="Customise Weapon Tests", group="Weapons & Ammo"
    )


@pytest.fixture
def library_weapon(weapon_category):
    weapon = ContentEquipment.objects.create(
        name="Library Lasgun", category=weapon_category, cost=10
    )
    # A standard library profile so the equipment is recognised as a weapon.
    ContentWeaponProfile.objects.create(
        equipment=weapon, name="", cost=0, range_short="8", range_long="24"
    )
    return weapon


# --- Picker -------------------------------------------------------------------


@pytest.mark.django_db
def test_picker_shows_library_weapons(client, user, pack, library_weapon):
    client.force_login(user)
    url = reverse("core:pack-customise-weapon-picker", args=(pack.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Library Lasgun" in response.content


@pytest.mark.django_db
def test_picker_excludes_pack_owned_weapon(client, user, pack, weapon_category):
    client.force_login(user)
    pack_weapon = ContentEquipment.objects.create(
        name="Pack Bolter", category=weapon_category, cost=20
    )
    ContentWeaponProfile.objects.create(equipment=pack_weapon, name="", cost=0)
    _add_to_pack(pack, pack_weapon)

    url = reverse("core:pack-customise-weapon-picker", args=(pack.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Pack Bolter" not in response.content


@pytest.mark.django_db
def test_picker_filters_by_q(client, user, pack, weapon_category):
    client.force_login(user)
    a = ContentEquipment.objects.create(
        name="Autopistol", category=weapon_category, cost=10
    )
    b = ContentEquipment.objects.create(
        name="Boltgun", category=weapon_category, cost=15
    )
    ContentWeaponProfile.objects.create(equipment=a, name="", cost=0)
    ContentWeaponProfile.objects.create(equipment=b, name="", cost=0)

    url = reverse("core:pack-customise-weapon-picker", args=(pack.id,))
    response = client.get(url + "?q=auto")
    assert response.status_code == 200
    assert b"Autopistol" in response.content
    assert b"Boltgun" not in response.content


@pytest.mark.django_db
def test_picker_requires_edit_permission(client, make_user, pack, library_weapon):
    other = make_user("other", "password")
    client.force_login(other)
    url = reverse("core:pack-customise-weapon-picker", args=(pack.id,))
    response = client.get(url)
    assert response.status_code == 404


# --- Customise weapon page ---------------------------------------------------


@pytest.mark.django_db
def test_customise_page_lists_existing_profiles(client, user, pack, library_weapon):
    client.force_login(user)
    url = reverse("core:pack-customise-weapon", args=(pack.id, library_weapon.id))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Library Lasgun" in response.content
    assert b"New profile" in response.content
    assert b"No customisations yet" in response.content


@pytest.mark.django_db
def test_customise_page_shows_pack_scoped_profile(client, user, pack, library_weapon):
    client.force_login(user)
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Inferno", cost=5
    )
    _add_to_pack(pack, profile)
    url = reverse("core:pack-customise-weapon", args=(pack.id, library_weapon.id))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Inferno" in response.content
    # Pack-scoped row exposes inline Edit + Archive links.
    assert (
        reverse(
            "core:pack-customise-weapon-profile-edit",
            args=(pack.id, library_weapon.id, profile.id),
        ).encode()
        in response.content
    )
    assert (
        reverse(
            "core:pack-customise-weapon-profile-delete",
            args=(pack.id, library_weapon.id, profile.id),
        ).encode()
        in response.content
    )


@pytest.mark.django_db
def test_customise_page_redirects_for_pack_owned_weapon(
    client, user, pack, weapon_category
):
    client.force_login(user)
    weapon = ContentEquipment.objects.create(
        name="Owned Weapon", category=weapon_category, cost=10
    )
    ContentWeaponProfile.objects.create(equipment=weapon, name="", cost=0)
    _add_to_pack(pack, weapon)

    url = reverse("core:pack-customise-weapon", args=(pack.id, weapon.id))
    response = client.get(url)
    # Redirects to the regular pack page item anchor.
    assert response.status_code == 302
    assert reverse("core:pack", args=(pack.id,)) in response["Location"]


# --- Add profile flow --------------------------------------------------------


@pytest.mark.django_db
def test_add_profile_creates_pack_item(client, user, pack, library_weapon):
    client.force_login(user)
    url = reverse(
        "core:pack-customise-weapon-profile-add", args=(pack.id, library_weapon.id)
    )
    response = client.get(url)
    assert response.status_code == 200

    response = client.post(
        url,
        data={
            "name": "Plasma Round",
            "cost": "10",
            "rarity": "C",
            "rarity_roll": "",
            "wp_range_short": "12",
            "wp_range_long": "24",
            "wp_accuracy_short": "+1",
            "wp_accuracy_long": "",
            "wp_strength": "6",
            "wp_armour_piercing": "-1",
            "wp_damage": "2",
            "wp_ammo": "5+",
        },
    )
    assert response.status_code == 302
    assert response["Location"].endswith(
        reverse("core:pack-customise-weapon", args=(pack.id, library_weapon.id))
    )

    profile = ContentWeaponProfile.objects.all_content().get(
        equipment=library_weapon, name="Plasma Round"
    )
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=profile_ct, object_id=profile.pk
    ).exists()


@pytest.mark.django_db
def test_add_profile_rejects_duplicate_name(client, user, pack, library_weapon):
    client.force_login(user)
    ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Hotshot", cost=4
    )
    url = reverse(
        "core:pack-customise-weapon-profile-add", args=(pack.id, library_weapon.id)
    )
    response = client.post(
        url,
        data={
            "name": "Hotshot",
            "cost": "4",
            "rarity": "C",
            "wp_range_short": "8",
            "wp_range_long": "24",
        },
    )
    assert response.status_code == 200
    assert b"already exists" in response.content


# --- Edit / delete profile ---------------------------------------------------


@pytest.mark.django_db
def test_edit_pack_scoped_profile(client, user, pack, library_weapon):
    client.force_login(user)
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon,
        name="Inferno",
        cost=5,
        range_short="8",
        range_long="20",
    )
    _add_to_pack(pack, profile)
    url = reverse(
        "core:pack-customise-weapon-profile-edit",
        args=(pack.id, library_weapon.id, profile.id),
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Inferno" in response.content

    response = client.post(
        url,
        data={
            "name": "Inferno",
            "cost": "8",
            "rarity": "R",
            "wp_range_short": "8",
            "wp_range_long": "20",
        },
    )
    assert response.status_code == 302
    profile.refresh_from_db()
    assert profile.cost == 8


@pytest.mark.django_db
def test_edit_library_profile_blocked(client, user, pack, library_weapon):
    """Editing a profile that isn't pack-scoped is not allowed."""
    client.force_login(user)
    library_profile = ContentWeaponProfile.objects.get(
        equipment=library_weapon, name=""
    )
    url = reverse(
        "core:pack-customise-weapon-profile-edit",
        args=(pack.id, library_weapon.id, library_profile.id),
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_delete_pack_scoped_profile_archives_pack_item(
    client, user, pack, library_weapon
):
    client.force_login(user)
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Inferno", cost=5
    )
    _add_to_pack(pack, profile)
    url = reverse(
        "core:pack-customise-weapon-profile-delete",
        args=(pack.id, library_weapon.id, profile.id),
    )
    response = client.post(url)
    assert response.status_code == 302
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    item = CustomContentPackItem.objects.get(
        pack=pack, content_type=profile_ct, object_id=profile.pk
    )
    assert item.archived


@pytest.mark.django_db
def test_archived_profiles_link_visible_after_archiving_only_profile(
    client, user, pack, library_weapon
):
    """Regression: after archiving a pack-scoped profile, the customise page
    must still show the "Archived profiles" link so the user can restore it.

    The bug was that the archived-count denominator used ``with_packs([pack])``,
    which excludes archived pack items — so the count came back 0 and the link
    disappeared.
    """
    client.force_login(user)
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Inferno", cost=5
    )
    _add_to_pack(pack, profile)

    # Archive the pack item.
    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    item = CustomContentPackItem.objects.get(
        pack=pack, content_type=profile_ct, object_id=profile.pk
    )
    item.archived = True
    item.save()

    url = reverse("core:pack-customise-weapon", args=(pack.id, library_weapon.id))
    response = client.get(url)
    assert response.status_code == 200
    archived_url = reverse(
        "core:pack-customise-weapon-archived-profiles",
        args=(pack.id, library_weapon.id),
    )
    assert archived_url.encode() in response.content


# --- Pack detail surfacing ---------------------------------------------------


@pytest.mark.django_db
def test_pack_detail_shows_customised_weapon(client, user, pack, library_weapon):
    client.force_login(user)
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Plasma Round", cost=10
    )
    _add_to_pack(pack, profile)
    url = reverse("core:pack", args=(pack.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Library Lasgun" in response.content
    assert b"Plasma Round" in response.content


@pytest.mark.django_db
def test_pack_detail_customised_weapon_not_shown_when_no_pack_profiles(
    client, user, pack, library_weapon
):
    """The library weapon should not appear in the pack page at all if no
    pack-scoped profiles are attached."""
    client.force_login(user)
    url = reverse("core:pack", args=(pack.id,))
    response = client.get(url)
    assert response.status_code == 200
    # Nothing customised — library weapon should not appear in the weapons section.
    assert b"Library Lasgun" not in response.content


# --- Subscribed list visibility ---------------------------------------------


@pytest.mark.django_db
def test_subscribed_list_sees_pack_scoped_profile(
    user, pack, library_weapon, make_list
):
    """A list subscribed to the pack should see the pack-scoped profile via
    with_packs filtering."""
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Plasma Round", cost=10
    )
    _add_to_pack(pack, profile)

    lst = make_list("Sub List")
    lst.packs.add(pack)

    visible = list(
        ContentWeaponProfile.objects.with_packs(lst.packs.all()).filter(
            equipment=library_weapon
        )
    )
    assert profile in visible


@pytest.mark.django_db
def test_unsubscribed_list_does_not_see_pack_scoped_profile(
    user, pack, library_weapon, make_list
):
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Plasma Round", cost=10
    )
    _add_to_pack(pack, profile)

    lst = make_list("Solo List")
    visible = list(
        ContentWeaponProfile.objects.with_packs(lst.packs.all()).filter(
            equipment=library_weapon
        )
    )
    assert profile not in visible


# --- Multi-pack safety ------------------------------------------------------


@pytest.mark.django_db
def test_delete_in_one_pack_does_not_affect_other_pack(
    client, user, make_pack, library_weapon
):
    """Archiving the pack item in one pack must leave the other pack's
    pack item alone."""
    client.force_login(user)
    pack_a = make_pack("Pack A")
    pack_b = make_pack("Pack B")
    profile = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Inferno", cost=5
    )
    _add_to_pack(pack_a, profile)
    _add_to_pack(pack_b, profile)

    url = reverse(
        "core:pack-customise-weapon-profile-delete",
        args=(pack_a.id, library_weapon.id, profile.id),
    )
    response = client.post(url)
    assert response.status_code == 302

    profile_ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    a_item = CustomContentPackItem.objects.get(
        pack=pack_a, content_type=profile_ct, object_id=profile.pk
    )
    b_item = CustomContentPackItem.objects.get(
        pack=pack_b, content_type=profile_ct, object_id=profile.pk
    )
    assert a_item.archived
    assert not b_item.archived


# --- Default-assignment regression: pack profile on default-assignment -----


@pytest.mark.django_db
def test_pack_profile_on_default_assignment_shows_on_list_page(
    client, user, pack, library_weapon, content_house, make_content_fighter, make_list
):
    """Regression: a pack-scoped weapon profile attached to a
    ContentFighterDefaultAssignment via weapon_profiles_field must appear on
    the list page when the list subscribes to the pack.

    The ListFighter prefetch chain previously only prefetched the equipment's
    contentweaponprofile_set, not the default-assignment's own
    weapon_profiles_field — so pack-scoped profiles were silently dropped by
    the M2M target's default ContentManager.
    """
    client.force_login(user)

    # Pack defines a "Custom ammo" profile on the library weapon.
    custom_ammo = ContentWeaponProfile.objects.create(
        equipment=library_weapon, name="Custom ammo", cost=50
    )
    _add_to_pack(pack, custom_ammo)

    # Pack also defines a fighter with the library weapon as a default
    # assignment, with the pack-scoped Custom ammo selected on it.
    cf = make_content_fighter(
        type="Pack Test Fighter",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    _add_to_pack(pack, cf)
    da = ContentFighterDefaultAssignment.objects.create(
        fighter=cf, equipment=library_weapon
    )
    da.weapon_profiles_field.add(custom_ammo)

    # Subscribe a list to the pack and hire the fighter.
    lst = make_list("Sub List")
    lst.packs.add(pack)
    fighter = ListFighter.objects.create(
        name="Hired", list=lst, owner=user, content_fighter=cf
    )

    url = reverse("core:list", args=(lst.id,))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Custom ammo" in response.content
    # Smoke: the default-assignment equipment is still visible too.
    assert library_weapon.name.encode() in response.content
    # Avoid an unused-name warning while still touching the fighter.
    assert fighter is not None
