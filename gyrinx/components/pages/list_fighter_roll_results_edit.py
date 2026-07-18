"""Fighter roll-results list (with remove links) display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import date as date_filter
from django.urls import reverse
from django.utils.timezone import template_localtime

from ..design import PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, em, h1, p, span
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _result_card(result: Any, lst: Any, fighter: Any) -> Node:
    return div(class_="border rounded p-2 vstack gap-1")[
        div(class_="hstack gap-2")[
            span(class_="fw-bold")[result.row.name],
            span(class_="text-secondary fs-7")[result.row.table.name],
        ],
        div(class_="fs-7")[result.row.description] if result.row.description else None,
        div(class_="text-secondary fs-7")[
            "Received ",
            date_filter(template_localtime(result.date_received), "M j, Y"),
            f" · +{result.rating_increase}¢" if result.rating_increase else None,
            f" · {result.counter_cost} {result.counter.name} spent"
            if (result.counter_cost and result.counter)
            else None,
        ],
        div(class_="fs-7")[em[result.notes]] if result.notes else None,
        div[
            a(
                href=reverse(
                    "core:list-fighter-roll-result-remove",
                    args=[lst.id, fighter.id, result.id],
                ),
                class_="btn btn-danger btn-sm",
            )["Remove"]
        ],
    ]


@register_page("core/list_fighter_roll_results_edit.html")
def list_fighter_roll_results_edit(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    results = context["results"]

    if results:
        body: Node = div(class_="vstack gap-2")[
            tuple(_result_card(result, lst, fighter) for result in results)
        ]
    else:
        body = p(class_="text-secondary")[f"{fighter.name} has no roll results."]

    content: Node = fragment[
        back_link(context, url=reverse("core:list", args=[lst.id]), text=lst.name),
        PageShell(
            h1(class_="h3")[f"Roll results: {fighter.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Roll results - {fighter.name} - {lst.name}",
        content=content,
    )
