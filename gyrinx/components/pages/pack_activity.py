"""Pack activity history display page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div, h1, h2, p
from ._shared import back_link


@register_page("core/pack/pack_activity.html")
def pack_activity(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    activities = context["activities"]
    request = context["request"]

    if activities:
        activity_items = [
            raw(
                render_to_string(
                    "core/includes/pack_activity_item.html",
                    {"activity": activity},
                    request=request,
                )
            )
            for activity in activities
        ]
        pagination = raw(
            render_to_string(
                "core/includes/pagination.html",
                {
                    "is_paginated": context.get("is_paginated"),
                    "page_obj": context.get("page_obj"),
                    "request": request,
                },
                request=request,
            )
        )
        body: Node = fragment[
            div(class_="list-group list-group-flush")[tuple(activity_items)],
            pagination,
        ]
    else:
        body = p(class_="text-secondary")["No activity yet."]

    content: Node = fragment[
        back_link(context, url=pack.get_absolute_url(), text="Back to Content Pack"),
        div(class_="col-12 col-xl-8 px-0 vstack gap-3")[
            div[
                h1(class_="h3 mb-0")["Activity"],
                h2(class_="h5 text-secondary")[pack.name],
            ],
            body,
        ],
    ]
    return Page(
        title=f"Activity - {pack.name}",
        content=content,
    )
