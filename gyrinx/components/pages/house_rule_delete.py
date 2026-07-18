"""House-rule archive confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, em, form, h1, p
from ._shared import back_link

SHELL = "col-12 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/house_rule_delete.html")
def house_rule_delete(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    request = context["request"]

    pack_url = reverse("core:pack", args=[pack.id])

    content: Node = fragment[
        back_link(context, url=pack_url, text=pack.name),
        PageShell(
            h1(class_="h3 mb-1")["Archive house rule"],
            p(class_="text-secondary mb-0")[
                "Are you sure you want to archive this house rule from ",
                em[pack.name],
                "? Lists subscribed to this Content Pack will "
                "stop seeing the modification on the next render.",
            ],
            form(method="post", class_="d-flex gap-2")[
                CsrfInput(request),
                button(type="submit", class_="btn btn-danger btn-sm")["Archive"],
                a(href=pack_url, class_="btn btn-secondary btn-sm")["Cancel"],
            ],
            kind=SHELL,
        ),
    ]
    return Page(
        title=f"Archive house rule - {pack.name}",
        content=content,
    )
