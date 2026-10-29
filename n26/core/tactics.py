"""Gang Tactics: how many a gang may hold, the ones it holds, and rolling
for more.

How many a gang may hold is a **counter reading**, as a Trading Post
visit's Trade Points are (``n26.core.trading``). The library holds an
undrawn counter, ``Gang Tactics contribution``, raised by a modifier on
each rank: 2 on Leader, 1 on Champion. The allowance is the sum of every
model's reading, so a promotion or a loss changes it with nothing to keep
in step. The player never sees the figure per model; the page shows the
gang's totals only.

Each tactic rolled is a ``GangTactic`` row naming the model whose share
paid for it. Rolling picks a model with share left over, biggest share
first, so the rows always say which rank brought which tactic.

The tables are library roll tables (``n26.library.gang_tactics``): a
gang may roll on each one a modifier gives it, through a hidden slot of
the ``Gang Tactic`` slot type.

A card's body is the owner's **tactics notes**: their own words about
the tactic, kept per gang and tactic (``GangTacticNotes``), so a tactic
rolled again later finds its notes waiting. The site never stores the
rules themselves. Where ``N26_TACTICS_NOTES`` names a local CSV (columns
``table``, ``name``, ``timing``, ``effect``) and the ``tactics-notes``
switch is on, each card also offers a suggested summary built from it.
That is helper text, not the official rules: it reaches the page only
for a reader to copy into their own notes, and is never saved on its own.
"""

import csv
import os
from dataclasses import dataclass

from django.utils.html import escape

from n26.core.operations import Refusal

#: How many times one roll is made again for a result the gang already
#: holds before giving up. The table is checked for a free result first,
#: so reaching this means the dice are not random.
MOST_REROLLS = 100


@dataclass(frozen=True)
class Share:
    """One model's share of the gang's tactics, and how much of it the
    gang has already rolled for."""

    miniature: object
    amount: int
    spent: int

    @property
    def left(self):
        return max(0, self.amount - self.spent)


@dataclass(frozen=True)
class TacticCard:
    """One held tactic, as its card draws it."""

    pk: str
    name: str
    table_name: str
    dice_label: str
    roll: int
    #: The tactic, which the owner's notes are kept against.
    tactic: str
    #: The owner's saved notes, cleaned to what a card may draw.
    notes: str = ""
    #: The suggested summary from the local tactics notes file, as HTML
    #: with every word escaped. Empty where there is none.
    suggested_notes: str = ""
    #: Rolled by the Develop Tactics action, or re-rolled from one that was.
    developed: bool = False
    #: Where the tactic is printed in the books.
    reference: str = ""
    #: Drawn as a bonus, outside the ranks' allowance.
    bonus: bool = False


@dataclass(frozen=True)
class TableChoice:
    value: str
    label: str
    description: str
    checked: bool
    full: bool


@dataclass(frozen=True)
class Table:
    """One Gang Tactics roll table a gang may roll on, with its rows."""

    picklist: object
    members: tuple

    @property
    def key(self):
        return str(self.picklist.pk)

    @property
    def name(self):
        return self.picklist.name

    @property
    def dice(self):
        return self.picklist.dice

    @property
    def dice_label(self):
        from n26.library.models.slots import Dice

        return Dice.label_for(self.picklist.dice)

    def landing(self, roll):
        """The row a roll lands on, or None for a roll nothing claims."""
        found = self.picklist.landing(roll, self.members)
        return found[0] if found else None


@dataclass(frozen=True)
class Allowance:
    """The gang's three figures, and the shares behind the first."""

    shares: tuple
    held: int

    @property
    def available(self):
        return sum(share.amount for share in self.shares)

    @property
    def to_generate(self):
        return max(0, self.available - self.held)

    @property
    def over_by(self):
        """How many more tactics the gang holds than its ranks allow."""
        return max(0, self.held - self.available)


def held(gang):
    """The gang's tactics, oldest first, with their table and tactic."""
    from n26.core.models import GangTactic

    return list(
        GangTactic.objects.filter(gang=gang, archived=False)
        .select_related("picklist", "pickable")
        .order_by("created")
    )


