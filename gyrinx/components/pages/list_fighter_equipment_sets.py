"""Fighter equipment-sets (Tools of the Trade) management page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    h2,
    i,
    input_,
    p,
    span,
    table,
    tbody,
    td,
    tr,
)

SHELL = "col-12 col-lg-8 px-0 vstack gap-3"


def _item_names(item_names: list[str]) -> Node:
    """Port of the comma-separated item-name summary (or the empty fallback)."""
    if not item_names:
        return span(class_="fst-italic")["Nothing selected"]
    nodes: list[Node] = []
    last = len(item_names) - 1
    for index, name in enumerate(item_names):
        nodes.append(span[name])
        if index != last:
            nodes.append(span[raw(",&nbsp;")])
    return tuple(nodes)


def _default_row(context: dict[str, Any], lst: Any, fighter: Any) -> Node:
    request = context["request"]
    if not context.get("has_active_set"):
        action = span(class_="badge text-bg-success")["Active"]
    else:
        action = form(
            method="post",
            action=reverse(
                "core:list-fighter-equipment-set-activate-default",
                args=[lst.id, fighter.id],
            ),
            class_="d-inline",
        )[
            CsrfInput(request),
            input_(type="hidden", name="next", value=request.path),
            button(type="submit", class_="btn btn-sm btn-secondary")["Activate"],
        ]
    return tr[
        td(class_="ps-2")[
            div(class_="fw-semibold")["Default"],
            div(class_="fs-7 text-secondary")["All equipment"],
        ],
        td(class_="text-end pe-2")[action],
    ]


def _set_row(context: dict[str, Any], lst: Any, fighter: Any, entry: dict) -> Node:
    request = context["request"]
    eqset = entry["set"]
    if entry["is_active"]:
        active = span(class_="badge text-bg-success")["Active"]
    else:
        active = form(
            method="post",
            action=reverse(
                "core:list-fighter-equipment-set-activate",
                args=[lst.id, fighter.id, eqset.id],
            ),
            class_="d-inline",
        )[
            CsrfInput(request),
            input_(type="hidden", name="next", value=request.path),
            button(type="submit", class_="btn btn-sm btn-secondary")["Activate"],
        ]
    return tr[
        td(class_="ps-2")[
            div(class_="fw-semibold")[eqset.name],
            div(class_="fs-7 text-secondary")[_item_names(entry["item_names"])],
        ],
        td(class_="text-end pe-2")[
            div(class_="d-inline-flex gap-2 align-items-center")[
                active,
                a(
                    class_="btn btn-sm btn-primary",
                    href=reverse(
                        "core:list-fighter-equipment-set-edit",
                        args=[lst.id, fighter.id, eqset.id],
                    ),
                )[i(class_="bi-pencil"), " Edit"],
                form(
                    method="post",
                    action=reverse(
                        "core:list-fighter-equipment-set-delete",
                        args=[lst.id, fighter.id, eqset.id],
                    ),
                    class_="d-inline",
                    onsubmit="return confirm('Delete this set? The Fighter keeps all their equipment.');",
                )[
                    CsrfInput(request),
                    button(
                        type="submit",
                        class_="btn btn-sm btn-link link-danger p-0",
                        aria_label="Delete set",
                    )[i(class_="bi-trash")],
                ],
            ]
        ],
    ]


def _sets_body(context: dict[str, Any], lst: Any, fighter: Any) -> Node:
    equipment_sets = context.get("equipment_sets") or []
    request = context["request"]

    rows: list[Node] = [_default_row(context, lst, fighter)]
    if equipment_sets:
        rows.extend(_set_row(context, lst, fighter, entry) for entry in equipment_sets)
    else:
        rows.append(
            tr[
                td(colspan="2", class_="ps-2 text-secondary")[
                    "No sets yet. Create one below."
                ]
            ]
        )

    return fragment[
        p(class_="text-secondary mb-0")[
            "Sets let this Fighter field different loadouts. Every item stays owned by the "
            "Fighter — a set just chooses which weapons and gear are shown. Switching sets "
            "never changes credits or wealth, only the displayed rating."
        ],
        div(class_="alert alert-info alert-icon", role="alert")[
            i(class_="bi-info-circle"),
            div[
                "The active set is what shows on the card, and is used when you print this gang."
            ],
        ],
        # Sets
        div[
            div(class_="bg-body-secondary rounded px-2 py-1 mb-2")[
                h2(class_="h5 mb-0")["Sets"]
            ],
            table(class_="table table-sm table-borderless align-middle mb-0")[
                tbody[tuple(rows)]
            ],
        ],
        # Create a set
        div[
            div(class_="bg-body-secondary rounded px-2 py-1 mb-2")[
                h2(class_="h5 mb-0")["Create a set"]
            ],
            div(class_="px-2")[
                form(
                    method="post",
                    action=reverse(
                        "core:list-fighter-equipment-set-create",
                        args=[lst.id, fighter.id],
                    ),
                    class_="hstack gap-2",
                )[
                    CsrfInput(request),
                    input_(
                        type="text",
                        name="name",
                        class_="form-control form-control-sm",
                        placeholder="e.g. Close-quarters loadout",
                        aria_label="New set name",
                        maxlength="255",
                        required=True,
                    ),
                    button(type="submit", class_="btn btn-sm btn-success text-nowrap")[
                        i(class_="bi-plus-lg"), " Create"
                    ],
                ],
                p(class_="text-secondary fs-7 mt-2 mb-0")[
                    "A new set starts with everything the Fighter has — you then remove "
                    "what they leave behind."
                ],
            ],
        ],
    ]


@register_page("core/list_fighter_equipment_sets.html")
def edit_list_fighter_equipment_sets(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-equipment-sets",
        },
        request=request,
    )

    if not fighter.has_tools_of_the_trade:
        body: Node = div(class_="alert alert-info alert-icon", role="alert")[
            i(class_="bi-info-circle"),
            div[
                "This Fighter does not have the requisite rule (Tools of the Trade), "
                "so equipment sets aren't available."
            ],
        ]
    else:
        body = _sets_body(context, lst, fighter)

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3 mb-0")[f"Equipment sets: {fighter.fully_qualified_name}"],
            body,
            kind=SHELL,
        ),
    ]
    return Page(
        title=f"Equipment sets - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
