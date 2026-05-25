"""Tests for the load_house_icons management command."""

import pytest
from django.core.management import call_command

from gyrinx.content.house_icons import ICON_HOUSE_MAP, ICONS_DIR
from gyrinx.content.models import ContentHouse


def test_every_mapped_icon_has_a_bundled_svg():
    for icon_slug in ICON_HOUSE_MAP:
        assert (ICONS_DIR / f"{icon_slug}.svg").exists(), icon_slug


@pytest.mark.django_db
def test_attaches_icons_to_matching_houses():
    cawdor_gotu = ContentHouse.objects.create(name="Cawdor (GotU)")
    cawdor_hof = ContentHouse.objects.create(name="Cawdor (HoF)")
    # A house with no icon mapping is left untouched.
    other = ContentHouse.objects.create(name="Abyssal Ferrymen")

    call_command("load_house_icons")

    for house in (cawdor_gotu, cawdor_hof):
        house.refresh_from_db()
        assert house.icon
        assert house.icon.name.startswith(f"house-icons/{_slug(house.name)}")
        assert b"<svg" in house.icon.read()

    other.refresh_from_db()
    assert not other.icon


@pytest.mark.django_db
def test_skips_houses_that_already_have_an_icon():
    house = ContentHouse.objects.create(name="Malstrain")
    call_command("load_house_icons")
    house.refresh_from_db()
    first_name = house.icon.name

    # Re-running without --overwrite must not touch the existing file.
    call_command("load_house_icons")
    house.refresh_from_db()
    assert house.icon.name == first_name


@pytest.mark.django_db
def test_overwrite_replaces_existing_icon():
    house = ContentHouse.objects.create(name="Malstrain")
    call_command("load_house_icons")
    house.refresh_from_db()
    assert house.icon

    call_command("load_house_icons", overwrite=True)
    house.refresh_from_db()
    assert house.icon


@pytest.mark.django_db
def test_dry_run_makes_no_changes():
    house = ContentHouse.objects.create(name="Slave Ogryns")
    call_command("load_house_icons", dry_run=True)
    house.refresh_from_db()
    assert not house.icon


def _slug(name):
    from django.utils.text import slugify

    return slugify(name)