def allowance(gang, tactics=None, members=None):
    """How many tactics the gang may hold, and how many it holds.

    Each model on the roster brings what its rank adds. Each completed
    Develop Tactics action brings one more, credited to the model that
    performed it; that one stays with the gang even after the model has
    gone, because the rule adds the tactic to the gang's roster.
    """
    from django.db.models import Count

    from n26.core.models import ActionRecord, Miniature
    from n26.core.render import roster
    from n26.core.trading import _readings
    from n26.library.standard_content import tactics_contribution_counter

    tactics = held(gang) if tactics is None else tactics
    members = roster(gang) if members is None else members
    spent = {}
    # A bonus tactic is held but was never paid for by a rank.
    counted = [tactic for tactic in tactics if not tactic.bonus]
    for tactic in counted:
        spent[tactic.source_id] = spent.get(tactic.source_id, 0) + 1
    amounts = {}
    counter = tactics_contribution_counter()
    if counter is not None:
        readings = _readings(gang, counter)
        for member in members:
            amount, _ = readings.get(member.pk, (0, ""))
            if amount > 0:
                amounts[member.pk] = amount
    developed = dict(
        ActionRecord.objects.filter(
            gang=gang,
            state=ActionRecord.State.COMPLETED,
            outcome__generate_gang_tactic__isnull=False,
        )
        .values("fighter_id")
        .annotate(count=Count("pk"))
        .values_list("fighter_id", "count")
    )
    for fighter_id, count in developed.items():
        amounts[fighter_id] = amounts.get(fighter_id, 0) + count
    by_pk = {member.pk: member for member in members}
    missing = [pk for pk in amounts if pk not in by_pk]
    if missing:
        by_pk.update({one.pk: one for one in Miniature.objects.filter(pk__in=missing)})
    shares = [
        Share(by_pk[pk], amount, spent.get(pk, 0)) for pk, amount in amounts.items()
    ]
    shares.sort(key=lambda share: (-share.amount, share.miniature.name))
    return Allowance(shares=tuple(shares), held=len(counted))


def tables(gang):
    """The tables this gang may roll on, in their slots' order.

    The gang's own card is computed, as the gang sheet computes it, and
    every hidden Gang Tactic slot a modifier gave it names one table.
    """
    from n26.core.card import (
        build_gang_cards,
        build_modifier_index,
        carriers,
        held_assets,
    )
    from n26.core.effects import compute
    from n26.library.models import Slot

    card = build_gang_cards([gang], {gang.pk: held_assets(gang)})[gang.pk]
    computed = compute(card, build_modifier_index(carriers(card)))
    given = {
        contribution.thing.pk
        for contribution in computed.acquired
        if isinstance(contribution.thing, Slot)
    }
    return _tables_of(Slot.objects.filter(pk__in=given))


def every_table():
    """Every Gang Tactics table in the library, in their slots' order. A
    bonus tactic may be drawn from any of them, whichever gangs they are
    given to."""
    from n26.library.models import Slot

    return _tables_of(Slot.objects.filter(archived=False, picklist__archived=False))


def _tables_of(slots):
    """The roll tables these Gang Tactic slots name, each once."""
    from n26.library.gang_tactics import SLOT_TYPE

    slots = (
        slots.filter(slot_type__name__iexact=SLOT_TYPE)
        .exclude(picklist__dice="")
        .select_related("picklist")
        .order_by("position", "name")
    )
    found = []
    seen = set()
    for slot in slots:
        if slot.picklist_id in seen:
            continue
        seen.add(slot.picklist_id)
        found.append(Table(slot.picklist, tuple(slot.picklist.available_members())))
    return found


def _table(gang, key, *, bonus=False):
    """One of the gang's tables by its key, or any table for a bonus, or
    a refusal."""
    for table in every_table() if bonus else tables(gang):
        if table.key == key:
            return table
    raise Refusal("Choose a table this gang can roll on.")


