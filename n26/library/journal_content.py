"""The Underhive Journal territories — House of Chains and House of Blades.

Each journal adds a D6 table of six Territories that a gang of its House
may roll its starting Territory on (design/house-and-territory-tables.md).
Every Territory has an income figure and a House Controlled boon that
applies only while a gang of that House holds it; each also has a
battlefield effect, which is out of scope and stored nowhere.

What the seed writes, all in the system pack and all ``staged`` until an
author puts it live:

* Twelve ``Asset`` rows under the Territory asset type of the Territory
  campaign type, each with its income as an Income contribution
  (``n26/library/income.py``).
* The House Controlled boon on each. Where the book's boon is more income,
  it is a second Income contribution scoped to gangs that have picked the
  House. Anything else is a ``Rule`` named "Goliath Controlled" or "Escher
  Controlled", annotated with the Territory's name, given to the gang
  alone under the same condition — the name only, never the rule's text.
  A boon that replaces the income boon ("instead of gaining the Income
  Boon") is stored as the plain income and the rule together; making the
  two an either/or is a choice the app does not offer yet.
* Two ``AssetTable`` rows, Goliath Territories and Escher Territories, a
  D6 each with six entries on bands 1–1 to 6–6 in the book's order. They
  are House tables, not built into the campaign type: each is given by a
  modifier on the matching Gang supertype pickable
  (``n26/library/gang_supertypes.py``) — the gang alone gains the table —
  so every gang of that House holds it, Clan House Outcasts included, and
  no other gang does until an arbitrator opens it. The supertype
  pickables are markers that carry no boon logic; a table grant is how a
  House table reaches its gangs, and is the one modifier they carry.

Everything is matched on its natural key and left alone if it is already
there, so this can run against a database that has some of it, and
running it twice changes nothing the second time. Names and numbers are
the book's; nothing else is. Written through the authoring verbs, so it
runs on live model classes only: as a maintenance operation after a
deploy, never from a migration.
"""

from dataclasses import dataclass

from django.apps import apps
from django.conf import settings
from django.db import transaction

from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.gang_supertypes import SLOT, Outcome, seed_gang_supertypes
from n26.library.territory_table import TERRITORY

#: The stored value of ``Dice.D6``.
DICE = "d6"


@dataclass(frozen=True)
class Territory:
    """One journal Territory: its name, its income figure, and its House
    Controlled boon — ``more_income`` where the boon is more credits when
    collecting income, otherwise a rule named after the House. ``instead``
    marks a boon the book offers in place of the income boon; it is stored
    alongside the income for now."""

    name: str
    income: int
    more_income: int = 0
    instead: bool = False


#: Each journal's table: the House it belongs to, the table's name, and
#: its six Territories in the book's order, rolls 1 to 6.
JOURNALS = (
    (
        "Goliath",
        "Goliath Territories",
        (
            Territory("Slug House", 20),
            Territory("Flesh-makers Theatre", 15, instead=True),
            Territory("Fight Arena", 15),
            Territory("Amneo-vats", 15, more_income=10),
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
            Territory("Wyld Den", 15, instead=True),
            Territory("Rogue Las Factoria", 20, instead=True),
            Territory("Chem Arena", 15, instead=True),
            Territory("Shivver Den", 15),
        ),
    ),
)

NOTHING_TO_DO = "Nothing to do: every row is already there."


def controlled_rule_name(house):
    """ "Goliath Controlled" — the name every one of a House's boon rules
    shares; the Territory's name is the annotation."""
    return f"{house} Controlled"


def seed_journal_content():
    """Create what is missing of the two journals' territories and tables,
    and return an ``Outcome``: what was created and what was skipped, in
    words.

    The Territory campaign type and the Gang supertype are created first
    where they are missing, so this runs on a fresh database as readily
    as on one that has them; their lines are returned too. A House whose
    supertype pickable cannot be found still gets its territories and
    table, but no grant, and is named on the record.
    """
    from n26.library.authoring import (
        add_asset_table_entry,
        create_asset,
        create_rule,
        ef_adds,
        ef_contributes_to_counter,
        has_gang_pickable,
        modifier,
        targets_gang_alone,
    )
    from n26.library.income import ensure_income_counter
    from n26.library.models import (
        Asset,
        AssetTable,
        CampaignType,
        ContentPack,
        Modifier,
        Rule,
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

    def modifier_missing(name):
        return not Modifier.objects.filter(pack=pack, name__iexact=name).exists()

    for house, table_name, territories in JOURNALS:
        pick = picks.get(house)
        if pick is None:
            outcome.skipped.append(
                f"skipped the {house} Controlled boons and the {table_name} "
                f"grant: no {SLOT} pickable named {house}"
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
                    "under another asset type, so no boon or entry was made for it"
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
            boon = f"{entry.name}: {house} Controlled"
            if entry.more_income:
                if modifier_missing(boon):
                    modifier(
                        boon,
                        targets_gang_alone(has_gang_pickable(pick)),
                        ef_contributes_to_counter(income, entry.more_income),
                        attach_to=asset,
                        pack=pack,
                    )
                    lines.append(
                        f"{entry.name}: {entry.more_income} more income for "
                        f"gangs that have picked {house}"
                    )
            else:
                rule = Rule.objects.filter(
                    pack=pack,
                    name__iexact=controlled_rule_name(house),
                    annotation__iexact=entry.name,
                    qualifier="",
                ).first()
                if rule is None:
                    rule = create_rule(
                        controlled_rule_name(house), annotation=entry.name, **staged
                    )
                    lines.append(f"created the rule {rule}, staged")
                if modifier_missing(boon):
                    modifier(
                        boon,
                        targets_gang_alone(has_gang_pickable(pick)),
                        ef_adds(rule),
                        attach_to=asset,
                        pack=pack,
                    )
                    line = f"{entry.name}: the {rule} rule for gangs that have picked {house}"
                    if entry.instead:
                        # The book offers this boon in place of the income
                        # boon. Both are stored; the either/or is not
                        # offered yet, so a holder reads both for now.
                        line += " (the book offers it instead of the income)"
                    lines.append(line)

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

    return outcome


def seed_all():
    """The whole seed as one transaction, reported in words: what it
    created, then what it skipped — or, where it created nothing, a first
    line saying there was nothing to do, then what it skipped."""
    with transaction.atomic():
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
        with transaction.atomic():
            raise _RolledBack(seed_all())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
