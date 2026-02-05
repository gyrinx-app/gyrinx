import uuid

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentWeaponAccessory,
    ContentWeaponProfile,
)
from gyrinx.core.models import CustomContentPack, CustomContentPackItem
from gyrinx.models import FighterCategoryChoices


@pytest.fixture
def pack(user):
    return CustomContentPack.objects.create(
        name="Test Pack",
        summary="A test content pack",
        owner=user,
    )


@pytest.fixture
def base_fighter(house):
    """A fighter not in any pack (base game content)."""
    return ContentFighter.objects.all_content().create(
        type="Base Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )


@pytest.fixture
def pack_fighter(house, pack):
    """A fighter that belongs to a pack."""
    fighter = ContentFighter.objects.all_content().create(
        type="Pack Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    return fighter


# -- CustomContentPack tests --


@pytest.mark.django_db
def test_pack_create(user):
    pack = CustomContentPack.objects.create(
        name="My Pack",
        summary="Short summary",
        description="Longer description",
        listed=False,
        owner=user,
    )
    assert pack.name == "My Pack"
    assert pack.summary == "Short summary"
    assert pack.description == "Longer description"
    assert pack.listed is False
    assert pack.owner == user
    assert str(pack) == "My Pack"


@pytest.mark.django_db
def test_pack_ordering(user):
    CustomContentPack.objects.create(name="Zebra Pack", owner=user)
    CustomContentPack.objects.create(name="Alpha Pack", owner=user)
    packs = list(CustomContentPack.objects.values_list("name", flat=True))
    assert packs == ["Alpha Pack", "Zebra Pack"]


# -- CustomContentPackItem tests --


@pytest.mark.django_db
def test_pack_item_create(pack, house):
    fighter = ContentFighter.objects.all_content().create(
        type="Custom Fighter",
        category=FighterCategoryChoices.LEADER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    item = CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    assert item.content_object == fighter
    assert item.pack == pack


@pytest.mark.django_db
def test_pack_item_unique_constraint(pack, house):
    fighter = ContentFighter.objects.all_content().create(
        type="Unique Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    with pytest.raises(Exception):
        CustomContentPackItem.objects.create(
            pack=pack,
            content_type=ct,
            object_id=fighter.pk,
            owner=pack.owner,
        )


@pytest.mark.django_db
def test_pack_item_in_multiple_packs(user, house):
    pack1 = CustomContentPack.objects.create(name="Pack 1", owner=user)
    pack2 = CustomContentPack.objects.create(name="Pack 2", owner=user)
    fighter = ContentFighter.objects.all_content().create(
        type="Shared Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack1,
        content_type=ct,
        object_id=fighter.pk,
        owner=user,
    )
    CustomContentPackItem.objects.create(
        pack=pack2,
        content_type=ct,
        object_id=fighter.pk,
        owner=user,
    )
    assert pack1.items.count() == 1
    assert pack2.items.count() == 1


@pytest.mark.django_db
def test_pack_item_validates_object_exists(pack):
    """Creating a pack item with a non-existent object ID should fail validation."""
    ct = ContentType.objects.get_for_model(ContentFighter)
    item = CustomContentPackItem(
        pack=pack,
        content_type=ct,
        object_id=uuid.uuid4(),
        owner=pack.owner,
    )
    with pytest.raises(ValidationError, match="object_id"):
        item.full_clean()


@pytest.mark.django_db
def test_pack_item_validates_object_exists_for_valid_object(pack, house):
    """Creating a pack item with a valid object ID should pass validation."""
    fighter = ContentFighter.objects.all_content().create(
        type="Valid Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    item = CustomContentPackItem(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    item.full_clean()


@pytest.mark.django_db
def test_pack_item_cascade_on_pack_delete(pack, house):
    fighter = ContentFighter.objects.all_content().create(
        type="Cascade Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=fighter.pk,
        owner=pack.owner,
    )
    pack.delete()
    assert CustomContentPackItem.objects.count() == 0


# -- ContentManager pack filtering tests --


@pytest.mark.django_db
def test_content_manager_default_excludes_pack_content(base_fighter, pack_fighter):
    """Default objects.all() should not include pack fighters."""
    fighters = ContentFighter.objects.all()
    assert base_fighter in fighters
    assert pack_fighter not in fighters


@pytest.mark.django_db
def test_content_manager_all_content_includes_pack(base_fighter, pack_fighter):
    """all_content() should include both base and pack fighters."""
    fighters = ContentFighter.objects.all_content()
    assert base_fighter in fighters
    assert pack_fighter in fighters


@pytest.mark.django_db
def test_content_manager_with_packs_includes_specified(
    base_fighter, pack_fighter, pack
):
    """with_packs() should include base content and specified pack content."""
    fighters = ContentFighter.objects.with_packs([pack])
    assert base_fighter in fighters
    assert pack_fighter in fighters


@pytest.mark.django_db
def test_content_manager_with_packs_excludes_other(
    user, house, base_fighter, pack_fighter, pack
):
    """with_packs() should exclude content from non-specified packs."""
    other_pack = CustomContentPack.objects.create(name="Other Pack", owner=user)
    other_fighter = ContentFighter.objects.all_content().create(
        type="Other Pack Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    ct = ContentType.objects.get_for_model(ContentFighter)
    CustomContentPackItem.objects.create(
        pack=other_pack,
        content_type=ct,
        object_id=other_fighter.pk,
        owner=user,
    )

    fighters = ContentFighter.objects.with_packs([pack])
    assert base_fighter in fighters
    assert pack_fighter in fighters
    assert other_fighter not in fighters


@pytest.mark.django_db
def test_content_manager_filter_chaining(base_fighter, pack_fighter, house):
    """Ensure normal queryset filtering still works."""
    fighters = ContentFighter.objects.filter(house=house)
    assert base_fighter in fighters
    assert pack_fighter not in fighters


@pytest.mark.django_db
def test_content_manager_without_stash_excludes_pack(
    house, pack, base_fighter, pack_fighter
):
    """The without_stash() method should also exclude pack content."""
    fighters = ContentFighter.objects.without_stash()
    assert base_fighter in fighters
    assert pack_fighter not in fighters


# -- ContentManager equipment pack filtering tests --


@pytest.mark.django_db
def test_content_manager_equipment_default_excludes_pack(user):
    pack = CustomContentPack.objects.create(name="Equip Pack", owner=user)
    category = ContentEquipmentCategory.objects.create(
        name="Test Cat", group="Weapons & Ammo"
    )
    base_equip = ContentEquipment.objects.all_content().create(
        name="Base Gun", category=category, cost="10"
    )
    pack_equip = ContentEquipment.objects.all_content().create(
        name="Pack Gun", category=category, cost="20"
    )
    ct = ContentType.objects.get_for_model(ContentEquipment)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=pack_equip.pk,
        owner=user,
    )

    default_qs = ContentEquipment.objects.all()
    assert base_equip in default_qs
    assert pack_equip not in default_qs

    all_qs = ContentEquipment.objects.all_content()
    assert base_equip in all_qs
    assert pack_equip in all_qs

    pack_qs = ContentEquipment.objects.with_packs([pack])
    assert base_equip in pack_qs
    assert pack_equip in pack_qs


# -- ContentManager weapon profile pack filtering tests --


@pytest.mark.django_db
def test_content_manager_weapon_profile_default_excludes_pack(user):
    pack = CustomContentPack.objects.create(name="WP Pack", owner=user)
    category = ContentEquipmentCategory.objects.create(
        name="WP Cat", group="Weapons & Ammo"
    )
    equip = ContentEquipment.objects.all_content().create(
        name="WP Gun", category=category, cost="10"
    )
    base_profile = ContentWeaponProfile.objects.all_content().create(
        equipment=equip, name="", cost=0
    )
    pack_profile = ContentWeaponProfile.objects.all_content().create(
        equipment=equip, name="Pack Profile", cost=5
    )
    ct = ContentType.objects.get_for_model(ContentWeaponProfile)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=pack_profile.pk,
        owner=user,
    )

    default_qs = ContentWeaponProfile.objects.all()
    assert base_profile in default_qs
    assert pack_profile not in default_qs

    all_qs = ContentWeaponProfile.objects.all_content()
    assert base_profile in all_qs
    assert pack_profile in all_qs


# -- ContentManager weapon accessory pack filtering tests --


@pytest.mark.django_db
def test_content_manager_weapon_accessory_default_excludes_pack(user):
    pack = CustomContentPack.objects.create(name="WA Pack", owner=user)
    base_acc = ContentWeaponAccessory.objects.all_content().create(
        name="Base Scope", cost=10
    )
    pack_acc = ContentWeaponAccessory.objects.all_content().create(
        name="Pack Scope", cost=15
    )
    ct = ContentType.objects.get_for_model(ContentWeaponAccessory)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=pack_acc.pk,
        owner=user,
    )

    default_qs = ContentWeaponAccessory.objects.all()
    assert base_acc in default_qs
    assert pack_acc not in default_qs

    all_qs = ContentWeaponAccessory.objects.all_content()
    assert base_acc in all_qs
    assert pack_acc in all_qs


# -- ContentManager equipment upgrade pack filtering tests --


@pytest.mark.django_db
def test_content_manager_equipment_upgrade_default_excludes_pack(user):
    pack = CustomContentPack.objects.create(name="EU Pack", owner=user)
    category = ContentEquipmentCategory.objects.create(
        name="EU Cat", group="Weapons & Ammo"
    )
    equip = ContentEquipment.objects.all_content().create(
        name="EU Gun", category=category, cost="10"
    )
    base_upgrade = ContentEquipmentUpgrade.objects.all_content().create(
        equipment=equip, name="Base Upgrade", cost=5
    )
    pack_upgrade = ContentEquipmentUpgrade.objects.all_content().create(
        equipment=equip, name="Pack Upgrade", cost=10
    )
    ct = ContentType.objects.get_for_model(ContentEquipmentUpgrade)
    CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ct,
        object_id=pack_upgrade.pk,
        owner=user,
    )

    default_qs = ContentEquipmentUpgrade.objects.all()
    assert base_upgrade in default_qs
    assert pack_upgrade not in default_qs

    all_qs = ContentEquipmentUpgrade.objects.all_content()
    assert base_upgrade in all_qs
    assert pack_upgrade in all_qs


# -- ContentManager with no pack content --


@pytest.mark.django_db
def test_content_manager_no_pack_returns_all(house):
    fighter = ContentFighter.objects.all_content().create(
        type="Normal Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    assert fighter in ContentFighter.objects.all()
    assert fighter in ContentFighter.objects.all_content()


@pytest.mark.django_db
def test_content_manager_with_empty_packs_returns_base(house):
    fighter = ContentFighter.objects.all_content().create(
        type="Normal Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
    )
    assert fighter in ContentFighter.objects.with_packs([])
