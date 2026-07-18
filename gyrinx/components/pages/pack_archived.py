"""Pack archived-items listing page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import (
    button,
    div,
    form,
    h1,
    input_,
    li,
    p,
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

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _restore_form(request: Any, pack: Any, pack_item: Any, restore_next: Any) -> Node:
    return form(
        action=reverse("core:pack-restore-item", args=[pack.id, pack_item.id]),
        method="post",
        class_="d-inline",
    )[
        CsrfInput(request),
        input_(type="hidden", name="next", value=restore_next)
        if restore_next
        else None,
        button(type="submit", class_="btn btn-link btn-sm p-0 linked-secondary fs-7")[
            "Restore"
        ],
    ]


@register_page("core/pack/pack_archived.html")
def pack_archived(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    section_label = context["section_label"]
    skill_groups = context.get("skill_groups")
    archived_items = context.get("archived_items")
    restore_next = context.get("restore_next")
    request = context["request"]

    if skill_groups:
        body: Node = div(class_="vstack gap-3")[
            tuple(
                div[
                    div(class_="text-secondary text-uppercase fs-7 fw-semibold mb-1")[
                        group["category"].name
                    ],
                    ul(class_="list-unstyled mb-0")[
                        tuple(
                            li(
                                class_="py-1 d-flex justify-content-between align-items-center"
                            )[
                                span[entry["content_object"].name],
                                _restore_form(request, pack, entry["pack_item"], None),
                            ]
                            for entry in group["skills"]
                        )
                    ],
                ]
                for group in skill_groups
            )
        ]
    elif archived_items:
        body = table(class_="table table-sm table-borderless mb-0 align-middle")[
            thead[
                tr[
                    th(class_="caps-label ps-0")["Name"],
                    th(class_="caps-label text-end pe-0")["Actions"],
                ]
            ],
            tbody[
                tuple(
                    tr[
                        td(class_="ps-0")[entry["content_object"]],
                        td(class_="text-end pe-0")[
                            _restore_form(
                                request, pack, entry["pack_item"], restore_next
                            )
                        ],
                    ]
                    for entry in archived_items
                )
            ],
        ]
    else:
        body = p(class_="text-secondary")[f"No archived {section_label.lower()}."]

    content: Node = fragment[
        back_link(context, url=pack.get_absolute_url(), text=pack.name),
        PageShell(
            div[
                h1(class_="h3 mb-0")[f"Archived {section_label}"],
                p(class_="text-secondary mb-0")[pack.name],
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Archived {section_label} - {pack.name}",
        content=content,
    )
