"""Fighter psyker-powers edit page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.text import slugify

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h3, i, input_, span, table, tbody, td, tr
from ._shared import back_link


@register_page("core/list_fighter_psyker_powers_edit.html")
def edit_list_fighter_powers(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]
    current_powers = context["current_powers"]
    available_disciplines = context["available_disciplines"]
    search_query = context.get("search_query", "")

    edit_action = reverse("core:list-fighter-powers-edit", args=[lst.id, fighter.id])

    # --- Current powers table ---------------------------------------------
    def current_row(assign: Any) -> Node:
        is_disabled = getattr(assign, "is_disabled", False)
        kind = assign.kind()
        if is_disabled:
            controls: Node = fragment[
                input_(type="hidden", name="action", value="enable"),
                button(
                    type="submit", class_="btn btn-link icon-link fs-7 link-success"
                )[i(class_="bi-check-lg"), " Enable"],
            ]
        else:
            controls = fragment[
                input_(type="hidden", name="action", value="remove"),
                button(type="submit", class_="btn btn-link icon-link fs-7 link-danger")[
                    i(class_="bi-trash"),
                    " Disable" if kind == "default" else " Remove",
                ],
            ]
        return tr(
            class_="text-decoration-line-through text-secondary"
            if is_disabled
            else None
        )[
            td[
                assign.psyker_power.name,
                span(class_="badge text-bg-secondary ms-1")["Default"]
                if kind == "default"
                else None,
            ],
            td(class_="text-secondary")[assign.disc],
            td(class_="text-end")[
                form(method="post", action=edit_action, class_="d-inline")[
                    CsrfInput(request),
                    input_(
                        type="hidden",
                        name="psyker_power_id",
                        value=assign.psyker_power.id,
                    ),
                    input_(type="hidden", name="assign_kind", value=kind),
                    controls,
                ]
            ],
        ]

    current_rows: list[Node] = (
        [current_row(assign) for assign in current_powers]
        if current_powers
        else [
            tr[
                td(colspan="3", class_="text-center text-secondary")[
                    "No psyker powers assigned to this fighter."
                ]
            ]
        ]
    )

    current_card = div(class_="card")[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")["Current Psyker Powers"]],
        div(class_="card-body p-0 p-sm-2")[
            div(class_="table-responsive")[
                table(class_="table table-borderless table-sm align-middle mb-0")[
                    tbody[current_rows]
                ]
            ]
        ],
    ]

    # --- Filter bar (bridged: partial has no component port) --------------
    filter_bar = raw(
        render_to_string(
            "core/includes/fighter_psyker_powers_filter.html",
            {**context, "action": edit_action},
            request=request,
        )
    )

    # --- Powers grid ------------------------------------------------------
    def discipline_card(disc_data: dict[str, Any]) -> Node:
        discipline = disc_data["discipline"]
        return div(
            class_="card g-col-12 g-col-md-6",
            id=f"discipline-{slugify(discipline)}",
        )[
            div(class_="card-header p-2")[h3(class_="h5 mb-0")[discipline]],
            div(class_="card-body p-0 p-sm-2")[
                div(class_="table-responsive")[
                    table(class_="table table-borderless table-sm align-middle mb-0")[
                        tbody[
                            [
                                tr[
                                    td[assign.psyker_power.name],
                                    td(class_="text-end")[
                                        form(
                                            method="post",
                                            action=edit_action,
                                            class_="d-inline",
                                        )[
                                            CsrfInput(request),
                                            input_(
                                                type="hidden",
                                                name="psyker_power_id",
                                                value=assign.psyker_power.id,
                                            ),
                                            input_(
                                                type="hidden",
                                                name="assign_kind",
                                                value=assign.kind(),
                                            ),
                                            input_(
                                                type="hidden",
                                                name="action",
                                                value="add",
                                            ),
                                            button(
                                                type="submit",
                                                class_="btn btn-sm btn-outline-primary",
                                            )[i(class_="bi-plus-lg"), " Add"],
                                        ]
                                    ],
                                ]
                                for assign in disc_data["powers"]
                            ]
                        ]
                    ]
                ]
            ],
        ]

    if available_disciplines:
        grid_children: list[Node] = [
            discipline_card(disc_data) for disc_data in available_disciplines
        ]
    elif search_query:
        grid_children = [
            div(class_="g-col-12")[
                'No psyker powers found matching "',
                search_query,
                '".',
                a(href="?")["Clear your search"],
                ".",
            ]
        ]
    else:
        grid_children = [div(class_="g-col-12")["No available psyker powers found."]]

    powers_grid = div(class_="grid")[grid_children]

    content: Node = fragment[
        back_link(context, url=reverse("core:list", args=[lst.id]), text=lst.name),
        div(class_="col-12 px-0 vstack gap-3")[
            h1(class_="h3")["Psyker Powers: ", fighter.fully_qualified_name],
            current_card,
            filter_bar,
            powers_grid,
        ],
    ]

    return Page(
        title=f"Psyker Powers - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
