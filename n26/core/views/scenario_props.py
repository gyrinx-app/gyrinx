"""Scenario choices for a compact, optional preview on battle creation."""

from django.urls import reverse

from n26.core.scenarios import parse, rolls_of
from n26.library.scenario_tables import (
    SIDE_JOB_KEYS,
    SIDE_JOB_LIMIT,
    load_catalogue,
)


def _entry(entry):
    return {
        "roll": entry.roll,
        "name": entry.label,
        "text": entry.plain,
        "parts": [[words, bold] for words, bold in entry.parts()],
        "image": entry.image_url,
        "imageAlt": entry.diagram_alt,
    }


def battle_scenario_props(mapping, catalogue=None):
    catalogue = catalogue or load_catalogue()
    found, wrong = parse(mapping, catalogue)
    if not wrong:
        mapping = rolls_of(found)
    keys = [table.key for table in catalogue.tables] + list(SIDE_JOB_KEYS)
    return {
        "rollUrl": reverse("n26-generate-scenario"),
        "rolls": {key: str(mapping.get(key, "") or "") for key in keys},
        "tables": [
            {
                "key": table.key,
                "name": table.name,
                "entries": [_entry(entry) for entry in table.entries],
            }
            for table in catalogue.tables
        ],
        "sideJobKeys": list(SIDE_JOB_KEYS),
        "sideJobLimit": SIDE_JOB_LIMIT,
        "referencedSideJobSets": [
            {
                "key": each.key,
                "name": each.name,
                "label": each.label,
                "entries": [_entry(entry) for entry in each.entries],
            }
            for each in {
                result.table.side_job_set.key: result.table.side_job_set
                for result in found
                if result.table.side_job_set
            }.values()
        ],
        "sideJobSets": [
            {
                "key": found.key,
                "name": found.name,
                "label": found.label,
                "entries": [_entry(entry) for entry in found.entries],
            }
            for found in catalogue.side_job_sets
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
            for found in form.catalogue.side_job_sets
        ],
        "sidePicks": form.side_job_picks(),
        "errors": {key: list(errors) for key, errors in form.errors.items()},
    }