def table_choices(gang, tactics, chosen="", *, bonus=False):
    """Each table as a radio card: the gang's own, or every table for a
    bonus. A table the gang holds every result of is marked full, and is
    never the default."""
    holding = {tactic.pickable_id for tactic in tactics}
    choices = []
    open_tables = []
    for table in every_table() if bonus else tables(gang):
        full = all(member.pickable_id in holding for member in table.members)
        if not full:
            open_tables.append(table.key)
        choices.append((table, full))
    if chosen not in open_tables:
        chosen = open_tables[0] if open_tables else ""
    return [
        TableChoice(
            value=table.key,
            label=f"{table.name} ({table.dice_label})",
            description=(
                "Every result on this table is held."
                if full
                else f"{len(table.members)} tactics."
            ),
            checked=table.key == chosen,
            full=full,
        )
        for table, full in choices
    ]


def cards(tactics, suggest=None):
    """The held tactics as cards, in the order they were rolled, each with
    the gang's saved notes for that tactic.

    ``suggest`` says whether the cards carry a suggested summary from the
    tactics notes file; left out, the ``tactics-notes`` switch decides.
    Every card says where the tactic is printed either way.
    """
    from n26.core.models import GangTacticNotes
    from n26.core.templatetags.richtext import clean_tactics_notes
    from n26.library.models.slots import Dice

    if suggest is None:
        from n26.flags import TACTICS_NOTES, switched_on

        suggest = switched_on(TACTICS_NOTES)
    suggestions = _suggested_tactics_notes() if suggest else {}
    tactics = list(tactics)
    saved = {}
    if tactics:
        saved = dict(
            GangTacticNotes.objects.filter(
                gang_id=tactics[0].gang_id,
                pickable_id__in=[tactic.pickable_id for tactic in tactics],
            ).values_list("pickable_id", "notes")
        )
    shown = []
    for tactic in tactics:
        timing, effect = suggestions.get(
            (_folded(tactic.picklist.name), _folded(tactic.pickable.name)), ("", "")
        )
        shown.append(
            TacticCard(
                pk=str(tactic.pk),
                name=tactic.pickable.name,
                table_name=tactic.picklist.name,
                dice_label=Dice.label_for(tactic.picklist.dice),
                roll=tactic.roll,
                tactic=str(tactic.pickable_id),
                notes=clean_tactics_notes(saved.get(tactic.pickable_id, "")),
                suggested_notes=suggested_summary(timing, effect),
                developed=tactic.action_record_id is not None,
                bonus=tactic.bonus,
                reference=tactic.pickable.summary,
            )
        )
    return shown


def suggested_summary(timing, effect):
    """A tactic's timing and effect as the HTML a notes box takes: one
    paragraph each, labelled, every word escaped. Empty when both are."""
    parts = [
        f"<p><strong>{label}:</strong> {escape(text.strip())}</p>"
        for label, text in (("Timing", timing), ("Effect", effect))
        if text.strip()
    ]
    return "".join(parts)


def roll_tactics(op, table_key, count, rng=None):
    """Roll ``count`` tactics on one table and add them to the gang.

    Called inside the gang's operation, so the allowance and the held
    tactics are read under the gang's line and two clicks cannot both
    spend the last share. A result the gang already holds is rolled
    again, as the rule says. Refused when the gang has fewer shares left
    than asked for, or the table runs out of results it does not hold.
    """
    gang = op.gang
    table = _table(gang, table_key)
    tactics = held(gang)
    room = allowance(gang, tactics)
    if count < 1:
        raise Refusal("Roll at least one tactic.")
    if count > room.to_generate:
        raise Refusal(
            f"{gang.name} has {room.to_generate} "
            f"tactic{'' if room.to_generate == 1 else 's'} to roll for."
        )
    holding = {one.pickable_id for one in tactics}
    shares = [[share.miniature, share.left] for share in room.shares]
    gained = []
    for _ in range(count):
        roll, landed, rolls = _roll_free(gang, table, holding, rng)
        source = next(share for share in shares if share[1] > 0)
        source[1] -= 1
        holding.add(landed.pickable_id)
        gained.append(
            op.gain_tactic(
                picklist=table.picklist,
                pickable=landed.pickable,
                roll=roll,
                dice=table.dice,
                source=source[0],
                note=_rolled_note(table, landed, rolls),
            )
        )
    return gained


