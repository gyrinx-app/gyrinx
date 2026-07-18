"""Fighter gear (non-weapon equipment) edit page component."""

from __future__ import annotations

import itertools
from typing import Any

from django.template.defaultfilters import dictsort
from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import qt_contains, qt_rm

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
    h3,
    h4,
    i,
    input_,
    label,
    legend,
    span,
)


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


def _propagated_hidden_inputs(request: Any) -> tuple[Node, ...]:
    """Hidden inputs that carry the current filter query params into the POST."""
    hidden: list[Node] = []
    filter_val = request.GET.get("filter")
    if filter_val:
        hidden.append(input_(type="hidden", name="filter", value=filter_val))
    q_val = request.GET.get("q")
    if q_val:
        hidden.append(input_(type="hidden", name="q", value=q_val))
    for al_val in request.GET.getlist("al"):
        hidden.append(input_(type="hidden", name="al", value=al_val))
    mal_val = request.GET.get("mal")
    if mal_val:
        hidden.append(input_(type="hidden", name="mal", value=mal_val))
    for cat_val in request.GET.getlist("cat"):
        hidden.append(input_(type="hidden", name="cat", value=cat_val))
    mc_val = request.GET.get("mc")
    if mc_val:
        hidden.append(input_(type="hidden", name="mc", value=mc_val))
    return tuple(hidden)


def _upgrades_section(assign: Any, form_id: str) -> Node:
    equipment = assign.equipment
    upgrades = assign.upgrades_display()
    if len(upgrades) <= 0:
        return None

    if equipment.upgrade_mode_single:
        choices: Node = div(class_="hstack gap-1")[
            div[
                input_(
                    type="radio",
                    name="upgrades_field",
                    value="",
                    id="upgrade-none",
                    form=form_id,
                    class_="btn-check",
                ),
                label(class_="btn btn-sm", for_="upgrade-none")["None"],
            ],
            div(class_="flex-grow-1 btn-group")[
                tuple(
                    fragment[
                        input_(
                            type="radio",
                            name="upgrades_field",
                            value=ud["upgrade"].id,
                            id=f"upgrade-{ud['upgrade'].id}",
                            form=form_id,
                            class_="btn-check",
                        ),
                        label(
                            class_="btn btn-outline-secondary btn-sm",
                            for_=f"upgrade-{ud['upgrade'].id}",
                        )[
                            ud["upgrade"].name,
                            f"({ud['cost_display']})" if ud["cost_int"] != 0 else None,
                        ],
                    ]
                    for ud in upgrades
                )
            ],
        ]
    else:
        choices = fragment[
            tuple(
                div(class_="form-check fs-7")[
                    input_(
                        type="checkbox",
                        name="upgrades_field",
                        value=ud["upgrade"].id,
                        id=f"upgrade-{ud['upgrade'].id}",
                        form=form_id,
                        class_="form-check-input",
                    ),
                    label(
                        class_="form-check-label",
                        for_=f"upgrade-{ud['upgrade'].id}",
                    )[
                        ud["upgrade"].name,
                        f"({ud['cost_display']})" if ud["cost_int"] != 0 else None,
                    ],
                ]
                for ud in upgrades
            )
        ]

    return fragment[
        legend(class_="fs-7")[
            i(class_="bi-arrow-up-circle"),
            " ",
            equipment.upgrade_stack_name_display,
        ],
        choices,
    ]


def _gear_form(assign: Any, gear_action: str, request: Any) -> Node:
    equipment = assign.equipment
    form_id = f"gear-{equipment.id}"
    base_name = assign.base_name()
    base_cost_int = assign.base_cost_int()
    base_cost_display = assign.base_cost_display()

    return form(
        action=gear_action,
        method="post",
        id=form_id,
        class_="p-2 p-sm-0 py-sm-2 hstack gap-2",
    )[
        CsrfInput(request),
        input_(type="hidden", name="content_equipment", value=equipment.id),
        input_(type="hidden", name="assign_id", value=assign.id),
        _propagated_hidden_inputs(request),
        div(class_="vstack gap-1")[
            div(class_="hstack")[
                h4(class_="h6 mb-0")[
                    base_name,
                    " ",
                    span(class_="fs-7 text-secondary")[
                        f"({base_cost_display})" if base_cost_int != 0 else None
                    ],
                ],
                span(class_="ms-auto fs-7 text-secondary")[
                    equipment.rarity,
                    equipment.rarity_roll or "",
                ],
            ],
            _upgrades_section(assign, form_id),
            button(
                type="submit",
                class_="btn btn-outline-primary btn-sm",
                form=form_id,
            )[
                i(class_="bi-plus"),
                " Add ",
                base_name,
                " ",
                f"({base_cost_display})" if base_cost_int != 0 else None,
            ],
        ],
    ]


def _category_card(
    grouper: Any, items: list[Any], gear_action: str, request: Any
) -> Node:
    return div(class_="card g-col-12 g-col-md-6")[
        div(class_="card-header p-2")[
            div(class_="vstack gap-1")[
                div(class_="hstack")[h3(class_="h5 mb-0")[grouper]],
            ],
        ],
        div(class_=["card-body vstack p-0 px-sm-2 py-sm-1", _flash(request, "search")])[
            tuple(_gear_form(assign, gear_action, request) for assign in items)
        ],
    ]


def _empty_block(fighter: Any, request: Any) -> Node:
    filter_val = request.GET.get("filter")
    q_val = request.GET.get("q")

    if not filter_val:
        no_gear: Node = fragment[
            "No gear found in the equipment list of ",
            fighter.term_proximal_demonstrative.lower(),
            ".",
        ]
    else:
        no_gear = "No gear found."

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
        no_gear,
        clear_search,
        avail_link,
    ]


@register_page("core/list_fighter_gear_edit.html")
def edit_list_fighter_gear(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    error_message = context.get("error_message")
    assigns = context.get("assigns") or []
    request = context["request"]

    gear_action = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])

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
                "fighter_url_name": "core:list-fighter-gear-edit",
            },
            request=request,
        )
    )
    fighter_card = raw(
        render_to_string(
            "core/includes/fighter_card_gear.html",
            {
                **context,
                "list": lst,
                "fighter": fighter,
                "weapons_mode": "gear",
                "gear_mode": "edit",
            },
            request=request,
        )
    )
    gear_filter = raw(
        render_to_string(
            "core/includes/fighter_gear_filter.html",
            {**context, "action": gear_action},
            request=request,
        )
    )

    groups = _regroup(assigns)
    if groups:
        category_nodes: tuple[Node, ...] = tuple(
            _category_card(grouper, items, gear_action, request)
            for grouper, items in groups
        )
    else:
        category_nodes = (_empty_block(fighter, request),)

    error_alert = None
    if error_message:
        error_alert = div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]

    content: Node = fragment[
        header,
        div(class_="col-12 px-0 vstack gap-3")[
            h1(class_="h3")[f"Gear: {fighter.fully_qualified_name}"],
            error_alert,
            div(class_="grid")[
                fighter_card,
                gear_filter,
                category_nodes,
            ],
        ],
    ]

    return Page(
        title=f"Gear - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
