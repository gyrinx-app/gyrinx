"""Pack fighter equipment tab page component.

Port of ``core/pack/pack_item_equipment.html`` — the combined default-equipment
and equipment-list tab for a fighter in a content pack. The three content
partials (fighter preview card, default equipment, equipment list) and the edit
tabs are bridged through the Django template loader with the same context the
legacy ``{% include %}`` tags pass.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div, h1, i
from ._shared import back_link


@register_page("core/pack/pack_item_equipment.html")
def pack_item_equipment(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    content_fighter = context["content_fighter"]
    back_url = context["back_url"]
    request = context["request"]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        div(class_="vstack gap-3")[
            h1(class_="h3")[i(class_="bi-person"), " Edit ", content_fighter.type],
            raw(
                render_to_string(
                    "core/pack/includes/pack_item_edit_tabs.html",
                    {**context, "active_tab": "equipment"},
                    request=request,
                )
            ),
        ],
        div(class_="row")[
            # Preview card (mobile: first, desktop: right column)
            div(class_="col-12 col-xl-5 order-xl-last mb-3 mb-xl-0 ps-xl-4")[
                raw(
                    render_to_string(
                        "core/pack/includes/fighter_preview_card.html",
                        context,
                        request=request,
                    )
                ),
            ],
            # Content (mobile: second, desktop: left column)
            div(class_="col-12 col-xl-7")[
                raw(
                    render_to_string(
                        "core/pack/includes/fighter_default_equipment.html",
                        context,
                        request=request,
                    )
                ),
                raw(
                    render_to_string(
                        "core/pack/includes/fighter_equipment_list.html",
                        context,
                        request=request,
                    )
                ),
            ],
        ],
    ]
    return Page(
        title=f"Edit {content_fighter.type} - {pack.name}",
        content=content,
    )
