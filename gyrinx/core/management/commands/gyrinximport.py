import hashlib
import json
import uuid
from collections import defaultdict
from pathlib import Path

import click
from django.core.management.base import BaseCommand

from gyrinx.core.models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipment,
    ContentFighterEquipmentAssignment,
    ContentHouse,
    ContentImportVersion,
    ContentPolicy,
    ContentSkill,
)
from scripts.schema import gather_data


def flatten(xss):
    return [x for xs in xss for x in xs]


def data_for_type(name, data_sources):
    return flatten([src.data for src in data_sources if src.name == name])


def stable_uuid(v):
    return uuid.UUID(hashlib.md5(v.encode()).hexdigest()[:32])


def id_for_fighter(fi):
    return f"{fi.get('house', 'N/A')}:{fi['type']}"


def id_for_equipment(e):
    return f"{e['category']}:{e['name']}"


def id_for_skill(e):
    return f"{e['category']}:{e['name']}"


def lookup(index, type, id):
    try:
        return index[type][stable_uuid(id)]
    except KeyError:
        return None


def by_label(enum, label):
    try:
        return next(
            name for name, choice_label in enum.choices if choice_label == label
        )
    except StopIteration:
        raise ValueError(f"Label '{label}' not found in choices: {enum.choices}")


class Command(BaseCommand):
    help = "Import Gyrinx content library"

    def add_arguments(self, parser):
        parser.add_argument("directory", type=Path)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = bool(options["dry_run"])

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

        import_version = ContentImportVersion(
            uuid=stable_uuid(f"{ruleset_dir.name}:{uuid.uuid4()}"),
            ruleset=ruleset_dir.name,
            directory=options["directory"],
        )
        click.echo(
            f"ImportingVersion: {import_version.directory}, {import_version.ruleset} ({import_version.uuid})"
        )
        if not dry_run:
            import_version.save()

        #
        # House
        #

        houses = data_for_type("house", data_sources)
        click.echo(f"Found {len(houses)} houses: ")
        for h in houses:
            id = stable_uuid(h["name"])
            existing = ContentHouse.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.name} ({existing.uuid}, {existing.version})"
                )
                index["house"][existing.uuid] = existing
                continue
            house = ContentHouse(
                version=import_version,
                uuid=id,
                name=by_label(ContentHouse.Choices, h["name"]),
            )
            index["house"][house.uuid] = house
            click.echo(f" - {house.name} ({house.uuid}, {house.version})")
            if not dry_run:
                house.save()

        #
        # Category (of Fighter)
        #

        categories = data_for_type("category", data_sources)
        click.echo(f"Found {len(categories)} categories: ")
        for category in categories:
            id = stable_uuid(category["name"])
            existing = ContentCategory.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.name} ({existing.uuid}, {existing.version})"
                )
                index["category"][existing.uuid] = existing
                continue

            cat = ContentCategory(
                version=import_version,
                uuid=id,
                name=by_label(ContentCategory.Choices, category["name"]),
            )
            index["category"][cat.uuid] = cat
            click.echo(f" - {cat.name} ({cat.uuid}, {cat.version})")
            if not dry_run:
                cat.save()

        #
        # Skills
        #

        skills = data_for_type("skill", data_sources)
        click.echo(f"Found {len(skills)} skills: ")
        for skill in skills:
            id = stable_uuid(id_for_skill(skill))
            existing = ContentSkill.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.category} {existing.name} ({existing.uuid}, {existing.version})"
                )
                index["skill"][existing.uuid] = existing
                continue

            sk = ContentSkill(
                version=import_version,
                uuid=id,
                name=skill["name"],
                category=skill["category"],
            )
            index["skill"][sk.uuid] = sk
            click.echo(f" - {sk.category}: {sk.name} ({sk.uuid}, {sk.version})")
            if not dry_run:
                sk.save()

        #
        # Equipment Categories
        #

        eq_cats = data_for_type("equipment_category", data_sources)
        click.echo(f"Found {len(eq_cats)} equipment categories: ")
        for eq_cat in eq_cats:
            id = stable_uuid(eq_cat["name"])
            existing = ContentEquipmentCategory.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.name} ({existing.uuid}, {existing.version})"
                )
                index["equipment_category"][existing.uuid] = existing
                continue

            eq_cat = ContentEquipmentCategory(
                version=import_version,
                uuid=id,
                name=by_label(ContentEquipmentCategory.Choices, eq_cat["name"]),
            )
            index["equipment_category"][eq_cat.uuid] = eq_cat
            click.echo(f" - {eq_cat.name} ({eq_cat.uuid}, {eq_cat.version})")
            if not dry_run:
                eq_cat.save()

        #
        # Equipment
        #

        equipment = data_for_type("equipment", data_sources)
        click.echo(f"Found {len(equipment)} equipment: ")
        for e in equipment:
            category = lookup(index, "equipment_category", e["category"])
            if not category:
                click.echo(f"Error: Could not find category matching {e['category']}")
                raise ValueError(
                    f"Error: Could not find category matching {e['category']}"
                )

            id = stable_uuid(id_for_equipment(e))
            existing = ContentEquipment.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.name} ({existing.uuid}, {existing.version})"
                )
                index["equipment"][existing.uuid] = existing
                continue

            item = ContentEquipment(
                version=import_version,
                uuid=id,
                name=e["name"],
                category=category,
            )
            index["equipment"][item.uuid] = item
            click.echo(f" - {item.category}: {item.name} ({item.uuid}, {item.version})")
            if not dry_run:
                item.save()

        #
        # Fighters
        #

        fighters = data_for_type("fighter", data_sources)
        click.echo(f"Found {len(fighters)} fighters: ")
        for fi in fighters:
            category = lookup(index, "category", fi["category"])
            house = (
                lookup(index, "house", fi["house"]) if fi.get("house", None) else None
            )
            skills = [
                lookup(index, "skill", id_for_skill(s)) for s in fi.get("skills", [])
            ]
            if not category:
                raise ValueError(
                    f"Error: Could not find category matching {e['category']}"
                )
            if fi.get("house") and not house:
                raise ValueError(
                    f"Error: Could not find category matching {e['category']}"
                )
            if any(not skill for skill in skills):
                raise ValueError(f"Error: Could not find all skills for {fi}")

            id = stable_uuid(id_for_fighter(fi))
            existing = ContentFighter.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.type} ({existing.uuid}, {existing.version})"
                )
                fighter = existing
                index["fighter"][existing.uuid] = existing
            else:
                fighter = ContentFighter(
                    version=import_version,
                    uuid=id,
                    type=fi["type"],
                    category=category,
                    house=house,
                )
                index["fighter"][fighter.uuid] = fighter
                click.echo(
                    f" - {fighter.house or "N/A"}: {fighter.type} ({fighter.category.name}) ({fighter.uuid}, {fighter.version})"
                )
                if skills:
                    click.echo("   Skills:")
                    for skill in skills:
                        click.echo(f"    - {skill.category}: {skill.name}")

                if not dry_run:
                    fighter.save()
                    for skill in skills:
                        fighter.skills.add(skill)

            #
            # Fighter Equipment Assignment
            #

            equipment = [
                (lookup(index, "equipment", id_for_equipment(item)), item["qty"])
                for item in fi.get("equipment", [])
            ]
            if any(not item for item, qty in equipment):
                raise ValueError(f"Error: Could not find all equipment for {fi}")
            for item, qty in equipment:
                click.echo(f"    Found equipment for {fighter}: {item.name} ({qty})")

                id = stable_uuid(f"{fighter.uuid}:{item.uuid}")
                existing = ContentFighterEquipmentAssignment.objects.filter(
                    uuid=id
                ).first()
                if existing:
                    click.echo(
                        f"     - Existing: {existing.fighter}: {existing.equipment.name} ({existing.uuid}, {existing.version})"
                    )
                    index["fighter_equipment_assignment"][existing.uuid] = existing
                    continue

                fighter_equip = ContentFighterEquipmentAssignment(
                    version=import_version,
                    uuid=id,
                    fighter=fighter,
                    equipment=item,
                    qty=qty,
                )
                index["fighter_equipment_assignment"][fighter_equip.uuid] = (
                    fighter_equip
                )
                click.echo(
                    f"     - {fighter_equip.fighter}: {fighter_equip.equipment.name} ({fighter_equip.qty}, {fighter_equip.uuid}, {fighter_equip.version})"
                )
                if not dry_run:
                    fighter_equip.save()

            #
            # Policy
            #

            fi_policy = fi.get("weapons", {}).get("policy", None)
            if fi_policy:
                click.echo(f"    Found policy for {fighter}")
                rules = fi_policy.get("rules", [])

                id = stable_uuid(f"{fighter.uuid}:tpp")
                existing = ContentPolicy.objects.filter(uuid=id).first()
                if existing:
                    click.echo(
                        f"     - Existing: {existing.fighter}: {len(existing.rules)} rules ({existing.uuid}, {existing.version})"
                    )

                    index["fighter_weapons_policy"][existing.uuid] = existing
                else:
                    policy = ContentPolicy(
                        version=import_version,
                        uuid=id,
                        fighter=fighter,
                        rules=json.dumps(rules),
                    )
                    index["fighter_weapons_policy"][policy.uuid] = policy
                    click.echo(
                        f"     - {policy.fighter}: {len(rules)} rules ({policy.uuid}, {policy.version})"
                    )
                    if not dry_run:
                        policy.save()

        #
        # Fighter Equipment
        #

        equipment_list = data_for_type("equipment_list", data_sources)
        click.echo(f"Found {len(equipment_list)} equipment lists: ")
        for el in equipment_list:
            fighter = lookup(index, "fighter", id_for_fighter(el["fighter"]))
            if not fighter:
                click.echo(
                    f"Error: Could not find fighter matching {id_for_fighter(el['fighter'])}",
                    err=True,
                )
                raise ValueError(
                    f"Error: Could not find fighter matching {id_for_fighter(el['fighter'])}"
                )

            #
            # Fighter Equipment List
            #

            # TODO: What if equipment is removed?
            equipment = [
                (item["name"], lookup(index, "equipment", id_for_equipment(item)))
                for item in el["equipment"]
            ]
            for entry in equipment:
                name, item = entry
                if not item:
                    click.echo(
                        f"Error: Could not find equipment matching {name} for {fighter}",
                        err=True,
                    )
                    raise ValueError(
                        f"Error: Could not find equipment matching {name} for {fighter}"
                    )

                id = stable_uuid(f"{fighter.uuid}:{item.uuid}")
                existing = ContentFighterEquipment.objects.filter(uuid=id).first()
                if existing:
                    click.echo(
                        f" - Existing: {existing.fighter.type}: {existing.equipment.name} ({existing.uuid}, {existing.version})"
                    )
                    index["fighter_equipment"][existing.uuid] = existing
                    continue

                fighter_equip = ContentFighterEquipment(
                    version=import_version,
                    uuid=id,
                    fighter=fighter,
                    equipment=item,
                )
                index["fighter_equipment"][fighter_equip.uuid] = fighter_equip
                click.echo(
                    f" - {fighter_equip.fighter.type}: {fighter_equip.equipment.name} ({fighter_equip.uuid}, {fighter_equip.version})"
                )
                if not dry_run:
                    fighter_equip.save()
