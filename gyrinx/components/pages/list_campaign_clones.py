"""Campaign-versions (clones) list page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from .. import bridge
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, p, span, table, tbody, td, th, thead, tr
from ._shared import back_link


def _status_cell(campaign: Any, request: Any) -> Node:
    """Port of the ``{% include "core/campaign/includes/status.html" %}`` cell."""
    return raw(
        render_to_string(
            "core/campaign/includes/status.html",
            {"campaign": campaign},
            request=request,
        )
    )


@register_page("core/list_campaign_clones.html")
def list_campaign_clones(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]
    campaign_clones = context["campaign_clones"]

    list_url = reverse("core:list", args=[lst.id])

    if campaign_clones:
        rows: list[Node] = []
        for clone in campaign_clones:
            rows.append(
                tr[
                    td[
                        a(href=reverse("core:list", args=[clone.id]), class_="linked")[
                            bridge.list_with_theme(clone)
                        ]
                    ],
                    td[
                        a(
                            href=reverse("core:campaign", args=[clone.campaign.id]),
                            class_="linked",
                        )[clone.campaign.name]
                        if clone.campaign
                        else span(class_="text-secondary")["No campaign"]
                    ],
                    td[
                        a(
                            href=reverse(
                                "core:user", args=[clone.campaign.owner.username]
                            ),
                            class_="linked",
                        )[clone.campaign.owner.username]
                        if clone.campaign
                        else span(class_="text-secondary")["-"]
                    ],
                    td[
                        _status_cell(clone.campaign, request)
                        if clone.campaign
                        else span(class_="text-secondary")["-"]
                    ],
                ]
            )
        body: Node = div(class_="table-responsive")[
            table(class_="table")[
                thead[
                    tr[
                        th["Name"],
                        th["Campaign"],
                        th["Campaign Owner"],
                        th["Status"],
                    ]
                ],
                tbody[tuple(rows)],
            ]
        ]
    else:
        body = p(class_="text-secondary")["This list has no campaign versions."]

    content = fragment[
        back_link(context, url=list_url, text="Back to List"),
        div(class_="col-12 col-md-8 col-lg-6 px-0")[
            h1(class_="h3")["Campaign Versions"],
            p(class_="text-secondary")[
                "All campaign versions of ",
                a(href=list_url, class_="linked")[lst.name],
            ],
            body,
        ],
    ]
    return Page(title=f"Campaign Versions of {lst.name}", content=content)
