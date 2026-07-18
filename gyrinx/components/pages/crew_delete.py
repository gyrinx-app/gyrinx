"""Crew delete confirmation page component (#1346)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, i, p
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/crew/crew_delete.html")
def crew_delete(context: dict[str, Any]) -> Page:
    crew = context["crew"]
    battle = context["battle"]

    crew_url = reverse("core:crew", args=[battle.id, crew.id])

    content = fragment[
        back_link(context, url=crew_url, text="Back to Crew"),
        PageShell(
            h1(class_="h3")[f"Delete {crew}"],
            form(
                action=reverse("core:crew-delete", args=[battle.id, crew.id]),
                method="post",
            )[
                CsrfInput(context["request"]),
                p[
                    "Are you sure you want to delete this crew? Its attendees and extras will be removed."
                ],
                div(class_="border rounded p-2")[
                    i(class_="bi-exclamation-triangle"),
                    " This does not affect the gang or its fighters — only this battle's crew.",
                ],
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-danger")["Delete crew"],
                    cancel_link(context, url=crew_url),
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Delete crew - {battle.name}", content=content)
