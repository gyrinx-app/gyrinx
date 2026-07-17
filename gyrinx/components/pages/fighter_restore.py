"""Fighter restore-confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, i, li, p, strong, ul
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_restore_confirm.html")
def list_fighter_restore_confirm(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    fighter_cost = context.get("fighter_cost")

    alert = None
    if lst.is_campaign_mode:
        alert = Alert(
            strong["Note:"],
            f" Restoring this fighter will increase your gang rating by {fighter_cost}¢.",
            variant="primary",
            class_="mb-0",
        )

    content = fragment[
        back_link(context, text="Archived Fighters"),
        PageShell(
            h1(class_="h3")[f"Restore Fighter: {fighter.fully_qualified_name}"],
            form(
                action=reverse("core:list-fighter-restore", args=[lst.id, fighter.id]),
                method="post",
            )[
                CsrfInput(context["request"]),
                p["Are you sure you want to restore ", strong[fighter.name], "?"],
                p["This will:"],
                ul[
                    li["Return them to the active gang roster"],
                    li[f"Add {fighter_cost}¢ back to your gang rating"],
                ],
                alert,
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-success")[
                        i(class_="bi-arrow-counterclockwise"), " Restore Fighter"
                    ],
                    cancel_link(
                        context,
                        url=reverse("core:list-archived-fighters", args=[lst.id]),
                    ),
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Restore Fighter - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
