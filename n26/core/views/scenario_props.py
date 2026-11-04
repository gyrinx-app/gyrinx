"""Scenario choices for a compact, optional preview on battle creation."""

from django.templatetags.static import static
from django.urls import reverse

from n26.core.scenarios import parse, rolls_of
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
    found, wrong = parse(mapping)
    if not wrong:
        mapping = rolls_of(found)
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


def scenario_picks_props(form):
    form.is_valid()
    return {
        "tables": [
            {
                "key": table.key,
                "label": table.name,
                "choices": list(form.fields[form.pick_name(table)].choices),
            }
            for table in form.tables
        ],
        "sideJobKeys": list(SIDE_JOB_KEYS),
        "sideJobLimit": SIDE_JOB_LIMIT,
        "sideJobSets": [
            {
                "key": found.key,
                "name": found.name,
                "label": found.label,
                "entries": [
                    {"roll": entry.roll, "name": entry.label} for entry in found.entries
                ],
            }
            for found in SIDE_JOB_SETS
        ],
        "sidePicks": form.side_job_picks(),
        "errors": {key: list(errors) for key, errors in form.errors.items()},
    }
