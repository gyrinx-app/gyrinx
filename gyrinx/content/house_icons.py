"""Shared data + logic for attaching the bundled SVG house icons.

The SVGs live in ``gyrinx/content/data/house_icons/`` and are stored on
``ContentHouse.icon`` (a FileField). Each icon covers every book-variant of a
house — e.g. the ``cawdor`` icon is applied to both ``Cawdor (GotU)`` and
``Cawdor (HoF)``.

This module is deliberately free of any real-model import so it can be used
from both the ``load_house_icons`` management command and a data migration
(which must pass the historical model from ``apps.get_model``).
"""

from pathlib import Path

from django.core.files.base import ContentFile
from django.utils.text import slugify

ICONS_DIR = Path(__file__).resolve().parent / "data" / "house_icons"

# The generic icon shared by every "custom gang" — i.e. any ContentHouse that
# belongs to a content pack. Pack houses have no bundled per-house artwork, so
# they all use this one. Deliberately absent from ``ICON_HOUSE_MAP`` (which is
# keyed by exact house name); custom gangs are matched by pack membership
# instead — see ``attach_custom_gang_icon``.
CUSTOM_GANG_ICON_SLUG = "custom_gang"

# Maps each bundled SVG (without extension) to the exact ContentHouse.name
# records it should be applied to. House names taken from production.
ICON_HOUSE_MAP = {
    "ash_wastes_nomads": ["Ash Wastes Nomads (BotO)", "Ash Wastes Nomads (TotW)"],
    "badzone_enforcers": ["Badzone Enforcers (BoL)", "Badzone Enforcers (WD)"],
    "cawdor": ["Cawdor (GotU)", "Cawdor (HoF)"],
    "corpse_grinder_cult": ["Corpse Grinder Cult"],
    "delaque": ["Delaque (GotU)", "Delaque (HoS)"],
    "enforcers": ["Palanite Enforcers (BoJ)", "Palanite Enforcers (BoL)"],
    "escher": ["Escher (GotU)", "Escher (HoB)"],
    "genestealer_cult": ["Genestealer Cult"],
    "goliath": ["Goliath (GotU)", "Goliath (HoC)"],
    "helot_chaos_cult": ["Helot Chaos Cult"],
    "ironhead_squats": ["Ironhead Squats (HotA)", "Ironhead Squat Prospectors (BotO)"],
    "malstrain": ["Malstrain"],
    "orlock": ["Orlock (GotU)", "Orlock (HoI)"],
    "slave_ogryns": ["Slave Ogryns"],
    "spyre_hunting_party": ["Spyre Hunting Party"],
    "underhive_outcasts": ["Underhive Outcasts"],
    "van_saar": ["Van Saar (GotU)", "Van Saar (HoA)"],
    "venators": ["Venators (AN)", "Venators (BoP)"],
}


def attach_house_icons(house_model, *, overwrite=False, dry_run=False, log=None):
    """Attach each bundled SVG to its matching ``house_model`` record(s).

    ``house_model`` is passed in so callers can supply either the concrete
    ``ContentHouse`` (command) or the migration-state model from
    ``apps.get_model`` (data migration). Houses absent from the target
    environment are skipped, as are houses that already have an icon unless
    ``overwrite`` is set. ``log`` is an optional ``callable(str)`` for progress
    output. Returns ``(applied, skipped, missing)`` counts.
    """
    emit = log or (lambda _msg: None)
    applied = skipped = missing = 0

    for icon_slug, house_names in ICON_HOUSE_MAP.items():
        svg_path = ICONS_DIR / f"{icon_slug}.svg"
        if not svg_path.exists():
            emit(f"Missing bundled SVG: {svg_path}")
            continue
        svg_bytes = svg_path.read_bytes()

        for house_name in house_names:
            house = house_model.objects.filter(name=house_name).first()
            if house is None:
                emit(f"  no house named {house_name!r}")
                missing += 1
                continue

            if house.icon and not overwrite:
                emit(f"  skip (has icon): {house_name}")
                skipped += 1
                continue

            emit(f"  set {icon_slug} -> {house_name}")
            applied += 1

            if dry_run:
                continue

            if house.icon:
                house.icon.delete(save=False)
            house.icon.save(
                f"{slugify(house_name)}.svg",
                ContentFile(svg_bytes),
                save=True,
            )

    return applied, skipped, missing


