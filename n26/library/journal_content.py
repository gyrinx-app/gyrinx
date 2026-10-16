"""The Underhive Journal territories — House of Chains and House of Blades.

Each journal adds a D6 table of six Territories that a gang of its House
may roll its starting Territory on (design/house-and-territory-tables.md).
Every Territory has its baseline income figure. Additional boons and
battlefield effects are not seeded.

What the seed writes, all in the system pack and all ``staged`` until an
author puts it live:

* Twelve ``Asset`` rows under the Territory asset type of the Territory
  campaign type, each with its income as an Income contribution
  (``n26/library/income.py``).
* Two ``AssetTable`` rows, Goliath Territories and Escher Territories, a
  D6 each with six entries on bands 1–1 to 6–6 in the book's order. They
  are House tables, not built into the campaign type: each is given by a
  modifier on the matching Gang supertype pickable
  (``n26/library/gang_supertypes.py``) — the gang alone gains the table —
  so every gang of that House holds it, Clan House Outcasts included, and
  no other gang does until an arbitrator opens it. The supertype
  pickables are markers that carry no boon logic; a table grant is how a
  House table reaches its gangs, and is the one modifier they carry.

Missing content is matched on its natural key. The maintenance run also
removes the known seeded House Controlled modifiers and unused placeholder
rules. Modified or reused content is retained and reported; protected rule
references, including player assignments, are preserved. Names and numbers
are the book's; nothing else is. Written through the authoring verbs, so it
runs on live model classes only: as a maintenance operation after a deploy,
never from a migration.
"""

from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import ProtectedError

from n26.library.core_campaign import (
    CAMPAIGN_TYPE,
    DESCRIPTION,
    LIBRARY_AUTHOR_HELP,
    seed_core_campaign,
)
from n26.library.gang_supertypes import SLOT, Outcome, seed_gang_supertypes
from n26.library.territory_table import TERRITORY
from n26.write_pause import SCOPE, exclusive_write_scope, write_guard

#: The stored value of ``Dice.D6``.
DICE = "d6"


@dataclass(frozen=True)
class Territory:
    """One journal territory's name and baseline income figure."""

    name: str
    income: int


#: Each journal's table: the House it belongs to, the table's name, and
#: its six Territories in the book's order, rolls 1 to 6.
JOURNALS = (
    (
        "Goliath",
        "Goliath Territories",
        (
            Territory("Slug House", 20),
            Territory("Flesh-makers Theatre", 15),
            Territory("Fight Arena", 15),
            Territory("Amneo-vats", 15),
            Territory("Feasting Hall", 20),
            Territory("Badzone Smelter", 20),
        ),
    ),
    (
        "Escher",
        "Escher Territories",
        (
            Territory("Phelynx Pen", 20),
            Territory("Bio-lab", 15),
            Territory("Wyld Den", 15),
            Territory("Rogue Las Factoria", 20),
            Territory("Chem Arena", 15),
            Territory("Shivver Den", 15),
        ),
    ),
)

NOTHING_TO_DO = "Nothing to do: journal content is up to date."


def _reset_campaign_copy(campaign_type):
    """Replace the seed's former boon claims; preserve authored wording."""
    words = {
        "description": (
            DESCRIPTION.replace(
                "The campaign has three phases:",
                "Each Territory a gang holds gives it a Boon, such as income, "
                "Reputation or equipment. The campaign has three phases:",
            ),
            DESCRIPTION,
        ),
        "library_author_help": (
            LIBRARY_AUTHOR_HELP.replace("Reputation at 1", "Reputation at 0").replace(
                "with its income in the Income box.",
                "with its income in the Income box and its Boons as modifiers.",
            ),
            LIBRARY_AUTHOR_HELP,
        ),
    }
    changed = []
    for name, (former, current) in words.items():
        if getattr(campaign_type, name) == former:
            setattr(campaign_type, name, current)
            changed.append(name)
    if changed:
        campaign_type.save(update_fields=changed)
    return [f"updated {campaign_type.name} {name}" for name in changed]


