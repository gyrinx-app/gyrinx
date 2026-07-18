"""Enable-default-assignment-modification confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_assign_convert.html")
def list_fighter_assign_convert(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    action_url = context["action_url"]
    back_url = context["back_url"]

    full_back_url = reverse(back_url, args=[lst.id, fighter.id])
    equipment_name = assign.equipment.name

    content: Node = fragment[
        back_link(context, url=full_back_url),
        PageShell(
            h1(class_="h3")[f"Enable modification of the {equipment_name}"],
            form(
                action=reverse(action_url, args=[lst.id, fighter.id, assign.id]),
                method="post",
            )[
                CsrfInput(context["request"]),
                p[
                    f"Are you sure you want to enable modification of this {equipment_name}?"
                ],
                Alert(
                    "Watch out! If you later delete this equipment, the default assignment will ",
                    strong["not"],
                    " be restored.",
                    variant="warning",
                    class_="mb-0",
                ),
                div(class_="mt-3")[
                    input_(type="hidden", name="convert", value="1"),
                    button(type="submit", class_="btn btn-success")["Enable"],
                    a(href=full_back_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Enable default assignment modification - {equipment_name}"
            f" - {fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
