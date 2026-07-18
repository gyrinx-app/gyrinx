"""House-rule target picker page component (pack editor).

Port of ``core/pack/house_rule_picker.html`` — step 1 of the add-house-rule
flow. A target-type tab bar plus a searchable list of candidate targets:
either library weapons (``target_type == "weapon-profile"``) or fighters &
vehicles. The shared filter form, weapon table, pagination, and pack-mod view
line are bridged through the DjangoTemplates loader rather than rebuilt; the
fighter statline table (inline in the legacy template) is rebuilt with tags.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from gyrinx.core.templatetags.custom_tags import qt

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
    h2,
    i,
    input_,
    li,
    p,
    section,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
    ul,
)
from ._shared import back_link


def _nav_tabs(context: dict[str, Any]) -> Node:
    request = context["request"]
    target_type = context["target_type"]
    return ul(class_="nav nav-tabs")[
        tuple(
            li(class_="nav-item")[
                a(
                    class_=["nav-link", "active" if slug == target_type else None],
                    aria_current="page" if slug == target_type else None,
                    href="?"
                    + qt(request, target_type=slug, q=None, page=None, cat=None),
                )[label]
            ]
            for slug, label in context["target_choices"]
        )
    ]


def _fighter_row(context: dict[str, Any], row: dict[str, Any]) -> Node:
    request = context["request"]
    fighter = row["fighter"]
    has_rule = bool(row["rule_view"]["entries"])
    first_row = tr(class_="align-top")[
        td(rowspan="2" if has_rule else "1")[
            button(
                type="submit",
                name="target_id",
                value=fighter.id,
                class_="btn btn-link p-0 link-primary link-underline-opacity-25 link-underline-opacity-100-hover text-start",
            )[fighter.type],
            span(class_="text-secondary")["· ", fighter.house.name]
            if fighter.house
            else None,
        ],
        tuple(
            td(
                class_=[
                    "text-center",
                    "border-start" if (idx == 0 or cell["first_of_group"]) else None,
                ]
            )[cell["value"] or "-"]
            for idx, cell in enumerate(row["cells"])
        ),
    ]
    if not has_rule:
        return first_row
    second_row = tr[
        td(colspan=len(row["cells"]))[
            raw(
                render_to_string(
                    "core/pack/includes/pack_mod_view_line.html",
                    {**context, "view": row["rule_view"]},
                    request=request,
                )
            )
        ]
    ]
    return fragment[first_row, second_row]


def _statline_table(context: dict[str, Any], sub: dict[str, Any]) -> Node:
    return table(class_="table table-sm table-borderless mb-0 fs-7")[
        thead(class_="table-group-divider")[
            tr[
                th(scope="col")["Fighter"],
                tuple(
                    th(
                        class_=[
                            "text-center",
                            "border-start"
                            if (idx == 0 or col["first_of_group"])
                            else None,
                        ],
                        scope="col",
                    )[col["name"]]
                    for idx, col in enumerate(sub["columns"])
                ),
            ]
        ],
        tbody(class_="table-group-divider")[
            tuple(_fighter_row(context, row) for row in sub["rows"])
        ],
    ]


def _fighter_form(context: dict[str, Any]) -> Node:
    request = context["request"]
    target_type = context["target_type"]
    return form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        input_(type="hidden", name="target_type", value=target_type),
        tuple(
            section[
                div(
                    class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
                )[h2(class_="h5 mb-0")[group["category"]]],
                div(class_="px-2 vstack gap-2")[
                    tuple(
                        _statline_table(context, sub)
                        for sub in group["statline_groups"]
                    )
                ],
            ]
            for group in context["fighter_groups"]
        ),
    ]


@register_page("core/pack/house_rule_picker.html")
def house_rule_picker(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    request = context["request"]
    target_type = context["target_type"]
    search_query = context.get("search_query", "")

    # The filter form is a shared partial; bridge it through the DjangoTemplates
    # loader with the same ``with hidden_inputs=...`` override the include uses.
    filter_form = raw(
        render_to_string(
            "core/pack/includes/weapon_picker_filter.html",
            {**context, "hidden_inputs": context["filter_hidden_inputs"]},
            request=request,
        )
    )
    pagination = raw(
        render_to_string(
            "core/includes/pagination.html",
            context,
            request=request,
        )
    )

    if target_type == "weapon-profile":
        if context["weapon_groups"]:
            branch: Node = fragment[
                raw(
                    render_to_string(
                        "core/pack/includes/weapon_picker_table.html",
                        {
                            **context,
                            "picker_mode": "post",
                            "hidden_inputs": context["table_hidden_inputs"],
                        },
                        request=request,
                    )
                ),
                pagination,
            ]
        else:
            branch = p(class_="text-secondary mb-0")[
                f'No weapons match "{search_query}".'
                if search_query
                else "No weapons available."
            ]
    else:
        if context["fighter_groups"]:
            branch = fragment[_fighter_form(context), pagination]
        else:
            branch = p(class_="text-secondary mb-0")[
                f'No fighters match "{search_query}".'
                if search_query
                else "No fighters available."
            ]

    content: Node = fragment[
        back_link(context, url=context["back_url"], text=pack.name),
        div(class_="col-12 col-lg-8 col-xl-6 px-0 vstack gap-3")[
            div[
                h1(class_="h3 mb-1")[i(class_="bi-megaphone"), " Add house rule"],
                p(class_="text-secondary mb-0")[
                    "Pick what this house rule changes. The library content itself "
                    "isn't modified — Lists subscribed to this Content Pack will see "
                    "the modified stats wherever the target appears."
                ],
            ],
            _nav_tabs(context),
            filter_form,
            branch,
        ],
    ]
    return Page(title=f"Add house rule - {pack.name}", content=content)
