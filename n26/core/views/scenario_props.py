"""Scenario choices for a compact, optional preview on battle creation."""

from django.templatetags.static import static
from django.urls import reverse

from n26.library.scenario_tables import (
    SIDE_JOB_KEYS,
    SIDE_JOB_LIMIT,
    SIDE_JOB_SETS,
    TABLES,
)


def _entry(entry):
    return {
        "roll": entry.roll,
        "name": entry.label,
        "text": entry.plain,
        "parts": [[words, bold] for words, bold in entry.parts()],
        "image": static(entry.image) if entry.image else "",
    }


def battle_scenario_props(mapping):
    keys = [table.key for table in TABLES] + list(SIDE_JOB_KEYS)
    return {
        "rollUrl": reverse("n26-generate-scenario"),
        "rolls": {key: str(mapping.get(key, "") or "") for key in keys},
        "tables": [
            {
                "key": table.key,
                "name": table.name,
                "entries": [_entry(entry) for entry in table.entries],
            }
            for table in TABLES
        ],
        "sideJobKeys": list(SIDE_JOB_KEYS),
        "sideJobLimit": SIDE_JOB_LIMIT,
        "sideJobSets": [
            {
                "key": found.key,
                "name": found.name,
                "label": found.label,
                "entries": [_entry(entry) for entry in found.entries],
            }
            for found in SIDE_JOB_SETS
        ],
    }
