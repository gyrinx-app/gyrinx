"""The core rulebook's Territories — their income and their boons.

The Territory Selection Table seed (``n26/library/territory_table.py``)
creates its eighteen Territories with no income and no boons, for a
content pass to fill in. This is that pass, for the system pack:

* Each Territory's income, as an Income contribution
  (``n26/library/income.py``). A Territory that already has an income is
  left as it is, so a figure an author entered by hand stays.
* A Reputation boon as a contribution to the Reputation counter, for as
  long as the gang holds the Territory.
* Any other boon — a cheaper recruit, free equipment, a special rule — as
  a ``Rule`` named after the kind of boon ("Recruit", "Equipment",
  "Special"), annotated with the Territory's name, given to the gang that
  holds it: the name only, never the rule's text. A boon the book offers
  instead of the income is stored as the plain income and the rule
  together, as the House territories' are (``journal_content.py``): the
  app does not model the either/or, so a holder reads both.

Battlefield effects are out of scope and stored nowhere. The Territories
are live, so what this writes is live too and reaches gangs already
holding one on their next read.

Everything is matched on its natural key and left alone if it is already
there, so running it twice changes nothing the second time. Names and
numbers are the book's; nothing else is. Written through the authoring
verbs, so it runs on live model classes only: as a maintenance operation
after a deploy, never from a migration.
"""

from dataclasses import dataclass

from django.conf import settings
from django.db import transaction

from n26.library.core_campaign import CAMPAIGN_TYPE, REPUTATION
from n26.library.gang_supertypes import Outcome
from n26.library.territory_table import TERRITORY
from n26.write_pause import guarded_write, write_guard

RECRUIT = "Recruit"
EQUIPMENT = "Equipment"
SPECIAL = "Special"


@dataclass(frozen=True)
class Territory:
    """One core Territory: its name, its income, and its boon besides the
    income — ``reputation`` where the boon is more Reputation, otherwise
    ``rule``, the kind of boon its rule is named after. ``instead`` marks
    a boon the book offers in place of the income boon."""

    name: str
    income: int
    reputation: int = 0
    rule: str = ""
    instead: bool = False


#: The eighteen Territories in the Territory Selection Table's order.
TERRITORIES = (
    Territory("Bullet Den", 15, rule=RECRUIT, instead=True),
    Territory("Rogue Doc Shop", 15, rule=RECRUIT, instead=True),
    Territory("Mess Shack", 15, rule=RECRUIT, instead=True),
    Territory("Drinking Hole", 15, rule=RECRUIT, instead=True),
    Territory("Fence Hangout", 15, rule=RECRUIT, instead=True),
    Territory("Bounty Den", 25),
    Territory("Generatorium", 15, reputation=1),
    Territory("Corpse Farm", 25),
    Territory("Tunnels", 20),
    Territory("Tech Bazaar", 15, rule=SPECIAL),
    Territory("Promethium Cache", 15, rule=EQUIPMENT, instead=True),
    Territory("Collapsed Dome", 20),
    Territory("Bone Shrine", 25),
    Territory("Mine Workings", 20, rule=EQUIPMENT, instead=True),
    Territory("Gambling Den", 15, reputation=1),
    Territory("Synth Still", 20),
    Territory("Old Ruins", 20),
    Territory("Fighting Pit", 25),
)

NOTHING_TO_DO = "Nothing to do: everything this seed can write is already there."


def seed_core_territory_content():
    """Fill in what is missing of the eighteen Territories' income and
    boons, and return an ``Outcome``: what was written and what was left
    alone, in words. A Territory the system pack does not have, or has
    under another asset type, is skipped and named."""
    from n26.library.authoring import (
        create_rule,
        ef_adds,
        ef_contributes_to_counter,
        modifier,
        set_income,
        targets_gang_alone,
    )
    from n26.library.income import income_modifiers, income_of
    from n26.library.models import (
        Asset,
        CampaignType,
        ContentPack,
        Counter,
        Modifier,
        Rule,
    )

    outcome = Outcome()
    lines = outcome.created
    pack = ContentPack.objects.get(slug=settings.DEFAULT_CONTENT_PACK_SLUG)
    campaign_type = CampaignType.objects.get(
        pack=pack, name__iexact=CAMPAIGN_TYPE, qualifier=""
    )
    territory_type = campaign_type.asset_types.get(label_singular__iexact=TERRITORY)
    reputation = Counter.objects.get(pack=pack, name__iexact=REPUTATION, qualifier="")

    def modifier_missing(name):
        return not Modifier.objects.filter(pack=pack, name__iexact=name).exists()

    for entry in TERRITORIES:
        asset = Asset.objects.filter(
            pack=pack, name__iexact=entry.name, qualifier=""
        ).first()
        if asset is None:
            outcome.skipped.append(
                f"skipped {entry.name}: the system pack has no territory of that name"
            )
            continue
        if asset.asset_type_id != territory_type.pk:
            outcome.skipped.append(
                f"skipped {entry.name}: an asset of that name stands under "
                "another asset type"
            )
            continue

        if income_modifiers(asset):
            outcome.skipped.append(
                f"skipped the income of {entry.name}: it already has {income_of(asset)}"
            )
        else:
            set_income(asset, entry.income)
            lines.append(f"{entry.name}: income {entry.income}")

        if entry.reputation:
            boon = f"{entry.name}: {REPUTATION}"
            if modifier_missing(boon):
                modifier(
                    boon,
                    targets_gang_alone(),
                    ef_contributes_to_counter(reputation, entry.reputation),
                    attach_to=asset,
                    pack=pack,
                )
                lines.append(
                    f"{entry.name}: {entry.reputation} more Reputation for the "
                    "gang that holds it"
                )

        if entry.rule:
            rule = Rule.objects.filter(
                pack=pack,
                name__iexact=entry.rule,
                annotation__iexact=entry.name,
                qualifier="",
            ).first()
            if rule is None:
                rule = create_rule(entry.rule, annotation=entry.name, pack=pack)
                lines.append(f"created the rule {rule}")
            boon = f"{entry.name}: {entry.rule}"
            if modifier_missing(boon):
                modifier(
                    boon,
                    targets_gang_alone(),
                    ef_adds(rule),
                    attach_to=asset,
                    pack=pack,
                )
                line = f"{entry.name}: the {rule} rule for the gang that holds it"
                if entry.instead:
                    # The book offers this boon in place of the income
                    # boon; both are stored, so a holder reads both.
                    line += " (the book offers it instead of the income)"
                lines.append(line)

    return outcome


@guarded_write
def seed_all():
    """The whole seed as one transaction, reported in words: what it
    wrote, then what it left alone — or, where it wrote nothing, a first
    line saying there was nothing to do, then what it left alone."""
    with transaction.atomic():
        outcome = seed_core_territory_content()
    if outcome.created:
        return outcome.lines
    return [NOTHING_TO_DO, *outcome.skipped]


class _RolledBack(Exception):
    """Carries a dry run's lines out of the transaction it rolls back."""


def preview():
    """What ``seed_all`` would do, without doing it: the seed runs inside
    a transaction that is rolled back, so the lines are exactly the run's
    own and nothing is written."""
    try:
        with transaction.atomic(), write_guard():
            raise _RolledBack(seed_all())
    except _RolledBack as rolled_back:
        return rolled_back.args[0]
