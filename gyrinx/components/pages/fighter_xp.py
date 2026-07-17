"""Fighter XP edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, li, span, ul

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_xp_edit.html")
def edit_list_fighter_xp(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-xp-edit",
        },
        request=request,
    )

    body = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="hstack gap-2 mt-3 align-items-center")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[f"Edit XP for {fighter.name}"],
            ul(class_="fs-5 mb-3 list-group list-group-flush")[
                li(class_="list-group-item")[
                    span(class_="badge text-bg-primary")[f"{fighter.xp_current} XP"],
                    " Current",
                ],
                li(class_="list-group-item")[
                    span(class_="badge text-bg-secondary")[f"{fighter.xp_total} XP"],
                    " Total",
                ],
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"XP - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