def read_icon_bytes(icon_slug):
    """Return the bytes of a bundled icon SVG, or ``None`` if it's missing."""
    svg_path = ICONS_DIR / f"{icon_slug}.svg"
    if not svg_path.exists():
        return None
    return svg_path.read_bytes()


def set_house_icon(house, icon_slug, *, overwrite=False, save=True):
    """Store the bundled ``icon_slug`` SVG on ``house.icon``.

    Skips houses that already have an icon unless ``overwrite`` is set. Returns
    ``True`` if an icon was written, ``False`` otherwise (the house already had
    one, or the bundled SVG is missing).
    """
    if house.icon and not overwrite:
        return False
    svg_bytes = read_icon_bytes(icon_slug)
    if svg_bytes is None:
        return False
    if house.icon:
        house.icon.delete(save=False)
    house.icon.save(f"{slugify(house.name)}.svg", ContentFile(svg_bytes), save=save)
    return True


def attach_custom_gang_icon(
    house_model, pack_item_model, *, overwrite=False, dry_run=False, log=None
):
    """Attach the generic custom-gang icon to every content-pack house.

    A "custom gang" is any ``ContentHouse`` that belongs to a content pack
    (i.e. is referenced by a ``CustomContentPackItem``). Such houses have no
    bundled per-house artwork, so they all share the single ``custom_gang``
    icon. Archived pack items still count — archiving is a pack-owner
    soft-delete and doesn't change what the house is.

    ``house_model`` / ``pack_item_model`` are passed in so this works from both
    the management command (concrete models) and a data migration (historical
    models from ``apps.get_model``). Houses that already have an icon are
    skipped unless ``overwrite`` is set. ``log`` is an optional ``callable(str)``
    for progress output. Returns ``(applied, skipped)`` counts.
    """
    emit = log or (lambda _msg: None)
    svg_bytes = read_icon_bytes(CUSTOM_GANG_ICON_SLUG)
    if svg_bytes is None:
        emit(f"Missing bundled SVG: {CUSTOM_GANG_ICON_SLUG}.svg")
        return 0, 0

    # ``ContentHouse.objects`` excludes pack content by default — the exact
    # houses we're after — so reach past it via ``all_content()``. The
    # historical model passed from a data migration has a plain manager (which
    # already returns everything and lacks ``all_content``), hence the guard.
    house_manager = house_model.objects
    all_houses = (
        house_manager.all_content()
        if hasattr(house_manager, "all_content")
        else house_manager.all()
    )

    # All content models use globally-unique UUID PKs, so matching pack items
    # by ``object_id`` alone reliably picks out houses — no ContentType lookup
    # needed, which keeps this safe to run from a migration on a fresh DB.
    house_ids = list(all_houses.values_list("pk", flat=True))
    pack_house_ids = set(
        pack_item_model.objects.filter(object_id__in=house_ids).values_list(
            "object_id", flat=True
        )
    )

    applied = skipped = 0
    for house in all_houses.filter(pk__in=pack_house_ids):
        if house.icon and not overwrite:
            emit(f"  skip (has icon): {house.name}")
            skipped += 1
            continue

        emit(f"  set custom_gang -> {house.name}")
        applied += 1
        if dry_run:
            continue

        if house.icon:
            house.icon.delete(save=False)
        house.icon.save(
            f"{slugify(house.name)}.svg",
            ContentFile(svg_bytes),
            save=True,
        )

    return applied, skipped
