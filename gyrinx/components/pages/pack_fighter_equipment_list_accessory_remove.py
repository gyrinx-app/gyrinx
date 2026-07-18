"""Pack fighter equipment-list accessory remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_fighter_equipment_list_accessory_remove.html")
def pack_fighter_equipment_list_accessory_remove(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    row = context["row"]
    request = context["request"]

    back_url = reverse("core:pack-item-equipment-list", args=(pack.id, pack_item.id))

    body: Node = PageShell(
        h1(class_="h3")["Remove from equipment list"],
        p[
            "Are you sure you want to remove ",
            strong[row.weapon_accessory.name],
            " from the equipment list of ",
            strong[content_fighter.type],
            "?",
        ],
        form(
            action=reverse(
                "core:pack-fighter-equipment-list-accessory-remove",
                args=(pack.id, pack_item.id, row.id),
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
    )

    content: Node = fragment[
        back_link(context, url=back_url, text=content_fighter.type),
        body,
    ]
    return Page(
        title=f"Remove from equipment list - {content_fighter.type} - {pack.name}",
        content=content,
    )
