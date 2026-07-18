"""Weapon-profile edit page for a single equipment assignment.

Port of ``core/list_fighter_weapon_edit.html`` (view: ``edit_single_weapon`` in
``core/views/fighter/equipment.py``). Three un-ported partials are bridged
verbatim through the DjangoTemplates loader: ``list_common_header.html``,
``list_fighter_weapon_assign_name.html`` and ``fighter_card_weapon_menu.html``.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    h4,
    i,
    input_,
    p,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)

_STAT_KEYS = (
    ("range_short", "text-center"),
    ("range_long", "text-center"),
    ("accuracy_short", "text-center border-start"),
    ("accuracy_long", "text-center"),
    ("strength", "text-center border-start"),
    ("armour_piercing", "text-center"),
    ("damage", "text-center"),
    ("ammo", "text-center"),
)


def _stat_cells(profile: Any, *, subscript: bool = False) -> tuple[Node, ...]:
    """The eight stat ``<td>``s, mirroring ``{{ profile.x|default:"-" }}``."""

    def get(key: str) -> Any:
        return profile[key] if subscript else getattr(profile, key)

    return tuple(td(class_=classes)[get(key) or "-"] for key, classes in _STAT_KEYS)


def _traitline_row(traits: list[str]) -> Node:
    return tr[td, td(colspan="9")[", ".join(traits)]]


@register_page("core/list_fighter_weapon_edit.html")
def edit_single_weapon(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    profiles = context["profiles"]
    error_message = context.get("error_message")
    request = context["request"]
    user = context.get("user")

    equipment_name = assign.content_equipment.name

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

    # ``list_fighter_weapon_assign_name.html`` is included with the same
    # ``assign`` override wherever it appears, so render it once and reuse.
    assign_name = raw(
        render_to_string(
            "core/includes/list_fighter_weapon_assign_name.html",
            {**context, "assign": assign},
            request=request,
        )
    )

    standard_profiles = assign.standard_profiles_cached

    # Section 1: standard (free) profiles — the base weapon stats.
    section1: list[Node] = []
    for index, profile in enumerate(standard_profiles):
        if profile.name:
            name_cell: Node = fragment[i(class_="bi-dash"), " ", profile.name]
        elif index == 0:
            name_cell = assign_name
        else:
            name_cell = None
        section1.append(tr[(td[name_cell],) + _stat_cells(profile)])
        if profile.traitline_cached:
            section1.append(_traitline_row(profile.traitline_cached))

    # Section 2: added paid profiles.
    section2: list[Node] = []
    for pd in assign.weapon_profiles_display():
        profile = pd["profile"]
        cost_display = pd["cost_display"]
        show_cost = cost_display != "0¢" and cost_display != ""
        name_cell = fragment[
            i(class_="bi-dash"),
            " ",
            profile.name,
            span(class_="text-secondary")[f"({cost_display})"] if show_cost else None,
            a(
                href=reverse(
                    "core:list-fighter-weapon-profile-delete",
                    args=[lst.id, fighter.id, assign.id, profile.id],
                ),
                class_="btn btn-link btn-sm link-danger icon-link",
            )[i(class_="bi-trash"), " Remove"],
        ]
        section2.append(tr[(td[name_cell],) + _stat_cells(profile)])
        if profile.traitline_cached:
            section2.append(_traitline_row(profile.traitline_cached))

    # Section 3: available paid profiles not yet added.
    section3: list[Node] = []
    if profiles:
        for profile in profiles:
            name_cell = fragment[
                i(class_="bi-dash"),
                " ",
                profile["name"],
                " ",
                span(class_="text-secondary")[f"(+{profile['cost_display']})"],
                " ",
                form(
                    action=reverse(
                        "core:list-fighter-weapon-edit",
                        args=[lst.id, fighter.id, assign.id],
                    ),
                    method="post",
                    class_="d-inline",
                )[
                    CsrfInput(request),
                    input_(type="hidden", name="profile_id", value=profile["id"]),
                    button(type="submit", class_="btn btn-link btn-sm icon-link")[
                        i(class_="bi-plus-lg"), " Add"
                    ],
                ],
            ]
            row_cells = (
                (td[name_cell],)
                + _stat_cells(profile, subscript=True)
                + (td(class_="text-end"),)
            )
            section3.append(tr[row_cells])
            if profile["traits"]:
                section3.append(tr[td, td(colspan="9")[profile["traits"]]])

    if assign.has_total_cost_override():
        cost_badge = span(class_="badge text-bg-secondary")[
            f"{assign.total_cost_override}¢"
        ]
    else:
        cost_badge = span(class_="badge text-bg-secondary")[assign.cost_display()]

    header_row = tr[
        th(scope="col")[assign_name if len(standard_profiles) == 0 else None],
        th(class_="text-center", scope="col")["S"],
        th(class_="text-center", scope="col")["L"],
        th(class_="text-center border-start", scope="col")["S"],
        th(class_="text-center", scope="col")["L"],
        th(class_="text-center border-start", scope="col")["Str"],
        th(class_="text-center", scope="col")["Ap"],
        th(class_="text-center", scope="col")["D"],
        th(class_="text-center", scope="col")["Am"],
    ]

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

    card = div(class_="card col-12 col-md-8 col-lg-6")[
        div(
            class_="card-header py-1 px-2 hstack justify-content-between align-items-center"
        )[
            h4(class_="h5 mb-0")[equipment_name],
            div[cost_badge],
        ],
        div(class_="card-body py-2 px-2")[
            div(class_="table-responsive")[
                table(class_="table table-sm table-borderless mb-0 fs-7")[
                    thead(class_="table-group-divider")[header_row],
                    tbody(class_="table-group-divider")[
                        tuple(section1),
                        tuple(section2),
                    ],
                    tbody(class_="table-group-divider")[tuple(section3)],
                ]
            ],
            p(class_="text-secondary mb-0 mt-3 fs-7")[
                "No additional weapon profiles available to add."
            ]
            if not profiles
            else None,
        ],
        div(class_="card-footer fs-7")[footer_menu],
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
            h1(class_="h3")[f"Edit: {equipment_name} - {fighter.fully_qualified_name}"],
            error_alert,
            card,
        ],
    ]
    return Page(
        title=(
            f"Edit Weapon - {equipment_name} - {fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
