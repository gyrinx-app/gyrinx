"""Generate and describe scenarios from stored table keys and rolls.

Store each selected table's key and roll on battles or in saved scenario
notes, then resolve entries for display. Side jobs use side_job, side_job_2
and subsequent positions with set-qualified rolls such as escher-3.
Unqualified rolls use the General set.
"""

from dataclasses import dataclass

from n26.library.scenario_tables import (
    PRIMARY_KEYS,
    SIDE_JOB_KEYS,
    ScenarioEntry,
    ScenarioTable,
    load_catalogue,
    side_job_set,
    side_job_table,
)

SCENARIO_PICK_KEYS = (
    *(f"{key}_pick" for key in PRIMARY_KEYS),
    *(f"{key}_{suffix}" for key in SIDE_JOB_KEYS for suffix in ("pick", "set")),
    "side_jobs",
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


def roll(keys, rng=None, *, catalogue=None):
    """A D6 roll for each named table, as ``{key: roll}`` in table order.
    ``rng`` is anything with ``randint``, so a test can seed it."""
    from n26.library.models import Dice

    return {
        found.key: Dice.roll(Dice.D6, rng)
        for found in (catalogue or load_catalogue()).tables
        if found.key in keys
    }


def roll_side_jobs(picks, rng=None):
    """Resolve set-and-result selections to values such as escher-3.

    A None result rolls D6, avoiding jobs already chosen from that set unless
    all jobs are taken. Preserve explicitly selected results, including repeats.
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


def reroll_side_job(found, key, set_key, rng=None, *, catalogue=None):
    """The rolls of the scenario ``found`` with its side job under ``key``
    rolled again on the set ``set_key``, keeping everything else.

    The new job is never one the scenario already has from that set,
    including the job it replaces, unless the set has no other. None when
    the scenario has no side job under ``key`` or there is no such set.
    """
    chosen = side_job_set(set_key, catalogue)
    side_jobs = [(r.table.side_job_set, r.roll) for r in found if r.table.side_job_set]
    keys = {r.table.key for r in found if r.table.side_job_set}
    if chosen is None or not chosen.available or key not in keys:
        return None
    value = roll_side_jobs([*side_jobs, (chosen, None)], rng)[-1]
    return {**rolls_of(found), key: value}


def read_side_job(value, catalogue=None):
    """``(set, entry)`` for a stored side job value, "escher-3", or a bare
    roll from the General set. Either is None for a value that is not a
    side job."""
    catalogue = catalogue or load_catalogue()
    general = catalogue.side_job_set("general")
    if type(value) is int:
        return general, general.entry(value) if general else None
    if not isinstance(value, str):
        return None, None
    set_key, dash, roll_text = value.rpartition("-")
    found = catalogue.side_job_set(set_key) if dash else general
    if found is None or roll_text not in {str(e.roll) for e in found.entries}:
        return found, None
    return found, found.entry(int(roll_text))


def parse(mapping, catalogue=None):
    """The results a mapping of ``{key: roll}`` names, in table order, and
    the tables whose value is not one of their rolls.

    A table the mapping does not name is left out of the scenario, which
    is valid. A table it names with anything but 1 to 6 is an error, so a
    caller refuses the whole scenario rather than quietly dropping a part.
    Side jobs come last, numbered in order from 1 whatever their keys.
    """
    if not any(
        mapping.get(key) not in (None, "") for key in (*PRIMARY_KEYS, *SIDE_JOB_KEYS)
    ):
        return [], []
    catalogue = catalogue or load_catalogue()
    found, wrong = [], []
    for key in PRIMARY_KEYS:
        each = catalogue.table(key) or ScenarioTable(
            key=key, name=key.capitalize(), entries=()
        )
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
        side_jobs, entry = read_side_job(value, catalogue)
        each = side_job_table(
            place,
            side_jobs
            or catalogue.side_job_set("general")
            or ScenarioTable(key="side_job", name="Side jobs", entries=()),
        )
        if entry is None:
            wrong.append(each)
        else:
            found.append(ScenarioResult(table=each, roll=entry.roll, entry=entry))
    return found, wrong


def results(mapping, catalogue=None):
    """The results a mapping names, or an empty list if any part is wrong."""
    found, wrong = parse(mapping, catalogue)
    return [] if wrong else found


def rolls_of(found):
    """``{key: value}`` for a list of results: each table's roll, and each
    side job's set and roll."""
    return {result.table.key: result.value for result in found}


def describe(found):
    """A list of results as a sentence says it: each table and roll with
    the entry's name, "Deployment 6 (Chance Encounter)", and each side job
    with its set, "Side job 1: Escher 3 (Hunt Together)"."""

    def describe_result(result):
        found = result.table.side_job_set
        roll = f"{found.name} {result.roll}" if found else result.roll
        sep = ":" if found else ""
        return f"{result.table.name}{sep} {roll} ({result.entry.label})"

    return ", ".join(describe_result(result) for result in found)


# Saved scenario notes contain table keys and rolls followed by the name,
# such as deployment=6,objective=2 Dust Up. Resolve entry names at display
# time, matching battle scenario rendering.


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
