"""Fighter state-edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, span, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_state_edit.html")
def list_fighter_state_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]

    if fighter.is_injured:
        state_class = "text-bg-warning"
    elif fighter.is_dead:
        state_class = "text-bg-danger"
    else:
        state_class = "text-bg-success"

    state_card = div(class_="card")[
        div(class_="card-body")[
            div(class_="d-flex align-items-center justify-content-between")[
                div[
                    strong[f"{fighter.term_singular} State:"],
                    span(class_=["badge", state_class, "ms-2"])[
                        fighter.get_injury_state_display()
                    ],
                ],
            ],
        ],
    ]

    alert = Alert(
        f"Changing {fighter.proximal_demonstrative.lower()}'s state will "
        "automatically log this event to the campaign action log.",
        variant="info",
        class_="mb-0",
    )

    body = form(
        action=reverse("core:list-fighter-state-edit", args=[lst.id, fighter.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(
                href=reverse(
                    "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
                ),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=reverse("core:list", args=[lst.id]), text=lst.name),
        PageShell(
            h1(class_="h3")[f"Update {fighter.term_singular} State: {fighter.name}"],
            state_card,
            alert,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Update {fighter.term_singular} State - {fighter.name} - {lst.name}",
        content=content,
    )
