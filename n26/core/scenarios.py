"""Rolling, checking and describing a scenario from the scenario tables.

A scenario is one entry from each of the tables in
``n26.library.scenario_tables`` that it uses. Only each table's key and
roll are stored, on a battle or in a saved scenario's log note, and the
entry is looked up when the page is drawn.
"""

from dataclasses import dataclass

from n26.library.scenario_tables import TABLES, ScenarioEntry, ScenarioTable


@dataclass(frozen=True)
class ScenarioResult:
    """What one table landed on, for drawing: the table, the roll and its
    entry."""

    table: ScenarioTable
    roll: int
    entry: ScenarioEntry

    @property
    def face(self):
        """The roll as the die component takes it, a string."""
        return str(self.roll)


def roll(keys, rng=None):
    """A D6 roll for each named table, as ``{key: roll}`` in table order.
    ``rng`` is anything with ``randint``, so a test can seed it."""
    from n26.library.models import Dice

    return {found.key: Dice.roll(Dice.D6, rng) for found in TABLES if found.key in keys}


def parse(mapping):
    """The results a mapping of ``{key: roll}`` names, in table order, and
    the tables whose value is not one of their rolls.

    A table the mapping does not name is left out of the scenario, which
    is valid. A table it names with anything but 1 to 6 is an error, so a
    caller refuses the whole scenario rather than quietly dropping a part.
    """
    found, wrong = [], []
    for each in TABLES:
        value = mapping.get(each.key)
        if value in (None, ""):
            continue
        try:
            entry = each.entry(int(value))
        except TypeError, ValueError:
            entry = None
        if entry is None:
            wrong.append(each)
        else:
            found.append(ScenarioResult(table=each, roll=entry.roll, entry=entry))
    return found, wrong


def results(mapping):
    """The results a mapping names, or an empty list if any part is wrong."""
    found, wrong = parse(mapping)
    return [] if wrong else found


def rolls_of(found):
    """``{key: roll}`` for a list of results."""
    return {result.table.key: result.roll for result in found}


def describe(found):
    """A list of results as a sentence says it: each table and roll with
    the entry's name, "Deployment 6 (Chance Encounter)"."""
    return ", ".join(
        f"{result.table.name} {result.roll} ({result.entry.label})" for result in found
    )


# --- Saving a scenario to the campaign's log ---------------------------------
#
# The log stores no sentence, only a note the reader turns into one. A saved
# scenario's note is each table's key and roll, then the name the player
# gave it: "deployment=6,objective=2 Dust Up". Entry names are looked up when
# the log is drawn, so a revised entry reads as it is now, as a battle's
# scenario does.


def history_note(rolls, name):
    """The note a saved scenario's log entry stores."""
    pairs = ",".join(f"{key}={value}" for key, value in rolls.items())
    return f"{pairs} {name}".strip()


def read_history_note(note):
    """``(rolls, name)`` from a saved scenario's note. A note that does not
    parse gives no rolls."""
    pairs, _, name = note.partition(" ")
    rolls = {}
    for pair in pairs.split(","):
        key, _, value = pair.partition("=")
        if key and value:
            rolls[key] = value
    return rolls, name.strip()
