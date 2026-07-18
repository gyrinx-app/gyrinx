"""Pack fighter equipment-list item remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, li, p, strong, ul
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_fighter_equipment_list_item_remove.html")
def pack_fighter_equipment_list_item_remove(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    eli = context["eli"]
    sibling_profiles = context["sibling_profiles"]
    request = context["request"]

    back_url = reverse("core:pack-item-equipment-list", args=[pack.id, pack_item.id])

    sibling_section: Node = None
    if sibling_profiles:
        sibling_section = fragment[
            p["The following weapon profiles will also be removed:"],
            ul(class_="mb-0")[
                tuple(
                    li[
                        sibling.equipment.name,
                        f" – {sibling.weapon_profile.name}"
                        if sibling.weapon_profile
                        else None,
                    ]
                    for sibling in sibling_profiles
                )
            ],
        ]

    content = fragment[
        back_link(context, url=back_url, text=content_fighter.type),
        PageShell(
            h1(class_="h3")["Remove from equipment list"],
            p[
                "Are you sure you want to remove ",
                strong[
                    eli.equipment.name,
                    f" – {eli.weapon_profile.name}" if eli.weapon_profile else None,
                ],
                " from the equipment list of ",
                strong[content_fighter.type],
                "?",
            ],
            sibling_section,
            form(
                action=reverse(
                    "core:pack-fighter-equipment-list-item-remove",
                    args=[pack.id, pack_item.id, eli.id],
                ),
                method="post",
            )[
                CsrfInput(request),
                div(class_="d-flex gap-2")[
                    button(type="submit", class_="btn btn-danger btn-sm")["Remove"],
                    a(href=back_url, class_="btn btn-link btn-sm")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove from equipment list - {content_fighter.type} - {pack.name}",
        content=content,
    )
