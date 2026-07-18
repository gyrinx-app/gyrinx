"""Weapon-profile archive (delete) confirmation page component."""

from __future__ import annotations

from typing import Any

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/weapon_profile_delete.html")
def weapon_profile_delete(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    equipment = context["equipment"]
    profile = context["profile"]
    back_url = context["back_url"]
    form_action_url = context["form_action_url"]
    request = context["request"]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")["Archive profile"],
            p[
                "Are you sure you want to archive the profile ",
                strong[profile.name],
                " from ",
                strong[equipment.name],
                "?",
            ],
            p(class_="text-secondary fs-7")["Archived items can be restored later."],
            form(action=form_action_url, method="post")[
                CsrfInput(request),
                div(class_="d-flex gap-2")[
                    button(type="submit", class_="btn btn-danger btn-sm")["Archive"],
                    a(href=back_url, class_="btn btn-link btn-sm")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Archive profile - {equipment.name} - {pack.name}",
        content=content,
    )
