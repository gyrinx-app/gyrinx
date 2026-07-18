"""Battle edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/battle/battle_edit.html")
def battle_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    battle = context["battle"]
    request = context["request"]
    battle_url = reverse("core:battle", args=[battle.id])

    non_field_errors = form_obj.non_field_errors()

    body = form(method="post", class_="vstack gap-3")[
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[raw(str(non_field_errors))],
        ]
        if non_field_errors
        else None,
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
            h1(class_="h3")["Edit Battle"],
            p(class_="text-secondary")[battle.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit Battle - {battle.name}", content=content)
