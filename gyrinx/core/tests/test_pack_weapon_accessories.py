"""Tests for weapon accessories in content packs."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentWeaponAccessory,
)
from gyrinx.content.models.modifier import ContentModStat, ContentModTrait
from gyrinx.content.models.weapon import ContentWeaponProfile, ContentWeaponTrait
from gyrinx.core.models.list import ListFighterEquipmentAssignment
from gyrinx.core.models.pack import CustomContentPackItem


def _add_to_pack(pack, obj):
    """Helper to associate a content object with a pack."""
    ct = ContentType.objects.get_for_model(type(obj))
    CustomContentPackItem.objects.create(
        pack=pack, content_type=ct, object_id=obj.pk, owner=pack.owner
    )


@pytest.fixture
def pack_accessory(pack):
    """A weapon accessory belonging to a pack."""
    accessory = ContentWeaponAccessory.objects.create(
        name="Pack Sight", cost=15, rarity="C"
    )
    _add_to_pack(pack, accessory)
    return accessory


# --- Equipping flow regression -------------------------------------------------


@pytest.mark.django_db
def test_pack_accessory_visible_in_equip_picker_when_subscribed(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """A pack-scoped accessory appears in the accessory picker for a list
    that has subscribed to the pack."""
    client.force_login(user)

    lst = make_list("Equip Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Pack Fighter")

    weapon_category = ContentEquipmentCategory.objects.create(
        name="Test Pistols", group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(
        name="Test Pistol", category=weapon_category, cost=10
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )

    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=(lst.id, fighter.id, assignment.id),
    )
    response = client.get(url + "?filter=all")
    assert response.status_code == 200
    assert b"Pack Sight" in response.content


@pytest.mark.django_db
def test_pack_accessory_hidden_in_equip_picker_when_not_subscribed(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """A pack-scoped accessory does NOT appear if the list isn't subscribed."""
    client.force_login(user)

    lst = make_list("No Sub Test")
    fighter = make_list_fighter(lst, "Solo Fighter")

    weapon_category = ContentEquipmentCategory.objects.create(
        name="Test Pistols 2", group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(
        name="Test Pistol 2", category=weapon_category, cost=10
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )

    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=(lst.id, fighter.id, assignment.id),
    )
    response = client.get(url + "?filter=all")
    assert response.status_code == 200
    assert b"Pack Sight" not in response.content


