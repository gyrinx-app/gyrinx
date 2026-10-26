"""The Gang Tactics tables as the standard seed writes them.

Each table is an ordinary library roll table, built from the same parts
as the Lasting Injury table (``recipes.md``): one slot type, ``Gang
Tactic``, shared by every table; one pickable per tactic; one picklist per
table with the tactic's band of rolls; and a hidden gang-held slot naming
that picklist. A modifier on a gang type gives its gangs the slot, and
the slot is what says a gang may roll on the table. The universal table's
modifier is attached to every standard gang type; a House's own table is
attached to that House alone. ``n26.core.tactics`` reads the tables from
the library, so staff add a new gang's table on the authoring pages
without any change here.

Only names, rolls and where each tactic is printed live here. What a
tactic's timing and effect say is rules text, which this edition does
not store (``n26/AGENTS.md``). The reference goes in each pickable's
summary, which a card prints when it has no rules text to show.
"""

from dataclasses import dataclass

#: The slot type every Gang Tactics table shares. Core finds the tables by
#: it, so renaming it here without renaming the row loses every table.
SLOT_TYPE = "Gang Tactic"
SLOT_TYPE_PLURAL = "Gang Tactics"

#: Game terms of several words that the tactics' rules text uses. Each is
#: one keyword, so its small words are drawn as part of it.
KEYWORD_PHRASES = ("Out of Action", "Out of Ammo")


@dataclass(frozen=True)
class SeedTable:
    """One table to seed. ``gang_types`` names the standard gang types it
    is given to; empty gives it to every one. ``rows`` are
    ``(lowest roll, highest roll, name)``."""

    name: str
    dice: str
    reference: str
    rows: tuple[tuple[int, int, str], ...]
    gang_types: tuple[str, ...] = ()

    @property
    def slot_name(self):
        return f"{SLOT_TYPE_PLURAL}: {self.name}"

    @property
    def modifier_name(self):
        return f"Gang Tactics: {self.name} table"


def _pair(tens, units, name):
    """A D66 band of two neighbouring results, such as 11-12."""
    low = 10 * tens + units
    return (low, low + 1, name)


UNIVERSAL = SeedTable(
    name="Universal",
    dice="d66",
    reference="Page 148/149 - N26 Core Rulebook",
    rows=(
        _pair(1, 1, "Point-blank Shot"),
        _pair(1, 3, "Hidden Stash"),
        _pair(1, 5, "Suppressing Fire"),
        _pair(2, 1, "Burst of Courage"),
        _pair(2, 3, "Adrenaline Surge"),
        _pair(2, 5, "Desperate Effort"),
        _pair(3, 1, "Grenade Bouquet"),
        _pair(3, 3, "Quick Finish"),
        _pair(3, 5, "Remorseless Killer"),
        _pair(4, 1, "Last Gasp"),
        _pair(4, 3, "Thundering Charge"),
        _pair(4, 5, "Chain Attack"),
        _pair(5, 1, "Opening Volley"),
        _pair(5, 3, "“You!”"),
        _pair(5, 5, "Rapid Healing"),
        _pair(6, 1, "Reckless Attack"),
        _pair(6, 3, "Rapid Fire"),
        _pair(6, 5, "Crossfire"),
    ),
)

ESCHER = SeedTable(
    name="Escher",
    dice="d6",
    reference="Page 42 - Underhive Journal: Escher",
    gang_types=("Escher",),
    rows=(
        (1, 1, "Thrill of the Hunt"),
        (2, 2, "Long Leash"),
        (3, 3, "Chem Queen"),
        (4, 4, "Blade Shield"),
        (5, 5, "Toxic Blood"),
        (6, 6, "Three-Point Landing"),
    ),
)

GOLIATH = SeedTable(
    name="Goliath",
    dice="d6",
    reference="Page 42 - Underhive Journal: Goliath",
    gang_types=("Goliath",),
    rows=(
        (1, 1, "And Stay Down!"),
        (2, 2, "Crunch Time"),
        (3, 3, "Forgeborn"),
        (4, 4, "“Get ’Em!”"),
        (5, 5, "Force of Habit"),
        (6, 6, "Ironhide"),
    ),
)

SEED_TABLES = (UNIVERSAL, ESCHER, GOLIATH)
