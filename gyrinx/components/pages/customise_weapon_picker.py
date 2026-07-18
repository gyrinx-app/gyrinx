"""Customise-existing-weapon picker page component (pack editor).

Port of ``core/pack/customise_weapon_picker.html``: a searchable, paginated
listing of library weapons the pack author can pick to attach custom profiles
to. The filter form, result table, and pagination are shared partials that are
bridged through the DjangoTemplates loader rather than rebuilt.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div, h1, i, p
from ._shared import back_link


@register_page("core/pack/customise_weapon_picker.html")
def customise_weapon_picker(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    request = context["request"]
    weapon_groups = context.get("weapon_groups")
    search_query = context.get("search_query", "")

    # The three {% include %}s (filter form, result table, pagination) are
    # shared partials that are hard to rebuild faithfully, so bridge them
    # through the DjangoTemplates loader with the same context (and the same
    # ``with`` override the table include uses).
    filter_form = raw(
        render_to_string(
            "core/pack/includes/weapon_picker_filter.html",
            context,
            request=request,
        )
    )

    if weapon_groups:
        results: Node = fragment[
            raw(
                render_to_string(
                    "core/pack/includes/weapon_picker_table.html",
                    {**context, "picker_mode": "weapon_link"},
                    request=request,
                )
            ),
            raw(
                render_to_string(
                    "core/includes/pagination.html",
                    context,
                    request=request,
                )
            ),
        ]
    else:
        results = p(class_="text-secondary mb-0")[
            f'No weapons match "{search_query}".'
            if search_query
            else "No weapons available to customise."
        ]

    content: Node = fragment[
        back_link(context, url=context["back_url"], text=pack.name),
        div(class_="col-12 col-lg-8 col-xl-6 px-0 vstack gap-3")[
            div[
                h1(class_="h3 mb-1")[
                    i(class_="bi-crosshair"), " Customise existing weapon"
                ],
                p(class_="text-secondary mb-0")[
                    "Pick an existing weapon to add new profiles to (e.g. special "
                    "ammo). The weapon itself stays untouched — only your custom "
                    "profiles are added."
                ],
            ],
            filter_form,
            results,
        ],
    ]
    return Page(
        title=f"Customise existing weapon - {pack.name}",
        content=content,
    )