@pytest.mark.django_db
def test_pack_accessory_can_be_purchased_when_subscribed(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """Submitting the pack accessory ID adds it to the assignment."""
    client.force_login(user)

    lst = make_list("Purchase Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Buyer")

    weapon_category = ContentEquipmentCategory.objects.create(
        name="Test Pistols 3", group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(
        name="Test Pistol 3", category=weapon_category, cost=10
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )

    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=(lst.id, fighter.id, assignment.id),
    )
    response = client.post(url, {"accessory_id": str(pack_accessory.id)})
    assert response.status_code == 302
    # The default M2M manager excludes pack content, so query via all_content()
    # to confirm the relationship was created.
    attached = ContentWeaponAccessory.objects.all_content().filter(
        weapon_accessories=assignment, pk=pack_accessory.pk
    )
    assert attached.exists()


@pytest.mark.django_db
def test_pack_accessory_not_duplicated_in_available_when_attached(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """Once attached, a pack accessory must not appear in 'available'."""
    client.force_login(user)

    lst = make_list("Dedup Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Repeat Buyer")

    weapon_category = ContentEquipmentCategory.objects.create(
        name="Test Pistols 4", group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(
        name="Test Pistol 4", category=weapon_category, cost=10
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(pack_accessory)

    url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=(lst.id, fighter.id, assignment.id),
    )
    response = client.get(url + "?filter=all")
    content = response.content.decode()
    available_section = content[content.find("Available Accessories") :]
    assert "Pack Sight" not in available_section


@pytest.mark.django_db
def test_pack_accessory_clones_with_assignment(
    user, make_list, make_list_fighter, pack, pack_accessory
):
    """Cloning an assignment must copy pack-scoped accessories too. Without a
    pack-aware clone, the default M2M manager would silently drop them."""
    lst = make_list("Clone Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Cloner")

    weapon_category = ContentEquipmentCategory.objects.create(
        name="Test Pistols 5", group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(
        name="Test Pistol 5", category=weapon_category, cost=10
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(pack_accessory)

    cloned = assignment.clone(list_fighter=fighter)
    cloned_accessories = ContentWeaponAccessory.objects.all_content().filter(
        weapon_accessories=cloned
    )
    assert pack_accessory in cloned_accessories


@pytest.mark.django_db
def test_pack_accessory_visible_in_sell_view(
    client, user, make_list, make_list_fighter, content_house, pack, pack_accessory
):
    """A pack accessory attached to an assignment is shown in the sell view's
    'items to sell' list (not silently dropped by the default M2M manager)."""
    from gyrinx.content.models.fighter import ContentFighter
    from gyrinx.core.models.campaign import Campaign
    from gyrinx.core.models.list import List as ListModel
    from gyrinx.core.models.list import ListFighter

    client.force_login(user)
    campaign = Campaign.objects.create(name="Sell Pack Campaign", owner=user)
    lst = make_list("Sell Pack List", campaign=campaign, status=ListModel.CAMPAIGN_MODE)
    lst.packs.add(pack)

    stash_content = ContentFighter.objects.create(
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
        house=content_house,
    )
    stash = ListFighter.objects.create(
        name="Stash", content_fighter=stash_content, list=lst, owner=user
    )

    weapon_category = ContentEquipmentCategory.objects.create(
        name="Test Pistols 6", group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(
        name="Test Pistol 6", category=weapon_category, cost=10
    )
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(pack_accessory)

    url = reverse(
        "core:list-fighter-equipment-sell",
        args=(lst.id, stash.id, assignment.id),
    )
    response = client.get(url + f"?sell_assign={assignment.id}")
    assert response.status_code == 200
    assert b"Pack Sight" in response.content


def _make_weapon_with_profile(name, category_name):
    """Create a weapon with a default profile so is_weapon() is true."""
    category = ContentEquipmentCategory.objects.create(
        name=category_name, group="Weapons & Ammo"
    )
    weapon = ContentEquipment.objects.create(name=name, category=category, cost=10)
    ContentWeaponProfile.objects.create(equipment=weapon, name="", cost=0)
    return weapon


@pytest.mark.django_db
def test_pack_accessory_visible_on_list_detail_view(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """A pack accessory attached to a fighter's weapon must appear on the
    main list detail page. The default M2M manager hides it without a
    pack-aware prefetch."""
    client.force_login(user)
    lst = make_list("Display Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Owner")
    weapon = _make_weapon_with_profile("Test Pistol 7", "Test Pistols 7")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(pack_accessory)

    response = client.get(reverse("core:list", args=(lst.id,)))
    assert response.status_code == 200
    assert b"Pack Sight" in response.content


@pytest.mark.django_db
def test_pack_accessory_shows_pack_dot_indicator(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """The pack-content dot icon appears next to a pack accessory on the
    list detail page so users can tell it came from a pack."""
    client.force_login(user)
    lst = make_list("Dot Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Dotter")
    weapon = _make_weapon_with_profile("Test Pistol Dot", "Test Pistols Dot")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(pack_accessory)

    response = client.get(reverse("core:list", args=(lst.id,)))
    content = response.content.decode()
    # Find the accessory name and assert the pack-icon dot is nearby
    idx = content.find("Pack Sight")
    assert idx >= 0
    snippet = content[idx : idx + 400]
    assert "pack-icon" in snippet
    assert "Added by Test Pack" in snippet


@pytest.mark.django_db
def test_pack_accessory_visible_on_weapon_edit_page(
    client, user, make_list, make_list_fighter, pack, pack_accessory
):
    """A pack accessory shows in the fighter's weapon-edit page (via the
    fighter's prefetched assignments)."""
    client.force_login(user)
    lst = make_list("Weapon Edit Test")
    lst.packs.add(pack)
    fighter = make_list_fighter(lst, "Editor")
    weapon = _make_weapon_with_profile("Test Pistol 8", "Test Pistols 8")
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=weapon
    )
    assignment.weapon_accessories_field.add(pack_accessory)

    url = reverse("core:list-fighter-weapons-edit", args=(lst.id, fighter.id))
    response = client.get(url)
    assert response.status_code == 200
    assert b"Pack Sight" in response.content


# --- Pack form CRUD ------------------------------------------------------------


@pytest.mark.django_db
def test_add_accessory_form_loads(client, user, pack):
    client.force_login(user)
    response = client.get(f"/pack/{pack.id}/add/weapon-accessory/")
    assert response.status_code == 200
    assert b"Add Weapon Accessory" in response.content


@pytest.mark.django_db
def test_add_accessory_creates_item(client, user, pack):
    client.force_login(user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {
            "name": "Telescopic Sight",
            "description": "Improves long-range accuracy.",
            "cost": "20",
            "rarity": "C",
            "rarity_roll": "",
        },
    )
    assert response.status_code == 302

    accessory = ContentWeaponAccessory.objects.all_content().get(
        name="Telescopic Sight"
    )
    assert accessory.cost == 20
    assert accessory.description == "Improves long-range accuracy."
    assert CustomContentPackItem.objects.filter(
        pack=pack, object_id=accessory.pk
    ).exists()


@pytest.mark.django_db
def test_add_accessory_with_stat_mod(client, user, pack):
    """Submitting a stat mod via the picker creates a ContentModStat row and
    attaches it to the accessory."""
    client.force_login(user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {
            "name": "Damage Booster",
            "description": "",
            "cost": "10",
            "rarity": "C",
            "rarity_roll": "",
            "stat_mod_damage_mode": "improve",
            "stat_mod_damage_value": "1",
        },
    )
    assert response.status_code == 302

    accessory = ContentWeaponAccessory.objects.all_content().get(name="Damage Booster")
    mod = ContentModStat.objects.get(stat="damage", mode="improve", value="1")
    assert mod in accessory.modifiers.all()


@pytest.mark.django_db
def test_add_accessory_with_trait_mod(client, user, pack):
    """Submitting a trait mod via the picker finds-or-creates a ContentModTrait
    and attaches it."""
    base_trait = ContentWeaponTrait.objects.create(name="Knockback")

    client.force_login(user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {
            "name": "Heavy Stock",
            "description": "",
            "cost": "5",
            "rarity": "C",
            "rarity_roll": "",
            f"trait_mod_{base_trait.pk}": "add",
        },
    )
    assert response.status_code == 302

    accessory = ContentWeaponAccessory.objects.all_content().get(name="Heavy Stock")
    mod = ContentModTrait.objects.get(trait=base_trait, mode="add")
    assert mod in accessory.modifiers.all()


@pytest.mark.django_db
def test_mod_dedup_across_accessories(client, user, pack):
    """Two accessories with the same stat mod share a single ContentModStat row."""
    client.force_login(user)

    for name in ("Sight A", "Sight B"):
        response = client.post(
            f"/pack/{pack.id}/add/weapon-accessory/",
            {
                "name": name,
                "description": "",
                "cost": "5",
                "rarity": "C",
                "rarity_roll": "",
                "stat_mod_strength_mode": "improve",
                "stat_mod_strength_value": "1",
            },
        )
        assert response.status_code == 302

    rows = ContentModStat.objects.filter(stat="strength", mode="improve", value="1")
    assert rows.count() == 1


@pytest.mark.django_db
def test_edit_view_opens_trait_collapsible_when_trait_mod_set(client, user, pack):
    """When editing an accessory that has a trait mod, the weapon-trait
    collapsible should be rendered with the ``open`` attribute."""
    base_trait = ContentWeaponTrait.objects.create(name="Knockback")
    client.force_login(user)
    client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {
            "name": "Trait Setter",
            "description": "",
            "cost": "5",
            "rarity": "C",
            "rarity_roll": "",
            f"trait_mod_{base_trait.pk}": "add",
        },
    )
    accessory = ContentWeaponAccessory.objects.all_content().get(name="Trait Setter")
    pack_item = CustomContentPackItem.objects.get(
        pack=pack, object_id=accessory.pk, archived=False
    )
    edit_url = reverse("core:pack-edit-item", args=(pack.id, pack_item.id))
    response = client.get(edit_url)
    content = response.content.decode()
    # Locate the "Weapon trait modifiers" details element and verify it has
    # the open attribute.
    trait_section_idx = content.find("Weapon trait modifiers")
    details_open_idx = content.rfind("<details", 0, trait_section_idx)
    details_tag = content[details_open_idx:trait_section_idx]
    assert "open" in details_tag


@pytest.mark.django_db
def test_add_view_trait_collapsible_closed_by_default(client, user, pack):
    """On the empty add form, the trait collapsible defaults to closed."""
    ContentWeaponTrait.objects.create(name="Some Trait")
    client.force_login(user)
    response = client.get(f"/pack/{pack.id}/add/weapon-accessory/")
    content = response.content.decode()
    trait_section_idx = content.find("Weapon trait modifiers")
    details_open_idx = content.rfind("<details", 0, trait_section_idx)
    details_tag = content[details_open_idx:trait_section_idx]
    assert "open" not in details_tag


@pytest.mark.django_db
def test_edit_accessory_preserves_mods_and_can_remove(client, user, pack):
    """Editing an accessory with a stat mod set to 'none' removes the mod from M2M."""
    client.force_login(user)

    # Create the accessory with a stat mod.
    client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {
            "name": "Editable Accessory",
            "description": "",
            "cost": "5",
            "rarity": "C",
            "rarity_roll": "",
            "stat_mod_ammo_mode": "set",
            "stat_mod_ammo_value": "5+",
        },
    )
    accessory = ContentWeaponAccessory.objects.all_content().get(
        name="Editable Accessory"
    )
    pack_item = CustomContentPackItem.objects.get(
        pack=pack, object_id=accessory.pk, archived=False
    )
    mod = ContentModStat.objects.get(stat="ammo", mode="set", value="5+")
    assert mod in accessory.modifiers.all()

    # Reload the edit page — radios should be pre-populated.
    edit_url = reverse("core:pack-edit-item", args=(pack.id, pack_item.id))
    response = client.get(edit_url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "stat_mod_ammo_mode" in content
    assert "5+" in content

    # Submit with the ammo mode cleared.
    response = client.post(
        edit_url,
        {
            "name": "Editable Accessory",
            "description": "",
            "cost": "5",
            "rarity": "C",
            "rarity_roll": "",
            "stat_mod_ammo_mode": "",
            "stat_mod_ammo_value": "",
        },
    )
    assert response.status_code == 302

    accessory.refresh_from_db()
    assert mod not in accessory.modifiers.all()


# --- Uniqueness ---------------------------------------------------------------


@pytest.mark.django_db
def test_add_accessory_rejects_duplicate_base_name(client, user, pack):
    ContentWeaponAccessory.objects.create(name="Sight")
    client.force_login(user)
    response = client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {"name": "Sight", "description": "", "cost": "0", "rarity": "C"},
    )
    assert response.status_code == 200
    assert b"already exists in the content library" in response.content


@pytest.mark.django_db
def test_add_accessory_rejects_duplicate_within_pack(client, user, pack):
    client.force_login(user)
    client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {"name": "PackSight", "description": "", "cost": "0", "rarity": "C"},
    )
    response = client.post(
        f"/pack/{pack.id}/add/weapon-accessory/",
        {"name": "PackSight", "description": "", "cost": "0", "rarity": "C"},
    )
    assert response.status_code == 200
    assert b"already exists in this Content Pack" in response.content


@pytest.mark.django_db
def test_different_packs_can_have_same_accessory_name(client, user, make_pack):
    pack1 = make_pack("Pack One")
    pack2 = make_pack("Pack Two")
    client.force_login(user)

    response = client.post(
        f"/pack/{pack1.id}/add/weapon-accessory/",
        {"name": "Shared Sight", "description": "", "cost": "0", "rarity": "C"},
    )
    assert response.status_code == 302

    response = client.post(
        f"/pack/{pack2.id}/add/weapon-accessory/",
        {"name": "Shared Sight", "description": "", "cost": "0", "rarity": "C"},
    )
    assert response.status_code == 302

    assert (
        ContentWeaponAccessory.objects.all_content().filter(name="Shared Sight").count()
        == 2
    )


@pytest.mark.django_db
def test_base_accessory_model_level_uniqueness():
    """Base weapon accessories enforce name uniqueness via validate_unique."""
    ContentWeaponAccessory.objects.create(name="Iron Sight")
    duplicate = ContentWeaponAccessory(name="Iron Sight")
    with pytest.raises(ValidationError) as exc_info:
        duplicate.validate_unique()
    assert "name" in exc_info.value.message_dict


# --- Pack detail rendering ----------------------------------------------------


@pytest.mark.django_db
def test_pack_detail_shows_weapon_accessories_section(
    client, user, pack, pack_accessory
):
    client.force_login(user)
    response = client.get(reverse("core:pack", args=[pack.id]))
    content = response.content.decode()
    assert response.status_code == 200
    assert "Weapon Accessories" in content
    assert "Pack Sight" in content
