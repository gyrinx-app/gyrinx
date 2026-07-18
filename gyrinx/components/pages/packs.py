"""Content-pack library ("Customisation") list page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import plain_text_truncate

from .. import bridge
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, br, div, h1, h2, i, p, span


def _pack_row(pack: Any) -> Node:
    """One pack in the main list (port of the ``{% for pack in packs %}`` body)."""
    return div(class_="hstack gap-3 position-relative")[
        div(class_="d-flex flex-column gap-1")[
            div(class_="hstack column-gap-2 row-gap-1 flex-wrap align-items-baseline")[
                h2(class_="mb-0 h5")[
                    a(href=reverse("core:pack", args=[pack.id]), class_="linked")[
                        pack.name
                    ]
                ],
                div[
                    i(class_="bi-person"),
                    " ",
                    a(
                        href=reverse("core:user", args=[pack.owner.username]),
                        class_="linked",
                    )[pack.owner],
                    bridge.user_badge(pack.owner),
                ],
                div[span(class_="badge text-bg-secondary")["Unlisted"]]
                if not pack.listed
                else None,
            ],
            div(class_="text-secondary")[plain_text_truncate(pack.summary, 150)]
            if pack.summary
            else None,
        ],
        div(class_="ms-auto d-md-none")[
            a(href=reverse("core:pack", args=[pack.id]), class_="p-3 stretched-link")[
                i(class_="bi-chevron-right")
            ]
        ],
    ]


@register_page("core/pack/packs.html")
def packs(context: dict[str, Any]) -> Page:
    request = context["request"]
    user = request.user
    packs_list = context.get("packs") or []
    featured_packs = context.get("featured_packs")

    # {% include packs_filter.html with action=action %} — action is the packs URL.
    packs_filter = raw(
        render_to_string(
            "core/includes/packs_filter.html",
            {"action": reverse("core:packs")},
            request=request,
        )
    )
    # {% include pagination.html %} — inherits is_paginated / page_obj / request.
    pagination = raw(
        render_to_string(
            "core/includes/pagination.html",
            {
                "is_paginated": context.get("is_paginated"),
                "page_obj": context.get("page_obj"),
            },
            request=request,
        )
    )

    if packs_list:
        pack_rows: Node = fragment[tuple(_pack_row(pack) for pack in packs_list)]
    else:
        pack_rows = div(class_="py-2")["No content packs available."]

    featured_column: Node = None
    if featured_packs:
        featured_column = div(class_="col-12 col-xl-4 order-1 order-xl-2")[
            div(class_="caps-label mb-2")["Featured"],
            div(class_="vstack gap-2")[
                tuple(
                    raw(
                        render_to_string(
                            "core/includes/featured_pack_card.html",
                            {"pack": pack},
                            request=request,
                        )
                    )
                    for pack in featured_packs
                )
            ],
        ]

    content: Node = div(class_="col-lg-12 px-0 vstack gap-4")[
        div[
            h1(class_="mb-1")["Customisation"],
            p(class_="fs-5 col-12 col-md-6 mb-0")[
                "Browse and manage Content Packs.",
                fragment[
                    br,
                    a(href=reverse("core:packs-new"), class_="linked")[
                        "Create a new Content Pack"
                    ],
                    ".",
                ]
                if user.is_authenticated
                else None,
            ],
        ],
        div(class_="row g-4")[
            div(class_="col-12 col-xl-8 order-2 order-xl-1")[
                div(class_="vstack gap-4")[
                    packs_filter,
                    pack_rows,
                    pagination,
                ]
            ],
            featured_column,
        ],
    ]

    return Page(title="Customisation", content=content)
