"""Campaigns index page component (list + filter + pinned sidebar)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, br, div, h1, p


def _campaign_row(campaign: Any, request: Any) -> Node:
    # Un-ported row partial (nested status/badge includes) — bridge it through the
    # DjangoTemplates loader with the same ``campaign`` override the legacy
    # ``{% include ... with campaign=campaign %}`` passes.
    return raw(
        render_to_string(
            "core/campaign/includes/campaign_row.html",
            {"campaign": campaign},
            request=request,
        )
    )


@register_page("core/campaign/campaigns.html")
def campaigns(context: dict[str, Any]) -> Page:
    request = context["request"]
    campaign_list = list(context.get("campaigns", []))
    pinned = list(context.get("pinned_campaigns") or [])

    # Intro paragraph — "Create a new Campaign" link only for signed-in users.
    intro_children: list[Node] = ["Browse and manage campaigns."]
    if request.user.is_authenticated:
        intro_children += [
            br,
            a(href=reverse("core:campaigns-new"), class_="linked")[
                "Create a new Campaign"
            ],
            ".",
        ]

    # Filter partial (custom template tags, status checkboxes, sort dropdown).
    filter_bar = raw(
        render_to_string(
            "core/includes/campaigns_filter.html",
            {
                "action": reverse("core:campaigns"),
                "status_choices": context.get("status_choices"),
                "show_sort": True,
                "current_sort": context.get("current_sort"),
            },
            request=request,
        )
    )

    # Pagination partial (reads page_obj / is_paginated from context).
    pagination = raw(
        render_to_string(
            "core/includes/pagination.html",
            {
                "is_paginated": context.get("is_paginated"),
                "page_obj": context.get("page_obj"),
            },
            request=request,
        )
    )

    if campaign_list:
        rows: Node = tuple(_campaign_row(c, request) for c in campaign_list)
    else:
        rows = div(class_="py-2")["No campaigns available."]

    main_column = div(class_="col-12 col-xl-8 order-2 order-xl-1 vstack gap-4")[
        rows,
        pagination,
    ]

    pinned_column = (
        div(class_="col-12 col-xl-4 order-1 order-xl-2 vstack gap-4")[
            div(class_="caps-label")["Pinned"],
            tuple(_campaign_row(c, request) for c in pinned),
        ]
        if pinned
        else None
    )

    content = div(class_="col-lg-12 px-0 vstack gap-4")[
        div[
            h1(class_="mb-1")["Campaigns"],
            p(class_="fs-5 col-12 col-md-6 mb-0")[intro_children],
        ],
        div(class_="grid")[filter_bar],
        div(class_="row g-4")[main_column, pinned_column],
    ]
    return Page(title="Campaigns", content=content)
