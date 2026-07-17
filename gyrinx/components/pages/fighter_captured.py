"""Fighter "mark as captured" page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import fragment
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    i,
    label,
    li,
    option,
    p,
    select,
    strong,
    ul,
)
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_mark_captured.html")
def list_fighter_mark_captured(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    capturing_lists = context["capturing_lists"]

    proximal = str(fighter.term_proximal_demonstrative).lower()

    body = form(
        action=reverse("core:list-fighter-mark-captured", args=[lst.id, fighter.id]),
        method="post",
    )[
        CsrfInput(context["request"]),
        Alert(
            strong["Important:"],
            " Once captured, ",
            proximal,
            " will not be able to participate in battles for ",
            lst.name,
            " until they are returned or sold to guilders.",
            variant="warning",
            class_="mb-0",
        ),
        p["You are marking ", strong[fighter.name], " as captured. This will:"],
        ul[
            li["Remove them from active duty in your gang"],
            li["Allow the capturing gang to decide their fate"],
            li["Prevent them from participating in battles"],
        ],
        div(class_="mb-3")[
            label(for_="capturing_list", class_="form-label")[
                "Select the capturing gang:"
            ],
            select(
                class_="form-select",
                id="capturing_list",
                name="capturing_list",
                required=True,
            )[
                option(value="")["Choose a gang..."],
                tuple(option(value=gang.id)[gang.name] for gang in capturing_lists),
            ],
            div(class_="form-text")[
                "The selected gang will be able to sell ",
                proximal,
                " to guilders or return them for ransom.",
            ],
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-warning")[
                i(class_="bi-person-lock"), " Mark as Captured"
            ],
            a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content = fragment[
        back_link(context, text=lst.name),
        PageShell(
            h1(class_="h3")[f"Mark as Captured: {fighter.fully_qualified_name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Mark as Captured - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
