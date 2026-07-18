"""New-list create form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .. import bridge
from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, input_
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _selected_packs_block(selected_packs: list[Any], change_packs_url: str) -> Node:
    """Port of the ``{% if selected_packs %}`` content-packs summary block."""
    if not selected_packs:
        return None

    names: list[Any] = []
    for idx, pack in enumerate(selected_packs):
        names.append(pack.name)
        if idx < len(selected_packs) - 1:
            names.append(" , ")

    return div(class_="border rounded p-3")[
        div(class_="d-flex justify-content-between align-items-center mb-1")[
            div(class_="text-secondary text-uppercase fs-7")[
                i(class_="bi-box-seam"), " Content Packs"
            ],
            a(href=change_packs_url, class_="link-secondary fs-7")["Change"],
        ],
        div[tuple(names)],
    ]


@register_page("core/list_new.html")
def list_new(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    request = context["request"]
    selected_packs = list(context.get("selected_packs") or [])
    pack_ids = list(context.get("pack_ids") or [])
    change_packs_url = context.get("change_packs_url")

    body = form(
        action=reverse("core:lists-new"),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        tuple(input_(type="hidden", name="packs", value=pid) for pid in pack_ids),
        raw(str(form_obj.media)),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Create"],
            a(
                href=bridge.safe_referer(request, "/lists/"),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context),
        PageShell(
            h1(class_="h3")["Create a new List"],
            _selected_packs_block(selected_packs, change_packs_url),
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title="New List", content=content)
