"""Return-captured-fighter-to-owner page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..design import Alert, CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, i, input_, label
from ._shared import back_link, cancel_link


@register_page("core/campaign/fighter_return_to_owner.html")
def fighter_return_to_owner(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    captured_fighter = context["captured_fighter"]
    return_url = context.get("return_url", "")
    request = context["request"]

    lst = captured_fighter.fighter.list
    credits_current = lst.credits_current
    max_ransom = 10000 if credits_current > 10000 else credits_current
    is_owner = request.user == lst.owner

    fighter_details = raw(
        render_to_string(
            "core/campaign/includes/captured_fighter_details.html",
            {
                "captured_fighter": captured_fighter,
                "show_original_gang_credits": True,
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
                h2(class_="h5 card-title")["Return Details"],
                div(class_="mb-3")[
                    label(for_="ransom", class_="form-label")[
                        "Ransom Amount (Credits)"
                    ],
                    input_(
                        type="number",
                        class_="form-control",
                        id="ransom",
                        name="ransom",
                        min="0",
                        max=max_ransom,
                        value="0",
                        placeholder="Enter ransom amount (optional)",
                    ),
                    div(class_="form-text")[
                        "Optional: The original gang will pay this amount to get "
                        "their fighter back. ",
                        "You currently have" if is_owner else "They currently have",
                        f" {credits_current}¢ available.",
                    ],
                ],
                Alert(
                    "The fighter will be returned to their original gang and can "
                    "participate in battles again.",
                    variant="info",
                    class_="mb-0",
                ),
                div(class_="d-flex gap-2")[
                    button(type="submit", class_="btn btn-primary")[
                        i(class_="bi-arrow-return-left"), " Return Fighter"
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
                h1(class_="h3 mb-0")["Return Fighter to Owner"],
                div(class_="text-secondary")[campaign.name],
            ],
            fighter_details,
            body,
        ],
    ]

    return Page(
        title=f"Return Fighter - {campaign.name}",
        content=content,
    )
