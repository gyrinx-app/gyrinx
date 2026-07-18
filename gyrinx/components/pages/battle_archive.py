"""Battle archive / unarchive confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, input_, li, p, strong, ul
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/battle/battle_archive.html")
def battle_archive(context: dict[str, Any]) -> Page:
    battle = context["battle"]
    archived = battle.archived
    verb = "Unarchive" if archived else "Archive"

    if archived:
        question = "Are you sure you want to unarchive this battle?"
        explainer = _explainer(
            "What happens when you unarchive:",
            [
                "The battle shows in the Campaign's battle list again",
                "Its state and roles can be changed again",
            ],
        )
        submit = button(type="submit", class_="btn btn-primary")["Unarchive"]
        hidden: Node = None
    else:
        question = "Are you sure you want to archive this battle?"
        explainer = _explainer(
            "What happens when you archive:",
            [
                "The battle is hidden from the Campaign's battle list",
                "Its state and roles cannot be changed until you unarchive it",
                "You can unarchive it at any time",
            ],
        )
        submit = button(type="submit", class_="btn btn-danger")["Archive"]
        hidden = input_(type="hidden", name="archive", value="1")

    body = form(action=reverse("core:battle-archive", args=[battle.id]), method="post")[
        CsrfInput(context["request"]),
        div(class_="mt-3")[
            hidden,
            submit,
            cancel_link(context),
        ],
    ]

    content = fragment[
        back_link(
            context,
            url=reverse("core:battle", args=[battle.id]),
            text="Back to Battle",
        ),
        PageShell(
            h1(class_="h3")[f"{verb} {battle.name}"],
            p[question],
            explainer,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"{verb} {battle.name}", content=content)


def _explainer(heading: str, items: list[str]) -> Node:
    return div(class_="border rounded p-3 bg-body-secondary")[
        p(class_="mb-2")[strong[heading]],
        ul(class_="mb-0")[tuple(li[item] for item in items)],
    ]
