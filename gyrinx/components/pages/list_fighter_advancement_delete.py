"""Fighter advancement delete confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, dd, div, dl, dt, form, h1, i, li, p, strong, ul
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_advancement_delete.html")
def list_fighter_advancement_delete(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    advancement = context["advancement"]
    request = context["request"]

    advancements_url = reverse(
        "core:list-fighter-advancements", args=[lst.id, fighter.id]
    )

    equipment_note: Node = None
    if advancement.advancement_type == advancement.ADVANCEMENT_EQUIPMENT:
        equipment_note = div(
            class_="alert alert-warning alert-icon mb-0", role="alert"
        )[
            i(class_="bi-exclamation-triangle"),
            div[
                strong["Note:"],
                " Equipment added by this advancement must be removed manually.",
            ],
        ]

    content: Node = fragment[
        back_link(context, url=advancements_url, text="Advancements"),
        PageShell(
            h1(class_="h3")[f"Remove Advancement: {fighter.name}"],
            div(class_="border rounded p-3 pb-0 mb-3")[
                dl(class_="mb-0")[
                    dt["Advancement"],
                    dd[advancement.display_description],
                    dt["To be restored/reverted"],
                    dd[
                        ul[
                            li[f"{advancement.xp_cost} XP spend"],
                            li[f"{advancement.cost_increase}¢ rating increase"],
                        ]
                    ],
                ]
            ],
            equipment_note,
            form(
                action=reverse(
                    "core:list-fighter-advancement-delete",
                    args=[lst.id, fighter.id, advancement.id],
                ),
                method="post",
            )[
                CsrfInput(request),
                p["Are you sure you want to remove this advancement?"],
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-danger")[
                        "Remove Advancement"
                    ],
                    a(href=advancements_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove Advancement - {fighter.name} - {lst.name}",
        content=content,
    )