def _is_seeded_boon(modifier, asset, pick, rule, income):
    """A name alone cannot distinguish seeded content from authored content."""
    from n26.library.models.modifier import (
        EFFECT_FIELDS,
        GRANTABLE_FIELDS,
        SCOPE_FIELDS,
        GangHasPickable,
    )
    from n26.library.references import references_to

    if modifier.staged or modifier.archived or modifier.archived_at is not None:
        return False
    if any(
        getattr(modifier, f"{field}_id") is not None
        for field in SCOPE_FIELDS
        if field != "targets_gang"
    ):
        return False
    effect_field = (
        "contributes_to_counter" if asset.name == "Amneo-vats" else "adds_assignable"
    )
    if any(
        getattr(modifier, f"{field}_id") is not None
        for field in EFFECT_FIELDS
        if field != effect_field
    ):
        return False
    scope = modifier.targets_gang
    if scope is None or scope.echoes:
        return False
    conditions = [
        condition
        for relation in scope.CONDITIONS
        for condition in getattr(scope, relation).all()
    ]
    if (
        len(conditions) != 1
        or not isinstance(conditions[0], GangHasPickable)
        or conditions[0].negate
    ):
        return False
    if list(conditions[0].pickables.all()) != [pick]:
        return False
    if asset.name == "Amneo-vats":
        effect = modifier.contributes_to_counter
        if effect is None or effect.counter_id != income.pk or effect.amount != 10:
            return False
    else:
        effect = modifier.adds_assignable
        if (
            rule is None
            or effect is None
            or effect.rule_id != rule.pk
            or effect.with_pick_id is not None
            or any(
                getattr(effect, f"{field}_id") is not None
                for field in GRANTABLE_FIELDS
                if field != "rule"
            )
        ):
            return False
    references = references_to(modifier)
    return len(references) == 1 and references[0].row == asset


def _is_seeded_rule(rule):
    return not (
        not rule.staged
        or rule.archived
        or rule.archived_at is not None
        or rule.modifiers.exists()
        or rule.built_ins_id is not None
        or rule.library_author_help
        or rule.price != 0
        or rule.trade_point_price is not None
        or rule.is_exclusive
        or rule.category_id is not None
        or rule.position != 0
    )


def _remove_seeded_boons(pack, territory, picks, income):
    """Remove only the journal seed's known modifier and rule shapes.

    Holdings and their histories never reference computed grants, so removing
    a modifier does not rewrite player data. A rule used directly remains
    protected by the library's ordinary deletion contract.
    """
    from n26.library.authoring import delete_content, delete_modifier
    from n26.library.models import Asset, Modifier, Rule

    outcome = Outcome()
    for house, _table_name, territories in JOURNALS:
        for entry in territories:
            rule_name = f"{house} Controlled"
            rule = None
            if entry.name != "Amneo-vats":
                rule = Rule.objects.filter(
                    pack=pack, name=rule_name, annotation=entry.name, qualifier=""
                ).first()
            asset = Asset.objects.filter(
                pack=pack, name=entry.name, qualifier="", asset_type=territory
            ).first()
            boon_name = f"{entry.name}: {rule_name}"
            boon = Modifier.objects.filter(pack=pack, name=boon_name).first()
            if rule is not None and not _is_seeded_rule(rule):
                outcome.skipped.append(
                    f"skipped rule {rule} and its modifier: its content "
                    "differs from the journal seed"
                )
                continue
            if boon is not None:
                if asset is None or not _is_seeded_boon(
                    boon, asset, picks.get(house), rule, income
                ):
                    outcome.skipped.append(
                        f"skipped modifier {boon_name}: its content or carriers "
                        "differ from the journal seed"
                    )
                    continue
                delete_modifier(boon)
                outcome.created.append(f"removed modifier {boon_name}")
            if rule is None:
                continue
            label = str(rule)
            try:
                delete_content(rule)
            except ProtectedError:
                outcome.skipped.append(
                    f"skipped rule {label}: it is still referenced by content "
                    "or player history"
                )
            else:
                outcome.created.append(f"removed rule {label}")
    return outcome


