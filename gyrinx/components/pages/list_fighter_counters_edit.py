"""Fighter counter edit page component (value, free-form spends, roll flows)."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import date as date_filter
from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, i, input_, label, p, span

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_counters_edit.html")
def edit_list_fighter_counter(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    counter = context["counter"]
    form_obj = context["form"]
    spend_form = context["spend_form"]
    flows = context["flows"]
    spends = context["spends"]
    can_spend = context["can_spend"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-counter-edit",
            "fighter_url_extra_arg": counter.id,
        },
        request=request,
    )

    main_form = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        input_(type="hidden", name="intent", value="save"),
        div[
            label(for_=form_obj["value"].id_for_label, class_="form-label fw-bold")[
                counter.name
            ],
            p(class_="text-secondary fs-7 mb-1")[counter.description]
            if counter.description
            else None,
            p(class_="mb-1 fs-7")[
                "Current value: ",
                span(class_="badge text-bg-secondary")[form_obj.current_value],
            ],
            raw(str(form_obj["value"])),
            tuple(
                div(class_="text-danger fs-7")[error]
                for error in form_obj["value"].errors
            ),
        ],
        div(class_="hstack gap-2 mt-3 align-items-center")[
            button(type="submit", class_="btn btn-success btn-sm")["Save"],
            a(
                href=reverse("core:list", args=[lst.id]) + f"#{fighter.id}",
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    spend_section: Node = None
    if can_spend:
        spend_section = div(class_="vstack gap-2")[
            h2(class_="h5 mb-0")[f"Spend {counter.name}"],
            p(class_="text-secondary fs-7 mb-0")[
                f"Record spending some {counter.name} without rolling on a table."
            ],
            form(method="post", class_="border rounded p-2 vstack gap-2")[
                CsrfInput(request),
                input_(type="hidden", name="intent", value="spend"),
                div[
                    label(
                        for_=spend_form["amount"].id_for_label,
                        class_="form-label fw-bold mb-1",
                    )[spend_form["amount"].label],
                    raw(str(spend_form["amount"])),
                    tuple(
                        div(class_="text-danger fs-7")[error]
                        for error in spend_form["amount"].errors
                    ),
                ],
                div[
                    label(
                        for_=spend_form["reason"].id_for_label,
                        class_="form-label fw-bold mb-1",
                    )[spend_form["reason"].label],
                    raw(str(spend_form["reason"])),
                    tuple(
                        div(class_="text-danger fs-7")[error]
                        for error in spend_form["reason"].errors
                    ),
                ],
                div[button(type="submit", class_="btn btn-primary btn-sm")["Spend"]],
            ],
        ]

    spends_section: Node = None
    if spends:
        spends_section = div(class_="vstack gap-2")[
            h2(class_="h5 mb-0")["Recorded spends"],
            tuple(
                div(class_="border rounded p-2 vstack gap-1")[
                    div(
                        class_="hstack gap-2 align-items-start justify-content-between"
                    )[
                        div(class_="fw-bold")[f"Spent {spend.amount} {counter.name}"],
                        form(method="post", class_="mb-0")[
                            CsrfInput(request),
                            input_(
                                type="hidden",
                                name="remove_spend_id",
                                value=str(spend.id),
                            ),
                            button(
                                type="submit",
                                class_="btn btn-danger btn-sm",
                                aria_label=(
                                    f"Remove spend of {spend.amount} {counter.name}"
                                ),
                            )["Remove"],
                        ],
                    ],
                    div(class_="fs-7")[spend.reason] if spend.reason else None,
                    div(class_="fs-7 text-secondary")[
                        date_filter(spend.date_spent, "j M Y, H:i")
                    ],
                ]
                for spend in spends
            ),
        ]

    flows_section: Node = None
    if flows:
        flows_section = div(class_="vstack gap-2")[
            h2(class_="h5 mb-0")[f"Spend {counter.name} on a roll"],
            tuple(
                div(class_="border rounded p-2 vstack gap-1")[
                    div(class_="fw-bold")[entry["flow"].name],
                    div(class_="text-secondary fs-7")[entry["flow"].description]
                    if entry["flow"].description
                    else None,
                    div(class_="fs-7")[
                        f"Spend {entry['flow'].cost} {counter.name} and roll on "
                        f"{entry['flow'].roll_table.name} "
                        f"({entry['flow'].roll_table.dice}).",
                    ],
                    div[
                        a(
                            href=reverse(
                                "core:list-fighter-roll-flow",
                                args=[lst.id, fighter.id, entry["flow"].id],
                            ),
                            class_="btn btn-primary btn-sm",
                        )[
                            "Start ",
                            i(class_="bi-arrow-right", aria_hidden="true"),
                        ]
                    ]
                    if entry["affordable"]
                    else div(class_="text-secondary fs-7")[
                        f"Requires {entry['flow'].cost} {counter.name} — currently "
                        f"{form_obj.current_value}.",
                    ],
                ]
                for entry in flows
            ),
        ]

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[f"Edit {counter.name} for {fighter.name}"],
            main_form,
            spend_section,
            spends_section,
            flows_section,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"{counter.name} - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
