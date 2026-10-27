"""Scenario choices for a compact, optional preview on battle creation."""

from django.templatetags.static import static
from django.urls import reverse

from n26.library.scenario_tables import TABLES


def battle_scenario_props(mapping):
    return {
        "rollUrl": reverse("n26-generate-scenario"),
        "rolls": {table.key: str(mapping.get(table.key, "")) for table in TABLES},
        "tables": [
            {
                "key": table.key,
                "name": table.name,
                "entries": [
                    {
                        "roll": entry.roll,
                        "name": entry.label,
                        "text": entry.text,
                        "image": static(entry.image) if entry.image else "",
                    }
                    for entry in table.entries
                ],
            }
            for table in TABLES
        ],
    }
