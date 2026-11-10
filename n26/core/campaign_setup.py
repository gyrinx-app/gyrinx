"""Campaign setup guidance derived from the dashboard's already-loaded facts."""

from django.urls import reverse
from django.utils.html import strip_tags

from n26.library.territory_table import TERRITORY


def setup_checklist(campaign, sheet, players, cycles, *, actor):
    if campaign.owner_id != actor.pk or campaign.archived:
        return None
    home = reverse("n26-campaign", args=[campaign.pk])
    items = [
        {
            "label": "Add a description and budget",
            "href": reverse("n26-edit-campaign", args=[campaign.pk]),
            "complete": bool(strip_tags(sheet.summary).strip())
            and sheet.budget is not None,
        },
        {
            "label": "Invite players",
            "href": reverse("n26-campaign-add-player", args=[campaign.pk]),
            "complete": any(
                player.state in {"invited", "accepted"} for player in players
            ),
        },
        {
            "label": "Add gangs",
            "href": reverse("n26-campaign-add-gang", args=[campaign.pk]),
            "complete": bool(sheet.gangs),
        },
    ]
    if cycles is not None:
        items.append(
            {
                "label": "Set up cycles",
                "href": cycles.setup_href or cycles.schedule_href,
                "complete": not bool(cycles.setup_href),
            }
        )
    tables = [
        table for table in sheet.assets if table.label == TERRITORY and table.tables
    ]
    if tables:
        items.append(
            {
                "label": "Roll territories",
                "href": home + "#assets",
                "complete": all(table.entries for table in tables),
            }
        )
    return {
        "storageKey": f"n26:campaign-setup:{actor.pk}:{campaign.pk}",
        "items": items,
    }
