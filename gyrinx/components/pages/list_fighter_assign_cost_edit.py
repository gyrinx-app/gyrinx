"""Edit equipment-assignment cost form page component."""

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


@register_page("core/list_fighter_assign_cost_edit.html")
def edit_list_fighter_assign_cost(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    form_obj = context["form"]
    request = context["request"]
    action_url = context["action_url"]
    back_url = context["back_url"]

    equipment_name = assign.content_equipment.name

    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {**context, "list": lst, "link_list": "true"},
            request=request,
        )
    )

    body = form(
        action=reverse(action_url, args=[lst.id, fighter.id, assign.id]),
        method="post",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(
                href=reverse(back_url, args=[lst.id, fighter.id]),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        header,
        PageShell(
            h1(class_="h3")[
                f"Edit {equipment_name} cost for {fighter.fully_qualified_name}"
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Cost - {equipment_name} - {fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
