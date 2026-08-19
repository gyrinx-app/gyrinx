"""The pre-ingest sheets: what they are called, and what each one holds.

One statement of them, imported by everything that has an opinion about a
sheet — the planner's keyword arguments, the pages that offer an upload, and
the column on a held upload. A sheet named in one of those and missing from
another is a file that can be uploaded and never planned, which the upload
would report as a success.

Kept apart from :mod:`n26.library.ingest` so that a model may read it: the
reader imports content models, so a content model importing the reader would
close a circle at import time.
"""

#: ``(what the planner calls it, the sheet's own name, what it holds)``. The
#: two names differ where the spreadsheet's heading is not the planner's word
#: for the sheet — an author looks for the heading.
#:
#: The order is the order they are planned in, and the order the pages offer
#: them in: a later sheet resolves against what an earlier one describes.
INGEST_SHEETS = [
    (
        "equipment",
        "Equipment",
        "The catalogue: one row per thing a gang can buy, with its price.",
    ),
    ("weapon_profiles", "Weapon profiles", "The statlines, and nothing else."),
    (
        "equipment_lists",
        "Equipment lists",
        "A named list per gang, one entry per line.",
    ),
    (
        "profiles",
        "All Profiles",
        "The fighters, each with the heading and category it is hired "
        "under and the title of the equipment list it buys from.",
    ),
    (
        "archetypes",
        "Archetypes",
        "The chosen carriers: each row reaches one rank of one gang — by "
        "subtype, or by naming the fighter — and places its skill sets.",
    ),
]

#: The planner's names, in planning order.
SHEET_NAMES = [name for name, _label, _held in INGEST_SHEETS]

#: The sheets as a model field states them.
SHEET_CHOICES = [(name, label) for name, label, _held in INGEST_SHEETS]

#: A sheet's own name, by the planner's name for it.
SHEET_LABELS = dict(SHEET_CHOICES)
