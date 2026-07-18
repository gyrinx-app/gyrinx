"""Roll-flow roll page component: show the table and roll (or enter) the dice."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    em,
    fieldset,
    form,
    h1,
    h2,
    i,
    legend,
    nav,
    option,
    p,
    select,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)


@register_page("core/list_fighter_roll_flow.html")
def list_fighter_roll_flow(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    flow = context["flow"]
    roll_table = context["table"]
    rows = context["rows"]
    form_obj = context["form"]
    counter_value = context["counter_value"]
    affordable = context["affordable"]
    counter_url = context["counter_url"]
    in_campaign = context["in_campaign"]
    request = context["request"]

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {**context, "list": lst, "link_list": "true"},
            request=request,
        )
    )

    intro = div(class_="vstack gap-1")[
        h1(class_="h3 mb-0")[flow.name],
        p(class_="text-secondary fs-7 mb-0")[
            "Spend ",
            flow.cost,
            " ",
            flow.counter.name,
            " and roll ",
            roll_table.dice,
            " on ",
            roll_table.name,
            " for ",
            fighter.name,
            ".",
        ],
        p(class_="text-secondary fs-7 mb-0")[flow.description]
        if flow.description
        else None,
    ]

    unaffordable_alert = (
        div(class_="alert alert-warning alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[
                fighter.name,
                " needs ",
                flow.cost,
                " ",
                flow.counter.name,
                " to use ",
                flow.name,
                " — currently ",
                counter_value,
                ".",
            ],
        ]
        if not affordable
        else None
    )

    non_field_errors = (
        div(class_="alert alert-danger alert-icon mb-last-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[raw(str(form_obj.non_field_errors()))],
        ]
        if form_obj.non_field_errors()
        else None
    )

    campaign_alert = (
        div(class_="alert alert-info alert-icon mb-0", role="alert")[
            i(class_="bi-info-circle"),
            div[
                "The roll will ",
                em["immediately"],
                " be added to the campaign action log.",
            ],
        ]
        if in_campaign
        else None
    )

    d6_2_select = (
        select(
            name="d6_2",
            class_="form-select",
            disabled=not affordable,
            aria_label="Second D6 result",
        )[
            option(value="", selected=True, disabled=True)["-"],
            tuple(option(value=str(digit))[str(digit)] for digit in "123456"),
        ]
        if roll_table.dice_count > 1
        else None
    )

    roll_form = form(method="post", class_="vstack gap-2", aria_label="Roll form")[
        CsrfInput(request),
        non_field_errors,
        div(class_="card shadow-sm")[
            div(class_="card-body vstack gap-3")[
                h2(class_="h5 card-title mb-0")["Roll ", roll_table.dice],
                campaign_alert,
                div(class_="vstack gap-2")[
                    nav(aria_label="Form navigation")[
                        button(
                            type="submit",
                            name="roll_action",
                            value="roll_auto",
                            class_="btn btn-primary",
                            disabled=not affordable,
                        )["Generate a ", roll_table.dice, " roll"]
                    ]
                ],
                fieldset(class_="vstack gap-2")[
                    legend(id="tabletop-result-label", class_="fs-6")[
                        "Or enter a tabletop result:"
                    ],
                    div(
                        class_="input-group",
                        aria_describedby="tabletop-result-label",
                    )[
                        select(
                            name="d6_1",
                            class_="form-select",
                            disabled=not affordable,
                            aria_label="First D6 result",
                        )[
                            option(value="", selected=True, disabled=True)["-"],
                            tuple(
                                option(value=str(digit))[str(digit)]
                                for digit in "123456"
                            ),
                        ],
                        d6_2_select,
                        button(
                            class_="btn btn-outline-primary",
                            type="submit",
                            name="roll_action",
                            value="roll_manual",
                            disabled=not affordable,
                        )["Confirm result"],
                    ],
                ],
            ]
        ],
    ]

    table_section = div(class_="vstack gap-2")[
        h2(class_="h5 mb-0")[roll_table.name],
        p(class_="text-secondary fs-7 mb-0")[roll_table.description]
        if roll_table.description
        else None,
        div(class_="table-responsive")[
            table(class_="table table-sm table-borderless mb-0")[
                thead[
                    tr(class_="fs-7")[
                        th(scope="col")[roll_table.dice],
                        th(scope="col")["Result"],
                        th(scope="col", class_="text-end")["Cost"],
                    ]
                ],
                tbody[
                    tuple(
                        tr(class_="fs-7")[
                            td(class_="text-nowrap")[row.roll_value],
                            td[
                                span(class_="fw-bold")[row.name],
                                div(class_="text-secondary")[row.description]
                                if row.description
                                else None,
                            ],
                            td(class_="text-end text-nowrap")[
                                "+", row.rating_increase, "¢"
                            ],
                        ]
                        for row in rows
                    )
                ],
            ]
        ],
    ]

    back = div[
        a(href=counter_url, class_="btn btn-link px-0")["← Back to ", flow.counter.name]
    ]

    content: Node = fragment[
        header,
        div(class_="col-12 col-md-8 col-lg-6 px-0 vstack gap-4")[
            intro,
            unaffordable_alert,
            roll_form,
            table_section,
            back,
        ],
    ]
    return Page(
        title=f"{flow.name} - {fighter.name} - {lst.name}",
        content=content,
    )
