"""Sheet names and descriptions shared by uploads, models and the planner.

Defined separately from ingest.py to avoid a circular import with content models.
"""

#: (Planner argument, display name, description), in dependency order.
INGEST_SHEETS = [
    (
        "equipment",
        "Equipment",
        "Weapons, wargear and accessories, with their categories and prices.",
    ),
    ("weapon_profiles", "Weapon profiles", "Weapon statlines and traits."),
    (
        "equipment_lists",
        "Equipment lists",
        "Equipment lists, with one entry per line and any list-specific prices.",
    ),
    (
        "profiles",
        "All Profiles",
        "Fighter profiles, including categories, statlines, starting equipment and equipment lists.",
    ),
]

#: The planner's names, in planning order.
SHEET_NAMES = [name for name, _label, _held in INGEST_SHEETS]

#: The sheets as a model field states them.
SHEET_CHOICES = [(name, label) for name, label, _held in INGEST_SHEETS]

#: A sheet's own name, by the planner's name for it.
SHEET_LABELS = dict(SHEET_CHOICES)
