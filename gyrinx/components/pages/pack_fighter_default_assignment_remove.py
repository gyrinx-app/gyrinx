"""Pack fighter default-assignment remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_fighter_default_assignment_remove.html")
def pack_fighter_default_assignment_remove(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    assignment = context["assignment"]
    request = context["request"]

    back_url = reverse("core:pack-item-default-equipment", args=(pack.id, pack_item.id))

    body: Node = PageShell(
        h1(class_="h3")["Remove default equipment"],
        p[
            "Are you sure you want to remove ",
            strong[assignment.equipment.name],
            " from the default equipment of ",
            strong[content_fighter.type],
            "?",
        ],
        div(class_="border border-warning rounded p-3 bg-warning bg-opacity-10")[
            p(class_="mb-0")[
                i(class_="bi-exclamation-triangle text-warning"),
                " ",
                strong["Warning:"],
                " This will immediately affect all Fighters based on this template."
                " Removing this default equipment means new Fighters will no longer"
                " receive it when hired. Existing Fighters that already have this"
                " equipment will not be changed.",
            ],
        ],
        form(
            action=reverse(
                "core:pack-fighter-default-assignment-remove",
                args=(pack.id, pack_item.id, assignment.id),
            ),
            method="post",
        )[
            CsrfInput(request),
            div(class_="d-flex gap-2")[
                button(type="submit", class_="btn btn-danger btn-sm")["Remove"],
                a(href=back_url, class_="btn btn-link btn-sm")["Cancel"],
            ],
        ],
        kind=FORM_SHELL,
    )

    content: Node = fragment[
        back_link(context, url=back_url, text=content_fighter.type),
        body,
    ]
    return Page(
        title=f"Remove default equipment - {content_fighter.type} - {pack.name}",
        content=content,
    )
