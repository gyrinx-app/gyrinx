"""Weapon-accessories edit page for a single equipment assignment.

Port of ``core/list_fighter_weapons_accessories_edit.html`` (view:
``edit_list_fighter_weapon_accessories`` in ``core/views/fighter/equipment.py``).
Four un-ported partials are bridged verbatim through the DjangoTemplates loader:
``list_common_header.html``, ``weapon_stat_headers.html``,
``list_fighter_weapon_rows.html`` and ``fighter_card_weapon_menu.html``.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import cachebuster

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    em,
    form,
    h1,
    h4,
    i,
    input_,
    label,
    p,
    span,
    table,
    tbody,
)


@register_page("core/list_fighter_weapons_accessories_edit.html")
def edit_list_fighter_weapon_accessories(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    accessories = context["accessories"]
    filter_mode = context["filter"]
    search_query = context["search_query"]
    error_message = context.get("error_message")
    request = context["request"]
    user = context.get("user")

    equipment_name = assign.content_equipment.name

    accessories_edit_url = reverse(
        "core:list-fighter-weapon-accessories-edit",
        args=[lst.id, fighter.id, assign.id],
    )

    # ---- Un-ported partials bridged through the DjangoTemplates loader ----
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {
                **context,
                "list": lst,
                "link_list": "true",
                "fighter": fighter,
                "fighter_url_name": "core:list-fighter-weapons-edit",
            },
            request=request,
        )
    )
    # Both weapon-table partials are included with no ``with`` overrides, so they
    # see the full page context (``first_col`` / ``show_al`` are undefined).
    stat_headers = raw(
        render_to_string(
            "core/includes/weapon_stat_headers.html",
            {**context},
            request=request,
        )
    )
    weapon_rows = raw(
        render_to_string(
            "core/includes/list_fighter_weapon_rows.html",
            {**context},
            request=request,
        )
    )

    # ---- Weapon details card ----
    if assign.has_total_cost_override():
        cost_badge = span(class_="badge text-bg-secondary")[
            f"{assign.total_cost_override}¢"
        ]
    else:
        cost_badge = span(class_="badge text-bg-secondary")[assign.cost_display()]

    show_footer = (
        user is not None and lst.owner_cached == user and not context.get("print")
    )
    footer_menu = (
        raw(
            render_to_string(
                "core/includes/fighter_card_weapon_menu.html",
                {**context, "assign": assign, "fighter": fighter, "list": lst},
                request=request,
            )
        )
        if show_footer
        else None
    )

    weapon_card = div(class_="card col-12 col-md-8 col-lg-6")[
        div(
            class_="card-header py-1 px-2 hstack justify-content-between align-items-center"
        )[
            h4(class_="h5 mb-0")[equipment_name],
            div(class_="mb-2")[cost_badge],
        ],
        div(class_="card-body py-2 px-2")[
            div(class_="table-responsive")[
                table(class_="table table-sm table-borderless mb-0 fs-7")[
                    stat_headers,
                    tbody(class_="table-group-divider")[weapon_rows],
                ]
            ],
        ],
        div(class_="card-footer fs-7")[footer_menu],
    ]

    # ---- Filter / search bar ----
    clear_link = (
        a(
            href=f"{accessories_edit_url}?filter={filter_mode}",
            class_="btn btn-outline-secondary",
        )["Clear"]
        if search_query
        else None
    )
    search_form = form(
        id="search",
        method="get",
        action=accessories_edit_url,
        class_="col-12 col-md-8 col-lg-6 vstack gap-2",
    )[
        input_(type="hidden", name="flash", value="search"),
        input_(type="hidden", name="cb", value=cachebuster()),
        div(class_="hstack gap-2")[
            div(class_="input-group")[
                span(class_="input-group-text")[i(class_="bi-search")],
                input_(
                    class_="form-control",
                    type="search",
                    placeholder="Search accessories...",
                    aria_label="Search",
                    name="q",
                    id="search-input",
                    value=search_query,
                ),
            ],
            div(class_="btn-group")[
                button(class_="btn btn-primary", type="submit")["Search"],
                clear_link,
            ],
        ],
        div(class_="form-check form-switch")[
            input_(type="hidden", name="filter", value="all"),
            input_(
                class_="form-check-input",
                type="checkbox",
                role="switch",
                id="filter-switch",
                name="filter",
                value="equipment-list",
                data_gy_toggle_submit="search",
                checked=(filter_mode == "equipment-list") or None,
            ),
            label(class_="form-check-label", for_="filter-switch")[
                "Only Equipment List"
            ],
        ],
    ]

    # ---- Available accessories card ----
    flash_class = "flash-warn" if request.GET.get("flash") == "search" else ""

    if accessories:
        body_children: list[Node] = [
            form(
                action=accessories_edit_url,
                method="post",
                class_="d-flex align-items-center gap-2",
            )[
                CsrfInput(request),
                input_(type="hidden", name="accessory_id", value=accessory["id"]),
                input_(type="hidden", name="filter", value=filter_mode),
                input_(type="hidden", name="q", value=search_query),
                div(class_="flex-grow-1")[
                    accessory["name"],
                    " ",
                    span(class_="text-secondary")[f"({accessory['cost_display']})"],
                ],
                button(type="submit", class_="btn btn-outline-primary btn-sm")[
                    i(class_="bi-plus"), " Add"
                ],
            ]
            for accessory in accessories
        ]
    else:
        body_children = [
            p(class_="text-secondary mb-0")[
                "No accessories found in the equipment list."
                if filter_mode == "equipment-list"
                else "No accessories found.",
                a(href=f"{accessories_edit_url}?filter={filter_mode}")[
                    em["Clear your search"]
                ]
                if search_query
                else None,
            ]
        ]

    available_card = div(class_="card col-12 col-md-8 col-lg-6")[
        div(class_="card-header p-1 p-sm-2")[
            h4(class_="h5 mb-0")["Available Accessories"],
        ],
        div(class_=f"card-body vstack gap-2 p-1 p-sm-2 {flash_class}")[
            tuple(body_children)
        ],
    ]

    error_alert = (
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]
        if error_message
        else None
    )

    content: Node = fragment[
        header,
        div(class_="col-12 px-0 vstack gap-3")[
            h1(class_="h3")[
                f"Accessories: {equipment_name} - {fighter.fully_qualified_name}"
            ],
            error_alert,
            weapon_card,
            search_form,
            available_card,
        ],
    ]
    return Page(
        title=(
            f"Accessories - {equipment_name} - {fighter.fully_qualified_name}"
            f" - {lst.name}"
        ),
        content=content,
    )
