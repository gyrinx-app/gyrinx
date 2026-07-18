"""Content-pack edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_edit.html")
def pack_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    pack = context["pack"]
    request = context["request"]

    body = form(
        action=reverse("core:pack-edit", args=[pack.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=reverse("core:pack", args=[pack.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context),
        PageShell(
            h1(class_="h3")["Edit Content Pack"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit {pack.name}", content=content)
