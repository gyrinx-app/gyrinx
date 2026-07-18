"""Archived fighters listing page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, span, table, tbody, td, th, thead, tr
from ._shared import back_link


@register_page("core/list_archived_fighters.html")
def list_archived_fighters(context: dict[str, Any]) -> Page:
    lst = context["list"]

    rows: list[Node] = []
    for fighter in lst.archived_fighters():
        if not fighter.source_assignment.exists():
            action = td[
                a(
                    href=reverse(
                        "core:list-fighter-restore", args=[lst.id, fighter.id]
                    ),
                    class_="btn btn-link",
                )["Restore"]
            ]
        else:
            source_name = fighter.source_assignment.get().list_fighter.name
            action = td[
                span(
                    class_="btn btn-link link-secondary",
                    disabled=True,
                    bs_tooltip=True,
                    data_bs_toggle="tooltip",
                    title=(
                        f"This fighter is assigned to {source_name} "
                        "and cannot be restored directly"
                    ),
                )["Restore"]
            ]
        rows.append(
            tr(class_="align-middle")[
                td[fighter.fully_qualified_name],
                action,
            ]
        )

    if not rows:
        rows.append(tr[td(colspan=3, class_="text-center")["No archived fighters"]])

    content: Node = fragment[
        back_link(context, text=lst.name),
        div(class_="col-lg-12 px-0 vstack gap-3")[
            h1(class_="h3 mb-0")["Archived Fighters"],
            div(class_="table-responsive")[
                table(class_="table table-sm")[
                    thead[
                        tr[
                            th["Name"],
                            th,
                        ]
                    ],
                    tbody[tuple(rows)],
                ]
            ],
        ],
    ]
    return Page(
        title=f"Archived Fighters - {lst.name}",
        content=content,
    )
