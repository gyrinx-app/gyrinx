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
