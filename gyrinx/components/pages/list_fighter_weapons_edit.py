"""Fighter weapons edit page component."""

from __future__ import annotations

import itertools
from typing import Any

from django.template.defaultfilters import dictsort
from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import qt_contains, qt_rm

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, em, h1, h3, i


def _flash(request: Any, flash_id: Any) -> str:
    """Port of ``{% flash id %}``: ``flash-warn`` when ``?flash=<id>``."""
    return "flash-warn" if request.GET.get("flash") == str(flash_id) else ""


def _regroup(assigns: Any) -> list[tuple[Any, list[Any]]]:
    """Port of ``{% regroup assigns|dictsort:"category" by cat as categories %}``."""
    sorted_assigns = dictsort(assigns, "category")
    if not sorted_assigns:
        return []
    return [
        (grouper, list(items))
        for grouper, items in itertools.groupby(sorted_assigns, key=lambda a: a.cat())
    ]


def _category_card(
    grouper: Any, items: list[Any], context: dict[str, Any], request: Any
) -> Node:
    # The card body content is the un-ported ``list_fighter_weapons.html``
    # include, bridged with the same ``with weapons=assigns mode="add"``
    # overrides the legacy template passes (full context carried forward).
    weapons_include = raw(
        render_to_string(
            "core/includes/list_fighter_weapons.html",
            {**context, "weapons": items, "mode": "add"},
            request=request,
        )
    )
    return div(class_="card g-col-12 g-col-md-6")[
        div(class_="card-header p-2")[
            div(class_="vstack gap-1")[
                div(class_="hstack")[h3(class_="h5 mb-0")[grouper]],
            ],
        ],
        div(class_=["card-body vstack gap-2 p-0 p-sm-2", _flash(request, "search")])[
            weapons_include
        ],
    ]


def _empty_block(request: Any) -> Node:
    # Django template quirk: `request.GET.filter == ""` is True only when the
    # "filter" key is PRESENT with an empty value (?filter=); when the key is
    # absent, `request.GET.filter` does NOT equal "" (it's a failed lookup).
    # So use .get("filter") (default None), not .get("filter", "").
    filter_val = request.GET.get("filter")
    q_val = request.GET.get("q")

    if filter_val == "":
        no_weapons: Node = "No weapons found in the equipment list of this fighter."
    else:
        no_weapons = "No weapons found."

    clear_search = None
    if q_val:
        clear_search = a(href=f"?{qt_rm(request, 'q', 'flash')}")[
            em["Clear your search"]
        ]

    has_c = qt_contains(request, "al", "C")
    has_r = qt_contains(request, "al", "R")
    has_i = qt_contains(request, "al", "I")
    has_e = qt_contains(request, "al", "E")
    has_u = qt_contains(request, "al", "U")

    avail_link = None
    if (
        filter_val == "all"
        and not has_c
        and not has_r
        and not has_i
        and not has_e
        and not has_u
    ):
        if request.GET.get("al"):
            avail_link = fragment[
                "or" if q_val else None,
                a(href="?filter=all&al=C&al=R&al=I&al=E&al=U#search")[
                    " ", em["Show equipment with any availability"]
                ],
                ".",
            ]
    elif filter_val == "all" and not has_i and not has_e and not has_u:
        avail_link = fragment[
            "or" if q_val else None,
            a(href="?filter=all&al=C&al=R&al=I&al=E&al=U#search")[
                em["Show equipment with any availability"]
            ],
            ".",
        ]

    return div(class_=["g-col-12", _flash(request, "search")])[
        no_weapons,
        clear_search,
        avail_link,
    ]


@register_page("core/list_fighter_weapons_edit.html")
def edit_list_fighter_weapons(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    error_message = context.get("error_message")
    assigns = context.get("assigns") or []
    request = context["request"]

    filter_action = reverse("core:list-fighter-weapons-edit", args=[lst.id, fighter.id])

    # Un-ported includes are bridged through the Django loader with the same
    # ``with`` overrides the legacy template passes (the full context is carried
    # forward, matching {% include %} semantics without ``only``).
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
    fighter_card = raw(
        render_to_string(
            "core/includes/fighter_card_gear.html",
            {**context, "list": lst, "fighter": fighter},
            request=request,
        )
    )
    gear_filter = raw(
        render_to_string(
            "core/includes/fighter_gear_filter.html",
            {**context, "action": filter_action},
            request=request,
        )
    )

    groups = _regroup(assigns)
    if groups:
        category_nodes: tuple[Node, ...] = tuple(
            _category_card(grouper, items, context, request)
            for grouper, items in groups
        )
    else:
        category_nodes = (_empty_block(request),)

    error_alert = None
    if error_message:
        error_alert = div(
            class_="alert alert-danger alert-icon g-col-12 mb-0", role="alert"
        )[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]

    content: Node = fragment[
        header,
        div(class_="col-lg-12 px-0 vstack gap-3")[
            h1(class_="h3")[f"Weapons: {fighter.fully_qualified_name}"],
            div(class_="grid")[
                fighter_card,
                error_alert,
                gear_filter,
                category_nodes,
            ],
        ],
    ]

    return Page(
        title=f"Weapons - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
