"""Tests for the generic custom-gang icon given to content-pack houses."""

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile

from gyrinx.content.house_icons import (
    CUSTOM_GANG_ICON_SLUG,
    ICONS_DIR,
    attach_custom_gang_icon,
    read_icon_bytes,
)
from gyrinx.content.models import ContentHouse
from gyrinx.core.models.pack import CustomContentPackItem


def test_custom_gang_svg_is_bundled():
    assert (ICONS_DIR / f"{CUSTOM_GANG_ICON_SLUG}.svg").exists()
    assert b"<svg" in read_icon_bytes(CUSTOM_GANG_ICON_SLUG)


def _add_house_to_pack(house, pack):
    return CustomContentPackItem.objects.create(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentHouse),
        object_id=house.pk,
        owner=pack.owner,
    )


@pytest.mark.django_db
def test_pack_house_gets_custom_gang_icon_on_creation(pack):
    """Adding a house to a pack stores the custom-gang icon via the signal."""
    house = ContentHouse.objects.create(name="My Custom Gang")
    assert not house.icon

    _add_house_to_pack(house, pack)

    house.refresh_from_db()
    assert house.icon
    assert b"<svg" in house.icon.read()


@pytest.mark.django_db
def test_signal_does_not_overwrite_an_existing_icon(pack):
    """A house that already has its own icon keeps it when added to a pack."""
    house = ContentHouse.objects.create(name="Already Iconned")
    house.icon.save("custom.svg", ContentFile(b"<svg>mine</svg>"), save=True)
    original_name = house.icon.name

    _add_house_to_pack(house, pack)

    house.refresh_from_db()
    assert house.icon.name == original_name
    assert house.icon.read() == b"<svg>mine</svg>"


@pytest.mark.django_db
def test_non_house_pack_item_leaves_house_untouched(pack, pack_fighter, content_house):
    """The signal only fires for ContentHouse pack items, not (e.g.) fighters."""
    content_house.refresh_from_db()
    assert not content_house.icon


@pytest.mark.django_db
def test_attach_custom_gang_icon_backfills_pack_houses(pack):
    """The backfill helper (used by the migration/command) sets icon-less
    pack houses and skips houses with an icon of their own."""
    pack_house = ContentHouse.objects.create(name="Pack House")
    _add_house_to_pack(pack_house, pack)
    # Clear the icon the signal set so the backfill has something to do. The
    # signal wrote it on its own instance, so refresh before deleting.
    pack_house.refresh_from_db()
    pack_house.icon.delete(save=True)

    own_icon_house = ContentHouse.objects.create(name="Own Icon House")
    own_icon_house.icon.save("mine.svg", ContentFile(b"<svg>mine</svg>"), save=True)
    _add_house_to_pack(own_icon_house, pack)

    non_pack_house = ContentHouse.objects.create(name="Not In A Pack")

    applied, skipped = attach_custom_gang_icon(ContentHouse, CustomContentPackItem)

    assert applied == 1
    assert skipped == 1

    pack_house.refresh_from_db()
    assert b"<svg" in pack_house.icon.read()

    own_icon_house.refresh_from_db()
    assert own_icon_house.icon.read() == b"<svg>mine</svg>"

    non_pack_house.refresh_from_db()
    assert not non_pack_house.icon


@pytest.mark.django_db
def test_attach_custom_gang_icon_dry_run_makes_no_changes(pack):
    house = ContentHouse.objects.create(name="Dry Run Gang")
    _add_house_to_pack(house, pack)
    house.refresh_from_db()
    house.icon.delete(save=True)

    applied, skipped = attach_custom_gang_icon(
        ContentHouse, CustomContentPackItem, dry_run=True
    )

    assert applied == 1
    house.refresh_from_db()
    assert not house.icon


@pytest.mark.django_db
def test_archived_pack_item_still_counts_as_custom_gang(pack):
    """Archiving a pack item is a pack-owner soft-delete; the house is still a
    custom gang, so the backfill still covers it."""
    house = ContentHouse.objects.create(name="Archived Pack Gang")
    item = _add_house_to_pack(house, pack)
    house.refresh_from_db()
    house.icon.delete(save=True)
    item.archived = True
    item.save()

    applied, _ = attach_custom_gang_icon(ContentHouse, CustomContentPackItem)

    assert applied == 1
    house.refresh_from_db()
    assert house.icon
