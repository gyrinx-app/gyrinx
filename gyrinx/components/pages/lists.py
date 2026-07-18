"""Lists & Gangs index page component (port of ``core/lists.html``)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import qt, qt_rm

from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, br, div, h1, li, p, ul


def _tab(*, label: str, href: str, active: bool) -> Node:
    return li(class_="nav-item")[
        a(
            class_=["nav-link", {"active": active}],
            aria_current="page" if active else None,
            href=href,
        )[label]
    ]


def _row(context: dict[str, Any], list_obj: Any, request: Any) -> Node:
    # ``list_row.html`` is un-ported; bridge it with the same ``list`` override
    # the legacy ``{% include ... with list=list %}`` passes.
    return raw(
        render_to_string(
            "core/includes/list_row.html",
            {**context, "list": list_obj},
            request=request,
        )
    )


@register_page("core/lists.html")
def lists(context: dict[str, Any]) -> Page:
    request = context["request"]
    lists_qs = context["lists"]
    pinned_lists = context["pinned_lists"]
    current_tab = context.get("current_tab")

    # Filter partial (un-ported) — bridge with the legacy ``with`` overrides.
    filter_include = raw(
        render_to_string(
            "core/includes/lists_filter.html",
            {
                **context,
                "action": reverse("core:lists"),
                "houses": context["houses"],
                "show_sort": True,
            },
            request=request,
        )
    )

    tabs = ul(class_="nav nav-tabs")[
        _tab(
            label="All",
            href="?" + qt_rm(request, "type", "page"),
            active=current_tab == "all",
        ),
        _tab(
            label="Lists",
            href="?" + qt(request, type="list", page=None),
            active=current_tab == "list",
        ),
        _tab(
            label="Campaign Gangs",
            href="?" + qt(request, type="gang", page=None),
            active=current_tab == "gang",
        ),
    ]

    if lists_qs:
        rows: Node = [_row(context, list_obj, request) for list_obj in lists_qs]
    else:
        archived = request.GET.get("archived") == "1"
        rows = div(class_="py-2")[
            "No archived lists found. Note: You can only view your own archived lists."
            if archived
            else "No lists available."
        ]

    pagination = raw(
        render_to_string(
            "core/includes/pagination.html",
            dict(context),
            request=request,
        )
    )

    main_col = div(class_="col-12 col-xl-8 order-2 order-xl-1 vstack gap-4")[
        tabs,
        div(class_="vstack gap-4")[rows, pagination],
    ]

    sidebar: Node = None
    if pinned_lists:
        sidebar = div(class_="col-12 col-xl-4 order-1 order-xl-2 vstack gap-4")[
            div(class_="caps-label")["Pinned"],
            [_row(context, list_obj, request) for list_obj in pinned_lists],
        ]

    content = div(class_="col-lg-12 px-0 vstack gap-4")[
        div[
            h1(class_="mb-1")["Lists & Gangs"],
            p(class_="fs-5 col-12 col-md-6 mb-0")[
                "Browse and manage your Lists & Campaign Gangs.",
                br,
                a(href=reverse("core:lists-new"), class_="linked")["Create a new List"],
                ".",
            ],
        ],
        div(class_="grid")[filter_include],
        div(class_="row g-4")[main_col, sidebar],
    ]

    return Page(title="Lists", content=content)
