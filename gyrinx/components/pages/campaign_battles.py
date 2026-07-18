"""Campaign battles list page component (view all battles in a campaign)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i
from ._shared import back_link


@register_page("core/campaign/campaign_battles.html")
def campaign_battles(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    battles = context["battles"]
    show_archived = context["show_archived"]
    archived_count = context["archived_count"]
    request = context["request"]

    heading = "Archived battles" if show_archived else "Battles"

    if show_archived:
        toggle_link: Node = a(
            href=reverse("core:campaign-battles", args=[campaign.id]),
            class_="fs-7 linked ms-md-auto",
        )["← Active battles"]
    elif archived_count:
        toggle_link = a(
            href=reverse("core:campaign-battles", args=[campaign.id]) + "?archived=1",
            class_="fs-7 linked ms-md-auto",
        )[f"View {archived_count} archived →"]
    else:
        toggle_link = None

    if battles:
        body: Node = div(class_="list-group list-group-flush")[
            tuple(
                raw(
                    render_to_string(
                        "core/includes/battle_summary_card.html",
                        {"battle": battle},
                        request=request,
                    )
                )
                for battle in battles
            )
        ]
    else:
        body = div(class_="border rounded p-2")[
            i(class_="bi-info-circle"),
            "No archived battles in this Campaign."
            if show_archived
            else "No battles have been recorded in this Campaign yet.",
        ]

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        div(class_="col-lg-12 px-0 vstack gap-4")[
            div(class_="vstack gap-0 mb-2")[
                div(class_="hstack gap-2 mb-2 align-items-start align-items-md-center")[
                    div(
                        class_="d-flex flex-column flex-md-row flex-grow-1 "
                        "align-items-start align-items-md-center gap-2"
                    )[
                        h1(class_="h3 mb-0")[heading],
                        toggle_link,
                    ]
                ],
                div(class_="text-secondary")[campaign.name],
            ],
            body,
        ],
    ]

    return Page(title=f"{heading} - {campaign.name}", content=content)
