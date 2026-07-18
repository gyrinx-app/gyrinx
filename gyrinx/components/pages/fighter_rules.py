"""Fighter rules edit page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

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
    h3,
    i,
    input_,
    li,
    nav,
    span,
    table,
    tbody,
    td,
    tr,
    ul,
)


def _list_common_header(request: Any, lst: Any, fighter: Any) -> Node:
    """Port of the ``list_common_header.html`` include (rendered through the
    legacy loader with the same ``with`` overrides the template passes)."""
    return raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {
                "list": lst,
                "link_list": "true",
                "fighter": fighter,
                "fighter_url_name": "core:list-fighter-rules-edit",
            },
            request=request,
        )
    )


def _rules_card(title: str, rows: Node) -> Node:
    return div(class_="card")[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")[title]],
        div(class_="card-body p-0 p-sm-2")[
            div(class_="table-responsive")[
                table(class_="table table-borderless table-sm align-middle mb-0")[
                    tbody[rows]
                ]
            ]
        ],
    ]


def _default_rows(
    default_rules_display: Any, lst: Any, fighter: Any, request: Any
) -> Node:
    if not default_rules_display:
        return tr[
            td(colspan="2", class_="text-center text-secondary")[
                "No default rules for this fighter."
            ]
        ]

    rows = []
    for rule_data in default_rules_display:
        rule = rule_data["rule"]
        is_disabled = rule_data["is_disabled"]
        rows.append(
            tr(
                class_="text-decoration-line-through text-secondary"
                if is_disabled
                else ""
            )[
                td[rule.name],
                td(class_="text-end")[
                    form(
                        method="post",
                        action=reverse(
                            "core:list-fighter-rule-toggle",
                            args=[lst.id, fighter.id, rule.id],
                        ),
                        class_="d-inline",
                    )[
                        CsrfInput(request),
                        button(
                            type="submit",
                            class_=(
                                "btn btn-link icon-link fs-7 "
                                + ("link-success" if is_disabled else "link-danger")
                            ),
                        )[
                            fragment[i(class_="bi-check-lg"), " Enable"]
                            if is_disabled
                            else fragment[i(class_="bi-x-circle"), " Disable"]
                        ],
                    ]
                ],
            ]
        )
    return fragment[tuple(rows)]


def _custom_rows(custom_rules: Any, lst: Any, fighter: Any, request: Any) -> Node:
    rules = list(custom_rules)
    if not rules:
        return tr[
            td(colspan="2", class_="text-center text-secondary")[
                "No user-added rules for this fighter."
            ]
        ]

    rows = []
    for rule in rules:
        rows.append(
            tr[
                td[rule.name],
                td(class_="text-end")[
                    form(
                        method="post",
                        action=reverse(
                            "core:list-fighter-rule-remove",
                            args=[lst.id, fighter.id, rule.id],
                        ),
                        class_="d-inline",
                    )[
                        CsrfInput(request),
                        button(
                            type="submit",
                            class_="btn btn-link icon-link fs-7 link-danger",
                        )[i(class_="bi-trash"), " Remove"],
                    ]
                ],
            ]
        )
    return fragment[tuple(rows)]


def _available_item(rule: Any, lst: Any, fighter: Any, request: Any) -> Node:
    return div(class_="col-12 col-md-6")[
        div(
            class_="d-flex align-items-center justify-content-between p-2 border rounded"
        )[
            span[rule.name],
            form(
                method="post",
                action=reverse("core:list-fighter-rule-add", args=[lst.id, fighter.id]),
                class_="d-inline ms-2",
            )[
                CsrfInput(request),
                input_(type="hidden", name="rule_id", value=rule.id),
                button(type="submit", class_="btn btn-sm btn-outline-primary")[
                    i(class_="bi-plus-lg"), " Add"
                ],
            ],
        ]
    ]


def _available_rules(
    page_obj: Any, lst: Any, fighter: Any, request: Any, search_query: str
) -> Node:
    rules = list(page_obj)
    if rules:
        return div(class_="row g-2")[
            tuple(_available_item(rule, lst, fighter, request) for rule in rules)
        ]

    edit_url = reverse("core:list-fighter-rules-edit", args=[lst.id, fighter.id])
    if search_query:
        empty = fragment[
            f'No rules found matching "{search_query}".',
            a(href=edit_url)["Clear your search"],
            ".",
        ]
    else:
        empty = "No available rules found."
    return div(class_="row g-2")[
        div(class_="col-12")[div(class_="text-center text-secondary p-3")[empty]]
    ]


def _pagination(page_obj: Any, request: Any) -> Node:
    if page_obj.paginator.num_pages <= 1:
        return None

    items: list[Node] = []
    if page_obj.has_previous():
        items.append(
            li(class_="page-item")[
                a(
                    class_="page-link",
                    href=f"?{qt(request, page=page_obj.previous_page_number())}",
                )["Previous"]
            ]
        )
    for num in page_obj.paginator.page_range:
        if page_obj.number == num:
            items.append(li(class_="page-item active")[span(class_="page-link")[num]])
        elif num > page_obj.number - 3 and num < page_obj.number + 3:
            items.append(
                li(class_="page-item")[
                    a(class_="page-link", href=f"?{qt(request, page=num)}")[num]
                ]
            )
    if page_obj.has_next():
        items.append(
            li(class_="page-item")[
                a(
                    class_="page-link",
                    href=f"?{qt(request, page=page_obj.next_page_number())}",
                )["Next"]
            ]
        )

    return nav(aria_label="Rules pagination", class_="mt-3")[
        ul(class_="pagination pagination-sm justify-content-center mb-0")[tuple(items)]
    ]


@register_page("core/list_fighter_rules_edit.html")
def edit_list_fighter_rules(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]
    default_rules_display = context["default_rules_display"]
    custom_rules = context["custom_rules"]
    page_obj = context["page_obj"]
    search_query = context["search_query"]

    edit_url = reverse("core:list-fighter-rules-edit", args=[lst.id, fighter.id])

    search_form = form(method="get", action=edit_url, class_="mb-3")[
        div(class_="input-group")[
            input_(
                type="text",
                name="q",
                class_="form-control",
                placeholder="Search rules...",
                value=search_query,
            ),
            button(type="submit", class_="btn btn-primary")[
                i(class_="bi-search"), " Search"
            ],
            a(href=edit_url, class_="btn btn-secondary")[i(class_="bi-x"), " Clear"]
            if search_query
            else None,
        ]
    ]

    add_card = div(class_="card")[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")["Add Rules"]],
        div(class_="card-body p-2")[
            search_form,
            _available_rules(page_obj, lst, fighter, request, search_query),
            _pagination(page_obj, request),
        ],
    ]

    content: Node = fragment[
        _list_common_header(request, lst, fighter),
        div(class_="col-12 col-lg-8 px-0 vstack gap-3")[
            h1(class_="h3")[f"Rules: {fighter.fully_qualified_name}"],
            _rules_card(
                "Default Rules",
                _default_rows(default_rules_display, lst, fighter, request),
            ),
            _rules_card(
                "User-added Rules",
                _custom_rows(custom_rules, lst, fighter, request),
            ),
            add_card,
        ],
    ]
    return Page(
        title=f"Rules - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
