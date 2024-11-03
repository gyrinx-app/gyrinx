import json
from pathlib import Path

import click
from django.core.management.base import BaseCommand

from gyrinx.content.management.imports import ImportConfig, Importer
from gyrinx.content.management.utils import (
    by_label,
    data_for_type,
    gather_data,
    id_for_skill,
    stable_uuid,
)
from gyrinx.content.models import (
    ContentCategory,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipment,
    ContentFighterEquipmentAssignment,
    ContentHouse,
    ContentPolicy,
    ContentSkill,
)


def id_for_fighter(fi):
    return f"{fi.get('house', 'N/A')}:{fi['type']}"


def id_for_equipment(e):
    return f"{e['category']}:{e['name']}"


def lookup(index, type, id):
    try:
        return index[type][stable_uuid(id)]
    except KeyError:
        return None


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

        imp = Importer(ruleset_dir, options["directory"], dry_run)

        # TODO: Clear this up when all the imports have been converted to use the Importer
        index = imp.index
        import_version = imp.iv

        #
        # House
        #

        ic_house = ImportConfig(
            source="house",
            id=lambda x: x["name"],
            model=ContentHouse,
            fields=lambda x: {
                "name": by_label(ContentHouse.Choices, x["name"]),
            },
        )
        imp.do(ic_house, data_sources)

        #
        # Category (of Fighter)
        #

        ic = ImportConfig(
            source="category",
            id=lambda x: x["name"],
            model=ContentCategory,
            fields=lambda x: {
                "name": by_label(ContentCategory.Choices, x["name"]),
            },
        )
        imp.do(ic, data_sources)

        #
        # Skills
        #

        ic = ImportConfig(
            source="skill",
            id=id_for_skill,
            model=ContentSkill,
            fields=lambda x: {
                "name": x["name"],
                "category": x["category"],
            },
        )
        imp.do(ic, data_sources)

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
                click.echo(f"Error: Could not find category {e['category']} for {e}")
                raise ValueError(
                    f"Error: Could not find category {e['category']} for {e}"
                )

            id = stable_uuid(id_for_equipment(e))
            existing = ContentEquipment.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.name} ({existing.uuid}, {existing.version})"
                )
                item = existing

                # Migrate: trading_post_cost
                if item.trading_post_cost != e.get("trading_post_cost", 0):
                    click.echo(
                        f"   Adding: trading_post_cost {e.get('trading_post_cost', 0)} to {item}"
                    )
                    item.trading_post_cost = e.get("trading_post_cost", 0)

                index["equipment"][existing.uuid] = existing
            else:
                item = ContentEquipment(
                    version=import_version,
                    uuid=id,
                    name=e["name"],
                    category=category,
                    trading_post_cost=e.get("trading_post_cost", 0),
                )
                click.echo(
                    f" - {item.category}: {item.name} ({item.uuid}, {item.version})"
                )
                index["equipment"][item.uuid] = item

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
                    f"Error: Could not find category {fi['category']} for {fi}"
                )
            if fi.get("house") and not house:
                raise ValueError(f"Error: Could not find house {fi['house']} for {fi}")
            if any(not skill for skill in skills):
                raise ValueError(f"Error: Could not find all skills for {fi}")

            id = stable_uuid(id_for_fighter(fi))
            existing = ContentFighter.objects.filter(uuid=id).first()
            if existing:
                click.echo(
                    f" - Existing: {existing.type} ({existing.uuid}, {existing.version})"
                )
                fighter = existing

                # Migrate: cost
                if fighter.base_cost != fi.get("cost", 0):
                    click.echo(f"   Adding: cost {fi.get('cost', 0)} to {fighter}")
                    fighter.base_cost = fi.get("cost", 0)

                index["fighter"][existing.uuid] = existing
            else:
                fighter = ContentFighter(
                    version=import_version,
                    uuid=id,
                    type=fi["type"],
                    category=category,
                    house=house,
                    base_cost=fi.get("cost", 0),
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
