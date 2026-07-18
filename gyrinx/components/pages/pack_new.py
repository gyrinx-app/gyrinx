"""New content pack create form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .. import bridge
from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_new.html")
def pack_new(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    request = context["request"]

    body = form(action=reverse("core:packs-new"), method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Create"],
            a(href=bridge.safe_referer(request, "/packs/"), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context),
        PageShell(
            h1(class_="h3")["Create a new Content Pack"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title="New Content Pack", content=content)
