"""Print-configuration index page component (list of a list's print configs)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i, p, span, strong, table, tbody, td, th, thead, tr

# The legacy shell class keeps ``px-0`` (unlike the ``form`` preset), so pass the
# exact class string as ``kind`` (PageShell falls back to the string verbatim).
FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _config_row(context: dict[str, Any], lst: Any, config: Any, is_owner: bool) -> Node:
    return tr(class_="align-middle")[
        td[strong[config.name]],
        td(class_="text-secondary")[config.card_summary()],
        td(class_="text-end")[
            div(class_="btn-group", role="group")[
                fragment[
                    a(
                        href=reverse(
                            "core:print-config-edit", args=[lst.id, config.id]
                        ),
                        class_="btn btn-outline-secondary btn-sm",
                    )[
                        i(class_="bi-pencil"),
                        "Edit",
                    ],
                    a(
                        href=reverse(
                            "core:print-config-delete", args=[lst.id, config.id]
                        ),
                        class_="btn btn-outline-danger btn-sm",
                    )[
                        i(class_="bi-trash"),
                        "Delete",
                    ],
                ]
                if is_owner
                else None,
                a(
                    href=reverse("core:print-config-print", args=[lst.id, config.id]),
                    class_="btn btn-primary btn-sm",
                )[
                    i(class_="bi-printer"),
                    "Print",
                ],
            ]
        ],
    ]


@register_page("core/print_config/index.html")
def print_config_index(context: dict[str, Any]) -> Page:
    lst = context["list"]
    is_owner = context["is_owner"]
    print_configs = context["print_configs"]
    request = context.get("request")

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {**context, "list": lst, "link_list": "true"},
            request=request,
        )
    )

    new_button: Node = (
        a(
            href=reverse("core:print-config-create", args=[lst.id]),
            class_="btn btn-primary btn-sm",
        )[
            i(class_="bi-plus"),
            "New Configuration",
        ]
        if is_owner
        else None
    )

    shell = PageShell(
        div(class_="d-flex justify-content-between align-items-center")[
            h1(class_="h3")["Print Configurations"],
            new_button,
        ],
        p(class_="text-secondary")[
            "Manage print configurations for ",
            strong[lst.name],
            ". Create custom configurations to control which cards and fighters "
            "are included when printing.",
        ],
        div(class_="table-responsive")[
            table(class_="table")[
                thead[
                    tr[
                        th["Name"],
                        th["Cards"],
                        th(class_="text-end")["Actions"],
                    ]
                ],
                tbody[
                    raw("<!-- Default configuration (always present) -->"),
                    tr(class_="align-middle")[
                        td[
                            strong["Default"],
                            span(class_="badge text-bg-secondary ms-2")["Built-in"],
                        ],
                        td(class_="text-secondary")["All cards and active fighters"],
                        td(class_="text-end")[
                            a(
                                href=reverse("core:list-print", args=[lst.id]),
                                class_="btn btn-primary btn-sm",
                            )[
                                i(class_="bi-printer"),
                                "Print",
                            ]
                        ],
                    ],
                    raw("<!-- User configurations -->"),
                    tuple(
                        _config_row(context, lst, config, is_owner)
                        for config in print_configs
                    ),
                ],
            ]
        ],
        kind=FORM_SHELL,
    )

    content: Node = fragment[header, shell]
    return Page(
        title=f"Print Configurations - {lst.name}",
        content=content,
    )
