"""List clone page component (renders a Django form)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, p
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_clone.html")
def list_clone(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]

    body: Node = form(
        action=reverse("core:list-clone", args=[lst.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(context["request"]),
        raw(str(form_obj.media)),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Clone"],
            cancel_link(context),
        ],
    ]
    content = fragment[
        back_link(context),
        PageShell(
            h1(class_="h3")[f"Clone {lst.name}"],
            p[
                "Cloning a list will create a new list with the same fighters and settings."
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Clone {lst.name}", content=content)
