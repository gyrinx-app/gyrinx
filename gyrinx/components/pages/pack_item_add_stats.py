"""Pack add-fighter step 2 (stat entry) form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, dd, div, dl, dt, form, h1, i, input_, label, span, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _category_alert(category: str) -> Node:
    """Port of the ``{% if params.category == ... %}`` info alerts."""
    if category == "VEHICLE":
        return div(class_="alert alert-info alert-icon mb-0", role="alert")[
            i(class_="bi-info-circle", aria_hidden="true"),
            div[
                "Saving will also create a matching equipment entry under ",
                strong["Vehicles"],
                " so subscribed lists can buy this Vehicle. The cost stays in sync"
                " with the fighter's base cost.",
            ],
        ]
    if category == "EXOTIC_BEAST":
        return div(class_="alert alert-info alert-icon mb-0", role="alert")[
            i(class_="bi-info-circle", aria_hidden="true"),
            div[
                "Saving will also create a matching equipment entry under ",
                strong["Status Items"],
                " so subscribed Fighters can buy this Exotic Beast. The cost stays"
                " in sync with the fighter's base cost.",
            ],
        ]
    return None


@register_page("core/pack/pack_item_add_stats.html")
def pack_item_add_stats(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    params = context["params"]
    stat_definitions = context["stat_definitions"]
    query_string = context["query_string"]
    house_name = context["house_name"]
    category_display = context["category_display"]
    back_url = context["back_url"]
    request = context["request"]

    summary = div(class_="border rounded p-2")[
        dl(class_="row mb-0 fs-7")[
            dt(class_="col-4 text-secondary")["Name"],
            dd(class_="col-8 mb-1")[params.type],
            dt(class_="col-4 text-secondary")["Category"],
            dd(class_="col-8 mb-1")[category_display],
            dt(class_="col-4 text-secondary")["House"],
            dd(class_="col-8 mb-1")[house_name],
            dt(class_="col-4 text-secondary")["Base cost"],
            dd(class_="col-8 mb-0")[params.base_cost, "¢"],
        ]
    ]

    stat_inputs = div(class_="d-flex flex-wrap gap-2")[
        tuple(
            div(class_="text-center stat-input-cell")[
                label(class_="form-label fs-7 mb-1")[stat["short_name"]],
                input_(
                    type="text",
                    name=f"stat_{stat['field_name']}",
                    value=stat["value"] or "",
                    class_="form-control form-control-sm text-center",
                    placeholder=stat["placeholder"],
                    maxlength="10",
                ),
            ]
            for stat in stat_definitions
        )
    ]

    body = form(
        action=reverse("core:pack-add-fighter-stats", args=[pack.id])
        + "?"
        + query_string,
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        div[
            label(class_="form-label")["Stats"],
            stat_inputs,
            div(class_="form-text")['Set each stat value, or leave as "-" for unset.'],
        ],
        div(class_="mt-3 d-flex gap-2 align-items-center")[
            button(type="submit", class_="btn btn-success")[
                i(class_="bi-check-lg me-1"), " Add ", params.type
            ],
            span["or"],
            button(
                type="submit", name="save_and_add_another", class_="btn btn-secondary"
            )["Add and create another"],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")[
                i(class_="bi-person"), " Configure stats for ", params.type
            ],
            summary,
            _category_alert(params.category),
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Configure stats for {params.type} ({pack.name})",
        content=content,
    )
