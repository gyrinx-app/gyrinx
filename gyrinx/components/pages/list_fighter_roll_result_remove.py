"""Roll-result remove confirmation page component."""

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


@register_page("core/list_fighter_roll_result_remove.html")
def list_fighter_roll_result_remove(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    roll_result = context["roll_result"]
    request = context["request"]

    row = roll_result.row
    counter = roll_result.counter

    card_text: list[Node] = []
    if row.description:
        card_text += [row.description, br]
    if roll_result.notes:
        card_text.append(em["Notes: ", roll_result.notes])

    alert_body: list[Node] = [
        "Removing this result will reverse its stat changes, reduce ",
        fighter.name,
        "'s cost by ",
        roll_result.rating_increase,
        "¢",
    ]
    if roll_result.counter_cost and counter:
        alert_body += [
            ", and refund ",
            roll_result.counter_cost,
            " ",
            counter.name,
        ]
    alert_body.append(".")

    content: Node = fragment[
        back_link(context, url=reverse("core:list", args=[lst.id]), text=lst.name),
        PageShell(
            h1(class_="h3")[f"Remove {row.name}: {fighter.name}"],
            div(class_="card")[
                div(class_="card-body")[
                    h5(class_="card-title")[row.name],
                    p(class_="card-text")[tuple(card_text)],
                    p(class_="text-secondary mb-0")[
                        f"Received: {date_filter(template_localtime(roll_result.date_received), 'M j, Y')}"
                    ],
                ]
            ],
            Alert(*alert_body, variant="info", class_="mb-0"),
            form(
                action=reverse(
                    "core:list-fighter-roll-result-remove",
                    args=[lst.id, fighter.id, roll_result.id],
                ),
                method="post",
            )[
                CsrfInput(request),
                p[
                    "Are you sure you want to remove this result from ",
                    fighter.name,
                    "?",
                ],
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-danger")["Remove"],
                    a(
                        href=reverse(
                            "core:list-fighter-roll-results-edit",
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
        title=f"Remove {row.name} - {fighter.name} - {lst.name}",
        content=content,
    )
