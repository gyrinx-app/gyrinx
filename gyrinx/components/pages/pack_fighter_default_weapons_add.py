"""Pack fighter "add default weapon" picker page component."""

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
    em,
    form,
    h1,
    h3,
    i,
    input_,
    label,
    span,
    table,
    tbody,
    td,
    tr,
)
from ._shared import back_link

_STATLINE_PARTIAL = "core/includes/list_fighter_weapon_profile_statline.html"
_HEADERS_PARTIAL = "core/includes/weapon_stat_headers.html"


def _statline(profile: Any, request: Any) -> Node:
    return raw(
        render_to_string(_STATLINE_PARTIAL, {"profile": profile}, request=request)
    )


def _weapon_tbody(weapon: dict[str, Any], request: Any) -> Node:
    eq = weapon["equipment"]
    rows: list[Node] = []

    for index, profile in enumerate(weapon["standard_profiles"]):
        first = index == 0
        if first and profile.name != "":
            rows.append(tr[td(colspan="9")[eq.name]])
        if first and profile.name == "":
            cell: Node = eq.name
        elif profile.name:
            cell = fragment[i(class_="bi-dash"), " ", profile.name]
        else:
            cell = None
        rows.append(
            tr(class_="align-top")[
                td(rowspan="2" if len(profile.traitline_cached) > 0 else "1")[cell],
                _statline(profile, request),
            ]
        )
        if len(profile.traitline_cached) > 0:
            rows.append(tr[td(colspan="8")[", ".join(profile.traitline_cached)]])

    for profile in weapon["non_standard_profiles"]:
        rows.append(
            tr(class_="align-top")[
                td(rowspan="2" if len(profile.traitline_cached) > 0 else "1")[
                    div(class_="form-check")[
                        input_(
                            type="checkbox",
                            name="weapon_profiles_field",
                            value=str(profile.id),
                            id=f"profile-{profile.id}",
                            form=f"weapon-{eq.id}",
                            class_="form-check-input",
                        ),
                        label(class_="form-check-label", for_=f"profile-{profile.id}")[
                            profile.name
                        ],
                    ]
                ],
                _statline(profile, request),
            ]
        )
        if len(profile.traitline_cached) > 0:
            rows.append(tr[td(colspan="8")[", ".join(profile.traitline_cached)]])

    rows.append(
        tr[
            td(colspan="9")[
                button(
                    type="submit",
                    class_="btn btn-outline-primary btn-sm",
                    form=f"weapon-{eq.id}",
                )[i(class_="bi-plus"), " Add ", eq.name]
            ]
        ]
    )

    return tbody(class_="table-group-divider")[tuple(rows)]


def _category_card(
    category_name: str, weapons: list[dict[str, Any]], add_url: str, request: Any
) -> Node:
    hidden_forms = tuple(
        form(
            action=add_url,
            method="post",
            id=f"weapon-{weapon['equipment'].id}",
            class_="d-none",
        )[
            CsrfInput(request),
            input_(
                type="hidden",
                name="content_equipment",
                value=str(weapon["equipment"].id),
            ),
        ]
        for weapon in weapons
    )
    return div(class_="card g-col-12 g-col-md-6")[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")[category_name]],
        div(class_="card-body vstack gap-2 p-0 p-sm-2")[
            hidden_forms,
            table(class_="table table-sm table-borderless mb-0 fs-7")[
                raw(
                    render_to_string(
                        _HEADERS_PARTIAL, {"first_col": "Weapons"}, request=request
                    )
                ),
                tuple(_weapon_tbody(weapon, request) for weapon in weapons),
            ],
        ],
    ]


@register_page("core/pack/pack_fighter_default_weapons_add.html")
def pack_fighter_default_weapons_add(context: dict[str, Any]) -> Page:
    request = context["request"]
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    categories = context["categories"]
    search_q = context["search_q"]
    error_message = context["error_message"]

    add_url = reverse(
        "core:pack-fighter-default-weapon-add", args=(pack.id, pack_item.id)
    )

    search = form(method="get", id="search")[
        div(class_="d-flex gap-2 align-items-center")[
            div(class_="input-group")[
                span(class_="input-group-text")[i(class_="bi-search")],
                input_(
                    type="search",
                    name="q",
                    value=search_q,
                    class_="form-control",
                    placeholder="Search weapons...",
                ),
                button(type="submit", class_="btn btn-primary")["Search"],
            ],
            a(href=add_url, class_="fs-7 text-nowrap")["Clear"] if search_q else None,
        ]
    ]

    if categories:
        grid_children: Node = tuple(
            _category_card(category_name, weapons, add_url, request)
            for category_name, weapons in categories.items()
        )
    else:
        grid_children = div(class_="g-col-12")[
            "No weapons found.",
            a(href=add_url)[em["Clear your search"]] if search_q else None,
        ]

    body = div(class_="col-12 col-xl-8 px-0 vstack gap-3")[
        h1(class_="h3")[f"Add default weapon: {content_fighter.type}"],
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]
        if error_message
        else None,
        raw("<!-- Search -->"),
        search,
        raw("<!-- Weapons by category -->"),
        div(class_="grid")[grid_children],
    ]

    content: Node = fragment[
        back_link(
            context,
            url=reverse(
                "core:pack-item-default-equipment", args=(pack.id, pack_item.id)
            ),
            text=content_fighter.type,
        ),
        body,
    ]

    return Page(
        title=f"Add default weapon - {content_fighter.type} - {pack.name}",
        content=content,
    )
