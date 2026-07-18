"""Edit-fighter-equipment-upgrade form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_assign_upgrade_edit.html")
def list_fighter_assign_upgrade_edit(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    form_obj = context["form"]
    request = context["request"]
    equipment = assign.content_equipment

    body: Node = form(
        action=reverse(context["action_url"], args=[lst.id, fighter.id, assign.id]),
        method="post",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=context.get("full_back_url", ""), class_="btn btn-link")["Cancel"],
        ],
    ]
    content = fragment[
        back_link(context),
        PageShell(
            h1(class_="h3")[
                equipment.upgrade_stack_name_display,
                ": ",
                equipment.name,
                " for ",
                fighter.fully_qualified_name,
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    title = (
        f"{equipment.upgrade_stack_name_display} - {equipment.name} "
        f"- {fighter.fully_qualified_name} - {lst.name}"
    )
    return Page(title=title, content=content)
