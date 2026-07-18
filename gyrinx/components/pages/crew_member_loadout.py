"""Crew member battle-loadout edit form page component."""

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


@register_page("core/crew/crew_member_loadout.html")
def crew_member_loadout(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    crew = context["crew"]
    battle = context["battle"]
    member = context["member"]
    request = context["request"]

    crew_url = reverse("core:crew", args=[battle.id, crew.id])

    body = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj.as_div())),
        div(class_="hstack gap-3 align-items-center")[
            button(type="submit", class_="btn btn-success")["Save loadout"],
            a(href=crew_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=crew_url, text="Back to Crew"),
        PageShell(
            h1(class_="h3")[f"{member.list_fighter.name} loadout"],
            p(class_="text-secondary")[
                "Choose which equipment set this fighter brings to ",
                battle.name,
                ". This only affects the crew's rating — the fighter keeps all "
                "their equipment on the gang.",
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"{member.list_fighter.name} loadout - {crew}",
        content=content,
    )