def seed_journal_content():
    """Create what is missing of the two journals' territories and tables,
    remove known seeded Controlled boons, and report changes and skips.

    The Territory campaign type and the Gang supertype are created first
    where they are missing, so this runs on a fresh database as readily
    as on one that has them; their lines are returned too. A House whose
    supertype pickable cannot be found still gets its territories and
    table, but no grant, and is named on the record.
    """
    from n26.library.authoring import (
        add_asset_table_entry,
        create_asset,
        ef_adds,
        modifier,
        targets_gang_alone,
    )
    from n26.library.income import ensure_income_counter
    from n26.library.models import (
        Asset,
        AssetTable,
        CampaignType,
        ContentPack,
    )

    outcome = Outcome(created=seed_core_campaign(apps))
    supertypes, picks = seed_gang_supertypes()
    outcome.extend(supertypes)
    lines = outcome.created

    pack = ContentPack.objects.get(slug=settings.DEFAULT_CONTENT_PACK_SLUG)
    campaign_type = CampaignType.objects.get(
        pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
    )
    territory = campaign_type.asset_types.get(label_singular__iexact=TERRITORY)
    income = ensure_income_counter()
    staged = {"pack": pack, "staged": True}

    for house, table_name, territories in JOURNALS:
        pick = picks.get(house)
        if pick is None:
            outcome.skipped.append(
                f"skipped the {table_name} grant: no {SLOT} pickable named {house}"
            )

        table = AssetTable.objects.filter(
            pack=pack, name__iexact=table_name, qualifier=""
        ).first()
        if table is None:
            # Written directly rather than through create_asset_table,
            # which builds a table into its campaign type: this one is
            # the House's, given by the pick below.
            table = AssetTable.objects.create(
                name=table_name, asset_type=territory, dice=DICE, **staged
            )
            lines.append(f"created the {table_name} table, staged")

        for position, entry in enumerate(territories):
            asset = Asset.objects.filter(
                pack=pack, name__iexact=entry.name, qualifier=""
            ).first()
            if asset is None:
                asset = create_asset(
                    entry.name, territory, income=entry.income, **staged
                )
                lines.append(
                    f"created the {entry.name} {TERRITORY} with income "
                    f"{entry.income}, staged"
                )
            elif asset.asset_type_id != territory.pk:
                outcome.skipped.append(
                    f"skipped {entry.name}: an asset of that name already stands "
                    "under another asset type, so no table entry was made for it"
                )
                continue

            roll = position + 1
            if not table.entries.filter(asset=asset).exists():
                add_asset_table_entry(
                    table, asset, position=position, roll_low=roll, **staged
                )
                lines.append(
                    f"added {entry.name} to the {table_name} table on {roll}-{roll}"
                )

        if pick is None:
            continue
        if not pick.modifiers.filter(adds_assignable__asset_table=table).exists():
            modifier(
                f"{house}: gives the {table_name} table",
                targets_gang_alone(),
                ef_adds(table),
                attach_to=pick,
                pack=pack,
            )
            lines.append(f"{house} gangs now hold the {table_name} table")

    outcome.created.extend(_reset_campaign_copy(campaign_type))
    outcome.extend(_remove_seeded_boons(pack, territory, picks, income))
    return outcome


def seed_all():
    """Seed and reset in one transaction, reporting creations and removals,
    then skipped content. A run with no changes reports nothing to do."""
    # The complete candidate graph must stay unchanged between inspection
    # and deletion, including references added by an authoring transaction.
    with exclusive_write_scope(SCOPE), write_guard():
        outcome = seed_journal_content()
    if outcome.created:
        return outcome.lines
    return [NOTHING_TO_DO, *outcome.skipped]


class _RolledBack(Exception):
    """Carries a dry run's lines out of the transaction it rolls back."""


def preview():
    """What ``seed_all`` would do, without doing it: the seed runs inside
    a transaction that is rolled back, so the lines are exactly the run's
    own and nothing is written — not even the propagation filings, whose
    messages publish only on commit."""
    try:
        # seed_all takes exclusive admission before any nested authoring guard.
        with transaction.atomic():
            raise _RolledBack(seed_all())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
