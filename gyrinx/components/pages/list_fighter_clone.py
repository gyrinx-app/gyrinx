"""List fighter clone form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_clone.html")
def list_fighter_clone(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    form_obj = context["form"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-edit",
        },
        request=request,
    )

    body = form(
        action=reverse("core:list-fighter-clone", args=[lst.id, fighter.id]),
        method="post",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Clone"],
            a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[
                f"Clone: {fighter.name} - {fighter.content_fighter.name()}"
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Clone - {fighter.name} - {fighter.content_fighter.name()} - {lst.name}",
        content=content,
    )
