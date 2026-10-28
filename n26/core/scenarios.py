"""Rolling, checking and describing a scenario from the scenario tables.

A scenario is one entry from each of the tables in
``n26.library.scenario_tables`` that it uses, then any side jobs. Only
each table's key and roll are stored, on a battle or in a saved
scenario's log note, and the entry is looked up when the page is drawn.

A side job is stored under its place, ``side_job`` then ``side_job_2``
and on, as its set and roll: ``escher-3``. A bare roll, as battles saved
before there were sets have, is from the General set.
"""

from dataclasses import dataclass

from n26.library.scenario_tables import (
    GENERAL_SIDE_JOBS,
    SIDE_JOB_KEYS,
    TABLES,
    ScenarioEntry,
    ScenarioTable,
    side_job_set,
    side_job_table,
)


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

    @property
    def heading(self):
        """The table as a result names it: "Deployment", or "Side job 2
        (Escher)" with the set a side job came from."""
        found = self.table.side_job_set
        return f"{self.table.name} ({found.name})" if found else self.table.name

    @property
    def value(self):
        """What a link or a stored battle holds for this result: the roll,
        or a side job's set and roll, "escher-3"."""
        found = self.table.side_job_set
        return f"{found.key}-{self.roll}" if found else self.roll


def roll(keys, rng=None):
    """A D6 roll for each named table, as ``{key: roll}`` in table order.
    ``rng`` is anything with ``randint``, so a test can seed it."""
    from n26.library.models import Dice

    return {found.key: Dice.roll(Dice.D6, rng) for found in TABLES if found.key in keys}


def roll_side_jobs(picks, rng=None):
    """Side job values, ``["escher-3", ...]``, for a list of picks, each
    a set and a roll, or a set and None to roll a D6.

    A rolled side job is never one the scenario already has from the same
    set, so it rolls again; a set whose every job is taken lets a repeat
    through. Named picks are the reader's choice and are kept as given.
    """
    from n26.library.models import Dice

    taken = {(found.key, chosen) for found, chosen in picks if chosen}
    values = []
    for found, chosen in picks:
        if not chosen:
            free = [e.roll for e in found.entries if (found.key, e.roll) not in taken]
            chosen = Dice.roll(Dice.D6, rng)
            while free and chosen not in free:
                chosen = Dice.roll(Dice.D6, rng)
            taken.add((found.key, chosen))
        values.append(f"{found.key}-{chosen}")
    return values


def read_side_job(value):
    """``(set, entry)`` for a stored side job value, "escher-3", or a bare
    roll from the General set. Either is None for a value that is not a
    side job."""
    if type(value) is int:
        return GENERAL_SIDE_JOBS, GENERAL_SIDE_JOBS.entry(value)
    if not isinstance(value, str):
        return None, None
    set_key, dash, roll_text = value.rpartition("-")
    found = side_job_set(set_key) if dash else GENERAL_SIDE_JOBS
    if found is None or roll_text not in {str(e.roll) for e in found.entries}:
        return found, None
    return found, found.entry(int(roll_text))


def parse(mapping):
    """The results a mapping of ``{key: roll}`` names, in table order, and
    the tables whose value is not one of their rolls.

    A table the mapping does not name is left out of the scenario, which
    is valid. A table it names with anything but 1 to 6 is an error, so a
    caller refuses the whole scenario rather than quietly dropping a part.
    Side jobs come last, numbered in order from 1 whatever their keys.
    """
    found, wrong = [], []
    for each in TABLES:
        value = mapping.get(each.key)
        if value in (None, ""):
            continue
        if type(value) is int:
            entry = each.entry(value)
        elif isinstance(value, str) and value in {
            str(entry.roll) for entry in each.entries
        }:
            entry = each.entry(int(value))
        else:
            entry = None
        if entry is None:
            wrong.append(each)
        else:
            found.append(ScenarioResult(table=each, roll=entry.roll, entry=entry))
    place = 0
    for key in SIDE_JOB_KEYS:
        value = mapping.get(key)
        if value in (None, ""):
            continue
        place += 1
        side_jobs, entry = read_side_job(value)
        each = side_job_table(place, side_jobs or GENERAL_SIDE_JOBS)
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
    """``{key: value}`` for a list of results: each table's roll, and each
    side job's set and roll."""
    return {result.table.key: result.value for result in found}


def describe(found):
    """A list of results as a sentence says it: each table and roll with
    the entry's name, "Deployment 6 (Chance Encounter)", and each side job
    with its set, "Side job 1: Escher 3 (Hunt Together)"."""

    def said(result):
        found = result.table.side_job_set
        roll = f"{found.name} {result.roll}" if found else result.roll
        sep = ":" if found else ""
        return f"{result.table.name}{sep} {roll} ({result.entry.label})"

    return ", ".join(said(result) for result in found)


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
