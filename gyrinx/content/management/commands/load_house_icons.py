"""Attach bundled SVG house icons to their matching ContentHouse records.

The SVGs live in ``gyrinx/content/data/house_icons/`` and are stored on
``ContentHouse.icon`` (a FileField). Each icon covers every book-variant of a
house — e.g. the ``cawdor`` icon is applied to both ``Cawdor (GotU)`` and
``Cawdor (HoF)``.

Run after deploy to populate icons in any environment::

    manage load_house_icons            # apply, skipping houses that already have an icon
    manage load_house_icons --overwrite  # replace existing icons too
    manage load_house_icons --dry-run    # report what would change, touch nothing
"""

from pathlib import Path

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from gyrinx.content.models import ContentHouse

ICONS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "house_icons"

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


class Command(BaseCommand):
    help = "Attach bundled SVG house icons to their matching ContentHouse records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace icons on houses that already have one.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        overwrite = options["overwrite"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - no changes will be made"))

        applied = skipped = missing = 0

        for icon_slug, house_names in ICON_HOUSE_MAP.items():
            svg_path = ICONS_DIR / f"{icon_slug}.svg"
            if not svg_path.exists():
                self.stderr.write(self.style.ERROR(f"Missing bundled SVG: {svg_path}"))
                continue
            svg_bytes = svg_path.read_bytes()

            for house_name in house_names:
                house = ContentHouse.objects.filter(name=house_name).first()
                if house is None:
                    self.stderr.write(
                        self.style.ERROR(f"  No house named {house_name!r}")
                    )
                    missing += 1
                    continue

                if house.icon and not overwrite:
                    self.stdout.write(f"  skip (has icon): {house_name}")
                    skipped += 1
                    continue

                self.stdout.write(
                    self.style.SUCCESS(f"  set {icon_slug} -> {house_name}")
                )
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

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. applied={applied} skipped={skipped} missing={missing}"
            )
        )
