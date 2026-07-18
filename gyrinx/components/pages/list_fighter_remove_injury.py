"""Fighter injury-removal confirmation page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils.timezone import template_localtime

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, br, button, div, em, form, h1, h5, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_remove_injury.html")
def list_fighter_remove_injury(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    injury = context["injury"]
    request = context["request"]

    term = fighter.term_injury_singular
    term_lower = term.lower()

    card_text_children: list[Node] = []
    if injury.injury.description:
        card_text_children += [injury.injury.description, br]
    if injury.notes:
        card_text_children.append(em["Notes: ", injury.notes])

    content: Node = fragment[
        back_link(context, url=reverse("core:list", args=[lst.id]), text=lst.name),
        PageShell(
            h1(class_="h3")[f"Remove {term}: {fighter.name}"],
            div(class_="card")[
                div(class_="card-body")[
                    h5(class_="card-title")[injury.injury.name],
                    p(class_="card-text")[tuple(card_text_children)],
                    p(class_="text-secondary mb-0")[
                        "Received: ",
                        date_filter(template_localtime(injury.date_received), "M j, Y"),
                    ],
                ],
            ],
            Alert(
                f"Removing this {term_lower} will automatically log the "
                "recovery to the campaign action log.",
                variant="info",
                class_="mb-0",
            ),
            form(
                action=reverse(
                    "core:list-fighter-injury-remove",
                    args=[lst.id, fighter.id, injury.id],
                ),
                method="post",
            )[
                CsrfInput(request),
                p[
                    f"Are you sure you want to remove this {term_lower} "
                    f"from {fighter.name}?"
                ],
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-danger")[f"Remove {term}"],
                    a(
                        href=reverse(
                            "core:list-fighter-injuries-edit",
                            args=[lst.id, fighter.id],
                        ),
                        class_="btn btn-link",
                    )["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove {term} - {fighter.name} - {lst.name}",
        content=content,
    )
