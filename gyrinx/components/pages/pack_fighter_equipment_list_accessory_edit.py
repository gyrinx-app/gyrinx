"""Pack fighter equipment-list weapon-accessory cost edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_fighter_equipment_list_accessory_edit.html")
def pack_fighter_equipment_list_accessory_edit(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    row = context["row"]
    request = context["request"]

    back_url = reverse("core:pack-item-equipment-list", args=(pack.id, pack_item.id))

    body = form(
        action=reverse(
            "core:pack-fighter-equipment-list-accessory-edit",
            args=(pack.id, pack_item.id, row.id),
        ),
        method="post",
    )[
        CsrfInput(request),
        div(class_="d-flex align-items-center gap-3")[
            label(for_="cost", class_="form-label mb-0 flex-grow-1")[
                row.weapon_accessory.name
            ],
            input_(
                type="number",
                name="cost",
                id="cost",
                value=str(row.cost),
                min="0",
                class_="form-control form-control-sm text-center w-em-5",
            ),
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text=content_fighter.type),
        PageShell(
            h1(class_="h3")["Edit accessory cost"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Edit accessory cost - {content_fighter.type} - {pack.name}",
        content=content,
    )