def roll_bonus_tactics(op, table_key, count, rng=None):
    """Draw ``count`` bonus tactics from any table and add them to the gang.

    A bonus is outside what the gang's ranks allow: it spends no share and
    does not count against them. It still never duplicates a tactic the
    gang holds.
    """
    gang = op.gang
    table = _table(gang, table_key, bonus=True)
    if count < 1:
        raise Refusal("Draw at least one bonus tactic.")
    holding = {one.pickable_id for one in held(gang)}
    gained = []
    for _ in range(count):
        roll, landed, rolls = _roll_free(gang, table, holding, rng)
        holding.add(landed.pickable_id)
        gained.append(
            op.gain_tactic(
                picklist=table.picklist,
                pickable=landed.pickable,
                roll=roll,
                dice=table.dice,
                source=None,
                bonus=True,
                note=f"{_rolled_note(table, landed, rolls)} as a bonus",
            )
        )
    return gained


def reroll_tactic(op, old, table_key, rng=None):
    """Swap one held tactic for a new roll on the table the owner picks.

    The new tactic spends the same model's share as the old one, and
    keeps any Develop Tactics action it came from, so a re-roll never
    changes how many the gang holds. It never lands on the tactic being
    replaced, nor on any other the gang holds.
    """
    from n26.core.models import GangTactic, LedgerEvent

    gang = op.gang
    old = (
        GangTactic.objects.select_for_update()
        .select_related("pickable")
        .get(pk=old.pk, gang=gang)
    )
    if old.archived:
        raise Refusal("That Gang Tactic has already gone.")
    table = _table(gang, table_key, bonus=old.bonus)
    holding = {one.pickable_id for one in held(gang)}
    roll, landed, rolls = _roll_free(gang, table, holding, rng)
    was = name_of(old)
    old.archive()
    return op.gain_tactic(
        picklist=table.picklist,
        pickable=landed.pickable,
        roll=roll,
        dice=table.dice,
        source=old.source,
        action_record=old.action_record,
        bonus=old.bonus,
        note=f"{was} into {_rolled_note(table, landed, rolls)}",
        kind=LedgerEvent.Kind.TACTIC_REROLLED,
    )


def preview_develop(record, terms):
    """What a Develop Tactics action will do, checked as it stands now.

    The player's one choice is the table. The fighter must still be in
    the gang and Active: a model that is dead, captured or recovering
    performs no post-cycle action.
    """
    from n26.core.status import Status, label_for

    gang = record.gang
    fighter = record.fighter
    if fighter.status != Status.ACTIVE:
        raise Refusal(
            f"{fighter.name} is {label_for(fighter.status).lower()} and cannot "
            "develop tactics."
        )
    table = _table(gang, terms.get("table", ""))
    holding = {one.pickable_id for one in held(gang)}
    if all(member.pickable_id in holding for member in table.members):
        raise Refusal(f"{gang.name} holds every tactic on the {table.name} table.")
    return {"table": table.key, "table_name": table.name, "dice": table.dice}


def apply_develop(op, record, terms, rng=None):
    """Roll the Develop Tactics action's tactic and add it to the gang.

    The roll is made here, at confirmation, so it cannot be seen and
    turned down. The tactic names the fighter and the action record, and
    the record is what credits the gang its extra tactic.
    """
    preview_develop(record, terms)
    table = _table(op.gang, terms["table"])
    holding = {one.pickable_id for one in held(op.gang)}
    roll, landed, rolls = _roll_free(op.gang, table, holding, rng)
    return op.gain_tactic(
        picklist=table.picklist,
        pickable=landed.pickable,
        roll=roll,
        dice=table.dice,
        source=record.fighter,
        note=_rolled_note(table, landed, rolls),
        action_record=record,
    )


