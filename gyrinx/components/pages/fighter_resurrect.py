"""Fighter resurrect confirm page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, input_, li, p, strong, ul
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_resurrect.html")
def list_fighter_resurrect(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    target_state = context["target_state"]
    target_state_display = context["target_state_display"]
    reason = context["reason"]

    if target_state == "active":
        roster_li = li["Return them to the gang roster"]
    else:
        roster_li = li[f"Return them to the gang roster, in {target_state_display}"]

    content: Node = fragment[
        back_link(context, text=lst.name),
        PageShell(
            h1(class_="h3")[f"Resurrect Fighter: {fighter.fully_qualified_name}"],
            form(
                action=reverse(
                    "core:list-fighter-resurrect", args=[lst.id, fighter.id]
                ),
                method="post",
            )[
                CsrfInput(context["request"]),
                input_(type="hidden", name="target_state", value=target_state),
                input_(type="hidden", name="reason", value=reason) if reason else None,
                p[
                    "Are you sure you want to bring ",
                    strong[fighter.name],
                    " back from the dead?",
                ],
                p["This will:"],
                ul[
                    roster_li,
                    li["Set their rating back to its original value, minus equipment"],
                ],
                Alert(
                    strong["Note:"],
                    " This will not restore the fighter's equipment - you will need to re-equip them manually from the stash or otherwise.",
                    variant="primary",
                    icon="info-circle",
                    class_="mb-0",
                ),
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-success")[
                        i(class_="bi-heart-pulse"), " Resurrect Fighter"
                    ],
                    a(
                        href=reverse("core:list", args=[lst.id]) + f"#{fighter.id}",
                        class_="btn btn-link",
                    )["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Resurrect Fighter - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
