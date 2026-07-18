"""List-fighter default-assignment disable confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_assign_disable.html")
def list_fighter_assign_disable(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    action_url = context["action_url"]
    back_url = context["back_url"]

    full_back_url = reverse(back_url, args=[lst.id, fighter.id])

    content = fragment[
        back_link(context, url=full_back_url),
        PageShell(
            h1(class_="h3")[
                f"Delete default assignment from {fighter.fully_qualified_name}"
            ],
            form(
                action=reverse(action_url, args=[lst.id, fighter.id, assign.id]),
                method="post",
            )[
                CsrfInput(context["request"]),
                p[
                    "Are you sure you want to delete the default "
                    f"{assign.equipment.name} assignment from {fighter.name}?"
                ],
                div(class_="mt-3")[
                    input_(type="hidden", name="remove", value="1"),
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    a(href=full_back_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Delete - {assign.equipment.name} - "
            f"{fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
