"""Battle end confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, p, strong
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/battle/battle_end.html")
def battle_end(context: dict[str, Any]) -> Page:
    battle = context["battle"]
    request = context["request"]

    battle_url = reverse("core:battle", args=[battle.id])

    body = form(action=reverse("core:battle-end", args=[battle.id]), method="post")[
        CsrfInput(request),
        p["Are you sure you want to end this battle?"],
        Alert(
            "Once ended, the battle moves from ",
            strong["In progress"],
            " to ",
            strong["Post-battle"],
            ". Battle states only move forward, so this cannot be undone.",
            variant="warning",
            class_="mb-0",
        ),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")["End battle"],
            cancel_link(context, url=battle_url),
        ],
    ]

    content: Node = fragment[
        back_link(context, url=battle_url, text="Back to Battle"),
        PageShell(
            h1(class_="h3")[f"End {battle.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"End {battle.name}", content=content)
