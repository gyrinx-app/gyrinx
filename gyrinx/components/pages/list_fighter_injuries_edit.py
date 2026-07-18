"""Fighter injuries-management (edit) display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import date as date_filter
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import template_localtime

from ..design import Alert, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, em, h1, h5, i, span, strong, table, tbody, td, th, thead, tr

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _injury_rows(injury: Any, lst: Any, fighter: Any) -> Node:
    name_td = (
        td(rowspan="2")[injury.injury.name] if injury.notes else td[injury.injury.name]
    )
    main_row = tr[
        name_td,
        td[date_filter(template_localtime(injury.date_received), "M j, Y")],
        td[
            a(
                href=reverse(
                    "core:list-fighter-injury-remove",
                    args=[lst.id, fighter.id, injury.id],
                ),
                class_="link-danger",
            )["Remove"]
        ],
    ]
    if injury.notes:
        return fragment[
            main_row,
            tr[td(colspan="2", class_="ps-4 fs-7 text-secondary")[em[injury.notes]],],
        ]
    return main_row


@register_page("core/list_fighter_injuries_edit.html")
def list_fighter_injuries_edit(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]

    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    if fighter.is_injured:
        badge_variant = "text-bg-warning"
    elif fighter.is_dead:
        badge_variant = "text-bg-danger"
    else:
        badge_variant = "text-bg-success"

    state_card = div(class_="card")[
        div(class_="card-body")[
            div(class_="d-flex align-items-center justify-content-between")[
                div[
                    strong[f"{fighter.term_singular} State:"],
                    span(class_=f"badge {badge_variant} ms-2")[
                        fighter.get_injury_state_display()
                    ],
                ],
                a(
                    href=reverse(
                        "core:list-fighter-state-edit", args=[lst.id, fighter.id]
                    ),
                    class_="btn btn-secondary btn-sm",
                )[
                    i(class_="bi-pencil"),
                    f"Update {fighter.term_singular} State",
                ],
            ],
        ],
    ]

    injuries = list(fighter.injuries.all())
    if injuries:
        injuries_section: Node = div(class_="card")[
            div(class_="card-header")[
                h5(class_="mb-0")[f"Current {fighter.term_injury_plural}"]
            ],
            div(class_="card-body mb-last-0")[
                table(class_="table table-sm table-borderless")[
                    thead[
                        tr[
                            th[fighter.term_injury_singular],
                            th["Received"],
                            th[span(class_="visually-hidden")["Actions"]],
                        ]
                    ],
                    tbody[
                        tuple(_injury_rows(injury, lst, fighter) for injury in injuries)
                    ],
                ]
            ],
        ]
    else:
        injuries_section = Alert(
            f"{fighter.proximal_demonstrative} has no "
            f"{fighter.term_injury_plural.lower()}.",
            variant="info",
            class_="mb-0",
        )

    actions = div[
        a(
            href=reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id]),
            class_="btn btn-primary",
        )[i(class_="bi-plus-lg"), f" Add {fighter.term_injury_singular}"],
        a(
            href=reverse("core:list", args=[lst.id]) + f"#{fighter.id}",
            class_="btn btn-link",
        )["Cancel"],
    ]

    content: Node = fragment[
        header,
        PageShell(
            h1(class_="h3")[f"Edit {fighter.term_injury_plural}: {fighter.name}"],
            state_card,
            injuries_section,
            actions,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Edit Injuries - {fighter.name} - {lst.name}",
        content=content,
    )
