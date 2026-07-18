"""Battle roles assignment form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/battle/battle_roles.html")
def battle_roles(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    battle = context["battle"]
    request = context["request"]

    battle_url = reverse("core:battle", args=[battle.id])

    body = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="hstack gap-3 align-items-center")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=battle_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=battle_url, text="Back to Battle"),
        PageShell(
            h1(class_="h3")["Assign roles"],
            p(class_="text-secondary")[
                f"Give each gang a role in {battle.name} (e.g. Attacker or Defender)."
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Assign roles - {battle.name}", content=content)
