"""Release captured fighter confirmation page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..design import Alert, CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, i, input_, p, strong
from ._shared import back_link, cancel_link


@register_page("core/campaign/fighter_release.html")
def fighter_release(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    captured_fighter = context["captured_fighter"]
    request = context["request"]

    return_url = context.get("return_url", "")
    return_url_field: Node = (
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None
    )

    details = render_to_string(
        "core/campaign/includes/captured_fighter_details.html",
        {
            "captured_fighter": captured_fighter,
            "show_capturing_gang_owner_check": True,
        },
        request=request,
    )

    body = form(method="post")[
        CsrfInput(request),
        return_url_field,
        div(class_="card")[
            div(class_="card-body")[
                h2(class_="h5 card-title")["Confirm Release"],
                Alert(
                    strong["Are you sure you want to release this fighter?"],
                    p(class_="mb-0 mt-2")[
                        f"{captured_fighter.fighter.name} will be returned to "
                        f"{captured_fighter.fighter.list.name} without any ransom "
                        "or compensation. This action cannot be undone."
                    ],
                    variant="warning",
                    class_="mb-0",
                ),
                div(class_="d-flex gap-2")[
                    button(type="submit", class_="btn btn-primary")[
                        i(class_="bi-unlock"), " Release Fighter"
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
                h1(class_="h3 mb-0")["Release Fighter"],
                div(class_="text-secondary")[campaign.name],
            ],
            raw(details),
            body,
        ],
    ]
    return Page(
        title=f"Release Fighter - {campaign.name}",
        content=content,
    )
