"""Sell-captured-fighter-to-guilders page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..design import Alert, CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, i, input_, label, strong
from ._shared import back_link, cancel_link


@register_page("core/campaign/fighter_sell_to_guilders.html")
def fighter_sell_to_guilders(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    captured_fighter = context["captured_fighter"]
    return_url = context.get("return_url", "")
    request = context["request"]

    fighter_details = raw(
        render_to_string(
            "core/campaign/includes/captured_fighter_details.html",
            {
                "captured_fighter": captured_fighter,
                "show_capturing_gang_owner_check": True,
            },
            request=request,
        )
    )

    body = form(method="post")[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None,
        div(class_="card")[
            div(class_="card-body")[
                h2(class_="h5 card-title")["Sale Details"],
                div(class_="mb-3")[
                    label(for_="credits", class_="form-label")["Sale Price (Credits)"],
                    input_(
                        type="number",
                        class_="form-control",
                        id="credits",
                        name="credits",
                        min="0",
                        max="10000",
                        value="0",
                        placeholder="Enter amount of credits",
                    ),
                    div(class_="form-text")[
                        "The amount of credits you'll receive for selling this fighter to the guilders."
                    ],
                ],
                div(class_="d-flex gap-2")[
                    button(type="submit", class_="btn btn-danger")[
                        i(class_="bi-coin"), " Sell to Guilders"
                    ],
                    cancel_link(context),
                ],
            ]
        ],
    ]

    content: Node = fragment[
        back_link(context, text="Back"),
        div(class_="col-12 col-md-8 col-lg-6 px-0")[
            div(class_="vstack gap-0 mb-3")[
                h1(class_="h3 mb-0")["Sell Fighter to Guilders"],
                div(class_="text-secondary")[campaign.name],
            ],
            fighter_details,
            Alert(
                strong["Warning:"],
                " Selling a fighter to the guilders is permanent. The fighter will be removed from play "
                "and cannot be recovered by their original gang.",
                variant="warning",
                class_="mb-0",
            ),
            body,
        ],
    ]

    return Page(
        title=f"Sell Fighter to Guilders - {campaign.name}",
        content=content,
    )
