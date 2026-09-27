"""Signed changes a report makes to stored counters.

A report records, for each counter it changes, the change it makes in
total, keyed by the counter's assignment. The assignment is the pin: a
correction moves the same counter by the difference between the new
entry and the recorded one, so a tally made since (a kill marked on the
model's page, a Reputation point from the arbitrator) stays where it is.

Results can move a counter too, through their own stored effects. That
movement is written when the result is added, not by this module, so it
is shown beside the entered change and counted once.

Nothing here reads the database or knows whose counters they are: the
caller hands over the card's nodes and readings, and gets back one
``CounterChange`` per counter and the errors to show. The gang's
counters use it today; a model's counters can use it the same way.
"""

from dataclasses import dataclass

from n26.library.income import is_income_counter
from n26.library.models import Counter
from n26.library.standard_content import XP_COUNTER

#: The largest change one report may enter for one counter, either way.
#: The same bound the model page's tally route keeps.
LIMIT = 1000


@dataclass(frozen=True)
class CounterChange:
    """One counter's line in a report.

    ``before`` is the reading now, ``manual`` the change this report
    enters in total, ``effect`` what this report's results add, and
    ``after`` where the counter lands. ``recorded`` is what the report
    last applied, so a correction moves the counter by ``manual -
    recorded``.
    """

    assignment_id: str
    name: str
    before: int
    manual: int
    effect: int
    after: int
    recorded: int = 0

    @property
    def delta(self):
        """The entered change still to apply."""
        return self.manual - self.recorded

    @property
    def changes(self):
        return bool(self.manual or self.recorded or self.effect)


@dataclass(frozen=True)
class HeldCounter:
    """A counter a report may change: one stored assignment and its values.

    ``reading`` is what the card shows (the stored value and any
    contributions); ``stored`` is the value a tally moves, which never
    goes below zero.
    """

    assignment: object
    name: str
    reading: int
    stored: int

    @property
    def id(self):
        return str(self.assignment.pk)


def changeable(node):
    """Whether a report may change this node's counter by hand.

    Stored and drawn, and neither XP (which has its own column) nor
    Income (whose reading is the sum of what the gang holds, so a tally
    would be a mistake).
    """
    thing = node.assignable
    return (
        isinstance(thing, Counter)
        and node.assignment is not None
        and not node.broadcast
        and not node.suppressed
        and thing.drawn
        and thing.name.casefold() != XP_COUNTER.casefold()
        and not is_income_counter(thing)
    )


def held_counters(nodes, readings):
    """The counters a report may change, in card order.

    ``readings`` are ``counter_readings`` for the same card, which gives
    one reading per counter node in the same order before any reading of
    a counter that is only contributed to.
    """
    counter_nodes = [node for node in nodes if isinstance(node.assignable, Counter)]
    held = []
    for node, reading in zip(counter_nodes, readings, strict=False):
        if not changeable(node):
            continue
        value = getattr(node.assignment, "counter_value", None)
        held.append(
            HeldCounter(
                assignment=node.assignment,
                name=str(node.assignable),
                reading=reading.value,
                stored=value.value if value else 0,
            )
        )
    return held


def read_changes(raw, errors):
    """Signed whole numbers keyed by assignment id, zeros left out.

    A blank entry counts as no change. Anything else that is not a whole
    number within the limit is reported and counted as no change.
    """
    if not isinstance(raw, dict):
        if raw not in (None, ""):
            errors.append("The counter changes are invalid.")
        return {}
    changes = {}
    for key, value in raw.items():
        text = str(value if value is not None else "").strip()
        if text in ("", "0", "+0", "-0"):
            continue
        try:
            number = int(text)
            if isinstance(value, bool) or not -LIMIT <= number <= LIMIT:
                raise ValueError
        except ValueError:
            errors.append(
                f"Enter a whole number from −{LIMIT:,} to {LIMIT:,} for each counter change."
            )
            continue
        changes[str(key)] = number
    return changes


def plan_changes(held, entered, recorded, effects=None, names=None):
    """Every held counter's line, and why any of them cannot be applied.

    ``entered`` and ``recorded`` are the change this report makes in
    total and the change it last applied, keyed by assignment id.
    ``effects`` is what this report's results move each counter by.
    ``names`` names a recorded counter that is no longer held.

    Returns ``(changes, errors)``. A counter the report changed before
    that has since been removed or moved to another holder cannot be
    corrected here. Leaving it out of
    ``entered`` keeps its recorded change.
    """
    effects = effects or {}
    names = names or {}
    errors = []
    changes = []
    by_id = {counter.id: counter for counter in held}
    for counter in held:
        manual = entered.get(counter.id, 0)
        was = recorded.get(counter.id, 0)
        effect = effects.get(counter.id, 0)
        after = counter.reading + manual - was + effect
        if counter.stored + manual - was + effect < 0:
            errors.append(f"{counter.name} cannot go below 0.")
        changes.append(
            CounterChange(
                assignment_id=counter.id,
                name=counter.name,
                before=counter.reading,
                manual=manual,
                effect=effect,
                after=after,
                recorded=was,
            )
        )
    for key in sorted(set(entered) | set(recorded)):
        # The page draws no row for a counter that has gone, so a report
        # that leaves it out keeps the recorded change. Only a change
        # entered for it is refused.
        was = recorded.get(key, 0)
        if key in by_id or entered.get(key, was) == was:
            continue
        name = names.get(key, "this counter")
        errors.append(
            f"You cannot correct the change to {name}: it was removed or moved "
            f"after this report was applied. Change {name} on the gang page."
        )
    return changes, errors


def entries(changes, entered, recorded):
    """What the report keeps: every entered change, and a recorded change
    for a counter that is no longer held, so a later correction still
    knows what was applied."""
    kept = {change.assignment_id: change.manual for change in changes if change.manual}
    held = {change.assignment_id for change in changes}
    for key, value in recorded.items():
        if key not in held and value:
            kept[key] = entered.get(key, value)
    return kept
