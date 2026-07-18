"""Roll-flow confirm page component: review a rolled result and apply it."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import Alert, CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, li, p, span, ul


@register_page("core/list_fighter_roll_flow_confirm.html")
def list_fighter_roll_flow_confirm(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    flow = context["flow"]
    table = context["table"]
    dice = context["dice"]
    rolled_value = context["rolled_value"]
    row = context["row"]
    modifiers = context["modifiers"]
    roll_url = context["roll_url"]
    request = context["request"]

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {**context, "list": lst, "link_list": "true"},
            request=request,
        )
    )

    summary = div(class_="vstack gap-1")[
        h1(class_="h3 mb-0")[flow.name],
        p(class_="text-secondary fs-7 mb-0")[
            fighter.name,
            " rolled ",
            tuple(span(class_="badge text-bg-secondary")[die] for die in dice),
            " on ",
            table.name,
            " (",
            table.dice,
            "): ",
            span(class_="fw-bold")[rolled_value],
        ],
    ]

    if row:
        result: Node = fragment[
            div(class_="card shadow-sm")[
                div(class_="card-body vstack gap-2")[
                    h2(class_="h5 card-title mb-0")[row.name],
                    p(class_="mb-0")[row.description] if row.description else None,
                    ul(class_="mb-0 fs-7")[tuple(li[str(mod)] for mod in modifiers)]
                    if modifiers
                    else None,
                    div(class_="fs-7 text-secondary")[
                        "Applying this result will spend ",
                        flow.cost,
                        " ",
                        flow.counter.name,
                        " and increase ",
                        fighter.name,
                        "'s cost by ",
                        row.rating_increase,
                        "¢.",
                    ],
                ]
            ],
            form(method="post", class_="hstack gap-2")[
                CsrfInput(request),
                button(type="submit", class_="btn btn-primary")["Apply ", row.name],
                a(
                    href=f"{reverse('core:list', args=[lst.id])}#{fighter.id}",
                    class_="btn btn-link",
                )["Cancel"],
            ],
        ]
    else:
        result = fragment[
            Alert(
                "No result on ",
                table.name,
                " matches a roll of ",
                rolled_value,
                ". Try rolling again — if this keeps happening, the table may be "
                "missing an entry and the Gyrinx team needs to fix it.",
                variant="warning",
                class_="mb-0",
            ),
            div[a(href=roll_url, class_="btn btn-link px-0")["← Back"]],
        ]

    content: Node = fragment[
        header,
        div(class_="col-12 col-md-8 col-lg-6 px-0 vstack gap-4")[summary, result],
    ]
    return Page(
        title=f"Confirm {flow.name} - {fighter.name} - {lst.name}",
        content=content,
    )
