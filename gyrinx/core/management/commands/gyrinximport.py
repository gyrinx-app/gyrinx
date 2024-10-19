import hashlib
import uuid
from collections import defaultdict
from pathlib import Path

import click
from django.core.management.base import BaseCommand

from gyrinx.core.models import (
    Category,
    Equipment,
    EquipmentCategory,
    Fighter,
    FighterEquipment,
    House,
    Skill,
)
from scripts.schema import gather_data


def flatten(xss):
    return [x for xs in xss for x in xs]


def data_for_type(name, data_sources):
    return flatten([src.data for src in data_sources if src.name == name])


def stable_uuid(v):
    return uuid.UUID(hashlib.md5(v.encode()).hexdigest()[:32])


def lookup(index, type, id):
    try:
        return index[type][stable_uuid(id)]
    except KeyError:
        return None


class Command(BaseCommand):
    help = "Import Gyrinx content library"

    def add_arguments(self, parser):
        parser.add_argument("directory", type=Path)
        parser.add_argument("--content-version", type=str, required=False)
        parser.add_argument("--dry-run", action="store_true")
        # TODO: In future...
        # --tag --dry-run

    def handle(self, *args, **options):
        # TODO: Reuse the schema.py functions to validate the schema?
        content_version = (
            uuid.UUID(options["content_version"])
            if options["content_version"]
            else uuid.uuid4()
        )
        dry_run = bool(options["dry_run"])

        click.echo("Importing content with version {content_version}")
        if dry_run:
            click.echo(f"Dry run: {dry_run}")

        if not options["directory"].exists():
            raise ConnectionError(f"Error: No such directory {options['directory']}")

        content_dir = options["directory"]
        rulesets = [d for d in content_dir.iterdir() if d.is_dir()]

        if not rulesets:
            raise ConnectionError(f"Error: No rulesets found in {content_dir}")

        click.echo(f"Found {len(rulesets)} rulesets in {content_dir}")

        # TODO: Which ruleset do we import? Do we need custom import rules for each ruleset?
        ruleset_dir = rulesets[0]

        schema_dir = ruleset_dir / "schema"
        data_dir = ruleset_dir / "data"

        if not schema_dir.exists():
            raise ConnectionError(f"Error: No schema folder in {content_dir}")
        if not data_dir.exists():
            raise ConnectionError(f"Error: No data folder in {content_dir}")

        click.echo(f"Using {ruleset_dir} for import")

        # Execution order:
        # - House
        # - Category
        # - Skill
        # - Weapon Stats [not implemented]
        # - Equipment
        # - Fighter
        # - Fighter Equipment

        data_sources = gather_data(ruleset_dir)
        click.echo(f"Found {len(data_sources)} data sources in {data_dir}")
        for src in data_sources:
            click.echo(f" - {src.name} from {src.path}")

        index = defaultdict(dict)

        houses = data_for_type("house", data_sources)
        click.echo(f"Found {len(houses)} houses: ")
        for house in houses:
            house = House(
                version=content_version,
                uuid=stable_uuid(house["name"]),
                name=house["name"],
            )
            index["house"][house.uuid] = house
            click.echo(f" - {house.name} ({house.uuid}, {house.version})")
            if not dry_run:
                house.save()

        categories = data_for_type("category", data_sources)
        click.echo(f"Found {len(categories)} categories: ")
        for category in categories:
            cat = Category(
                version=content_version,
                uuid=stable_uuid(category["name"]),
                name=category["name"],
            )
            index["category"][cat.uuid] = cat
            click.echo(f" - {cat.name} ({cat.uuid}, {cat.version})")
            if not dry_run:
                cat.save()

        skills = data_for_type("skill", data_sources)
        click.echo(f"Found {len(skills)} skills: ")
        for skill in skills:
            sk = Skill(
                version=content_version,
                uuid=stable_uuid(skill["name"]),
                name=skill["name"],
            )
            index["skill"][sk.uuid] = sk
            click.echo(f" - {sk.name} ({sk.uuid}, {sk.version})")
            if not dry_run:
                sk.save()

        eq_cats = data_for_type("equipment_category", data_sources)
        click.echo(f"Found {len(eq_cats)} equipment categories: ")
        for eq_cat in eq_cats:
            eq_cat = EquipmentCategory(
                version=content_version,
                uuid=stable_uuid(eq_cat["name"]),
                name=eq_cat["name"],
            )
            index["equipment_category"][eq_cat.uuid] = eq_cat
            click.echo(f" - {eq_cat.name} ({eq_cat.uuid}, {eq_cat.version})")
            if not dry_run:
                eq_cat.save()

        equipment = data_for_type("equipment", data_sources)
        click.echo(f"Found {len(equipment)} equipment: ")
        for e in equipment:
            category = lookup(index, "equipment_category", e["category"])
            if not category:
                click.echo(f"Error: Could not find category matching {e['category']}")
                continue
            item = Equipment(
                version=content_version,
                uuid=stable_uuid(e["name"]),
                name=e["name"],
                category=category,
            )
            index["equipment"][item.uuid] = item
            click.echo(f" - {item.category}: {item.name} ({item.uuid}, {item.version})")
            if not dry_run:
                item.save()

        fighters = data_for_type("fighter", data_sources)
        click.echo(f"Found {len(fighters)} fighters: ")
        for f in fighters:
            category = lookup(index, "category", f["category"])
            house = lookup(index, "house", f["house"]) if f.get("house", None) else None
            if not category:
                click.echo(f"Error: Could not find category matching {f['category']}")
                continue
            if f.get("house") and not house:
                click.echo(f"Error: Could not find house matching {f['house']}")
                continue
            fighter = Fighter(
                version=content_version,
                uuid=stable_uuid(f["type"]),
                type=f["type"],
                category=category,
                house=house,
            )
            index["fighter"][fighter.uuid] = fighter
            click.echo(
                f" - {fighter.house or "N/A"}: {fighter.type} ({fighter.category.name}) ({fighter.uuid}, {fighter.version})"
            )
            if not dry_run:
                fighter.save()

        equipment_list = data_for_type("equipment_list", data_sources)
        click.echo(f"Found {len(equipment_list)} equipment lists: ")
        for el in equipment_list:
            fighter = lookup(index, "fighter", el["fighter_type"])
            if not fighter:
                click.echo(
                    f"Error: Could not find fighter matching {el['fighter_type']}",
                    err=True,
                )
                continue

            equipment = [
                (item["name"], lookup(index, "equipment", item["name"]))
                for item in el["equipment"]
            ]
            for entry in equipment:
                name, item = entry
                if not item:
                    click.echo(
                        f"Error: Could not find equipment matching {name}", err=True
                    )
                    continue

                fighter_equip = FighterEquipment(
                    version=content_version,
                    uuid=stable_uuid(f"{fighter.uuid}:{item.uuid}"),
                    fighter=fighter,
                    equipment=item,
                )
                click.echo(
                    f" - {fighter_equip.fighter.type}: {fighter_equip.equipment.name} ({fighter_equip.uuid}, {fighter_equip.version})"
                )
                if not dry_run:
                    fighter_equip.save()
