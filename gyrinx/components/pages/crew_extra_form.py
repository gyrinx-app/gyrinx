"""Crew extra (line item) add/edit form page component."""

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


@register_page("core/crew/crew_extra_form.html")
def crew_extra_form(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    crew = context["crew"]
    battle = context["battle"]
    item = context.get("item")
    request = context["request"]

    is_edit = item is not None
    heading = "Edit extra" if is_edit else "Add an extra"
    crew_url = reverse("core:crew", args=[battle.id, crew.id])

    body = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj.as_div())),
        div(class_="hstack gap-3 align-items-center")[
            button(type="submit", class_="btn btn-success")["Save extra"],
            a(href=crew_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=crew_url, text="Back to Crew"),
        PageShell(
            h1(class_="h3")[heading],
            p(class_="text-secondary")[
                "Extras are credit-consuming things attached to the crew — tactics "
                "cards, hired help, and the like. How they're paid for is recorded "
                "but no credits are moved."
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"{'Edit extra' if is_edit else 'Add extra'} - {crew}",
        content=content,
    )
