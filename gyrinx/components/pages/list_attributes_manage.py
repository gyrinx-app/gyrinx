"""Manage list attributes display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import urlencode
from django.urls import reverse

from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i, p, span, table, tbody, td, tr
from ._shared import back_link


@register_page("core/list_attributes_manage.html")
def manage_list_attributes(context: dict[str, Any]) -> Page:
    lst = context["list"]

    list_url = reverse("core:list", args=[lst.id])
    manage_url = reverse("core:list-attributes-manage", args=[lst.id])

    attributes = lst.all_attributes

    if attributes:
        body: Node = table(class_="table table-sm fs-7")[
            tbody[
                tuple(
                    tr[
                        td(class_="ps-0")[attribute["name"]],
                        td[
                            ", ".join(attribute["assignments"])
                            if attribute["assignments"]
                            else span(class_="text-secondary")["Not set"]
                        ],
                        td(class_="text-end pe-0")[
                            a(
                                href=reverse(
                                    "core:list-attribute-edit",
                                    args=[lst.id, attribute["id"]],
                                )
                                + "?return_url="
                                + urlencode(manage_url),
                                class_="icon-link link-secondary fs-7",
                            )[
                                i(class_="bi-pencil", aria_hidden="true"),
                                "Edit",
                            ]
                            if not lst.archived
                            else None
                        ],
                    ]
                    for attribute in attributes
                )
            ]
        ]
    else:
        body = p(class_="text-secondary")["No attributes available for this list."]

    content: Node = fragment[
        back_link(context, url=list_url, text="Back to list"),
        div(class_="row g-3 mb-3")[
            div(class_="col-lg-8")[
                h1(class_="h3")["Attributes"],
                body,
            ]
        ],
    ]
    return Page(
        title=f"Manage attributes - {lst.name}",
        content=content,
    )
