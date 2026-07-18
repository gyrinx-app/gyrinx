"""Pack item archive confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_item_delete.html")
def pack_item_delete(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_obj = context["content_obj"]
    label = context["label"]
    back_url = context["back_url"]
    request = context["request"]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")[f"Archive {label}"],
            p[
                "Are you sure you want to archive ",
                strong[content_obj],
                " from ",
                strong[pack.name],
                "?",
            ],
            p(class_="text-secondary fs-7")["Archived items can be restored later."],
            form(
                action=reverse("core:pack-delete-item", args=[pack.id, pack_item.id]),
                method="post",
            )[
                CsrfInput(request),
                div(class_="d-flex gap-2")[
                    button(type="submit", class_="btn btn-danger btn-sm")["Archive"],
                    a(href=back_url, class_="btn btn-link btn-sm")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Archive {label} - {pack.name}",
        content=content,
    )
