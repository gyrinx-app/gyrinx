"""Customise-weapon page component (port of core/pack/customise_weapon.html).

Shows the pack-scoped profiles for a library weapon and lets the pack author
add more. The profiles table is rendered through the shared weapon partials
(``weapon_stat_headers.html`` + ``weapon_profiles_display.html``) via the
template loader, so their branching logic isn't reimplemented here.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, h2, i, p, span, table, tbody
from ._shared import back_link


@register_page("core/pack/customise_weapon.html")
def customise_weapon(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    equipment = context["equipment"]
    profiles = context["profiles"]
    pack_profile_count = context["pack_profile_count"]
    archived_pack_profile_count = context["archived_pack_profile_count"]
    back_url = context["back_url"]
    request = context["request"]

    # Profiles table body: two shared partials rendered exactly as the legacy
    # template's {% include %}s (which inherit the full parent context plus the
    # ``with`` overrides).
    if profiles:
        profiles_body: Node = table(class_="table table-sm table-borderless mb-0 fs-7")[
            raw(
                render_to_string(
                    "core/includes/weapon_stat_headers.html",
                    {**context, "show_al": True},
                    request=request,
                )
            ),
            tbody(class_="table-group-divider")[
                raw(
                    render_to_string(
                        "core/pack/includes/weapon_profiles_display.html",
                        {
                            **context,
                            "profiles": profiles,
                            "weapon": equipment,
                            "can_edit": True,
                            "show_al": True,
                            "is_customised": True,
                            "show_actions_row": False,
                        },
                        request=request,
                    )
                )
            ],
        ]
    else:
        profiles_body = p(class_="text-secondary mb-0")["No profiles yet."]

    archived_link = (
        a(
            href=reverse(
                "core:pack-customise-weapon-archived-profiles",
                args=(pack.id, equipment.id),
            ),
            class_="linked-secondary fs-7",
        )[f"Archived profiles ({archived_pack_profile_count})"]
        if archived_pack_profile_count > 0
        else None
    )

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        div(class_="col-12 col-lg-8 col-xl-6 px-0 vstack gap-4")[
            div[
                h1(class_="h3 mb-1")[
                    i(class_="bi-crosshair"), " Customise ", equipment.name
                ],
                p(class_="text-secondary mb-0")[
                    "Add new profiles (e.g. special ammo) to this weapon. The weapon "
                    "itself isn't modified — your changes are scoped to this Content "
                    "Pack."
                ],
            ],
            div[
                div(class_="d-flex justify-content-between align-items-baseline mb-2")[
                    h2(class_="h5 mb-0")["Profiles"],
                    archived_link,
                ],
                profiles_body,
                p(class_="text-secondary fs-7 mt-2 mb-0")["No customisations yet."]
                if pack_profile_count == 0
                else None,
            ],
            div[
                h2(class_="h5 mb-2")["Add"],
                div(class_="row g-3")[
                    div(class_="col-12 col-md-6 col-lg-4")[
                        a(
                            href=reverse(
                                "core:pack-customise-weapon-profile-add",
                                args=(pack.id, equipment.id),
                            ),
                            class_="border rounded p-3 d-flex flex-column gap-1 text-decoration-none h-100",
                        )[
                            div(class_="d-flex align-items-center gap-2")[
                                i(class_="bi-plus-lg"),
                                span(class_="h6 mb-0")["New profile"],
                            ],
                            span(class_="text-secondary fs-7")[
                                "Add a special-ammo or alternate profile to this weapon."
                            ],
                        ]
                    ]
                ],
            ],
        ],
    ]
    return Page(
        title=f"Customise {equipment.name} - {pack.name}",
        content=content,
    )