def developed_tactic(record):
    """The tactic a completed Develop Tactics action rolled, as a card, or
    None where it has since been deleted."""
    from n26.core.models import GangTactic

    found = (
        GangTactic.objects.filter(action_record=record, archived=False)
        .select_related("picklist", "pickable")
        .first()
    )
    return cards([found])[0] if found else None


def name_of(tactic):
    """A held tactic's name, as its pickable says it now."""
    return tactic.pickable.name


def _roll_free(gang, table, holding, rng):
    """Roll on ``table`` until the result is a tactic not in ``holding``.

    Returns the roll kept, the row it landed on, and every roll made.
    Refused when the gang already holds everything on the table.
    """
    from n26.library.models.slots import Dice

    if all(member.pickable_id in holding for member in table.members):
        raise Refusal(f"{gang.name} holds every tactic on the {table.name} table.")
    rolls = []
    for _ in range(MOST_REROLLS):
        roll = Dice.roll(table.dice, rng)
        rolls.append(roll)
        landed = table.landing(roll)
        if landed is not None and landed.pickable_id not in holding:
            return roll, landed, rolls
    raise RuntimeError(
        f"No free result after {MOST_REROLLS} rolls."
    )  # pragma: no cover


def too_many_for(campaign, gang):
    """Whether a gang holds more tactics than its ranks allow, while the
    campaign has not started — as ``over_budget`` asks of credits. After
    the start a rank can be lost in play, and no rule says what happens
    to its tactics then."""
    return gang.pk in too_many_among(campaign, [gang])


def too_many_among(campaign, gangs):
    """The ids of the gangs here that hold more tactics than their ranks
    allow, asked as ``too_many_for`` asks it.

    One query finds which gangs hold any tactics, so a campaign page pays
    the same however many gangs it lists. Only those gangs have their
    roster computed, a fixed number of queries each.
    """
    from django.db.models import Count

    from n26.core.models import Campaign, GangTactic

    if campaign.status != Campaign.Status.PRE_CAMPAIGN or not gangs:
        return set()
    by_pk = {gang.pk: gang for gang in gangs}
    holding = (
        GangTactic.objects.filter(gang_id__in=by_pk, archived=False, bonus=False)
        .values("gang_id")
        .annotate(held=Count("pk"))
    )
    return {
        row["gang_id"]
        for row in holding
        if allowance(by_pk[row["gang_id"]]).over_by > 0
    }


def too_many_tactics_sentence(gang):
    """What the campaign warnings say about a gang over its allowance."""
    room = allowance(gang)
    return (
        f"{gang.name} has {room.held} Gang Tactic{'' if room.held == 1 else 's'}. "
        f"Its Leader and Champions allow {room.available}."
    )


def _rolled_note(table, landed, rolls):
    """What the log keeps: the tactic, and the rolls that found it."""
    said = f"{landed.label} ({table.name}, rolled {rolls[-1]}"
    if len(rolls) > 1:
        again = ", ".join(str(roll) for roll in rolls[:-1])
        said += f" after re-rolling {again}"
    return said + ")"


def _suggested_tactics_notes():
    """The local tactics notes file's timing and effect, by table and
    tactic name, each folded (``_folded``). Empty where no file is named
    or it cannot be read."""
    path = os.environ.get("N26_TACTICS_NOTES", "")
    if not path:
        return {}
    try:
        with open(path, newline="", encoding="utf-8") as handle:
            return {
                (_folded(row["table"]), _folded(row["name"])): (
                    row["timing"],
                    row["effect"],
                )
                for row in csv.DictReader(handle)
            }
    except OSError, KeyError:
        return {}


#: Curly quotes and apostrophes, and what they are matched as.
_STRAIGHT = str.maketrans({"“": '"', "”": '"', "‘": "'", "’": "'"})


def _folded(name):
    """A name as a lookup matches it: quotes straightened, case ignored."""
    return name.translate(_STRAIGHT).casefold().strip()
