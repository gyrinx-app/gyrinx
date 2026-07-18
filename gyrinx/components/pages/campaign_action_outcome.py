"""Campaign action-outcome edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .. import bridge
from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, i, input_, p, span, strong
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_action_outcome.html")
def campaign_action_outcome(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    action = context["action"]
    request = context["request"]
    return_url = context.get("return_url", "")

    card = div(class_="card")[
        div(class_="card-body")[
            p(class_="card-text")[bridge.list_with_theme(action.list)]
            if action.list
            else None,
            p(class_="card-text")[action.description],
            p(class_="card-text")[
                i(class_="bi-dice-6"),
                " Rolled ",
                action.dice_count,
                "D6",
                span(class_="ms-2")[
                    [
                        span(class_="badge text-bg-secondary")[result]
                        for result in action.dice_results
                    ],
                    " = ",
                    strong[action.dice_total],
                ],
            ]
            if action.dice_count > 0
            else None,
        ]
    ]

    body = form(
        action=reverse("core:campaign-action-outcome", args=[campaign.id, action.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None,
        FormField(form_obj["outcome"]),
        div(class_="mt-3 hstack gap-2")[
            button(type="submit", class_="btn btn-success", name="save")[
                "Save outcome"
            ],
            "or",
            button(type="submit", class_="btn btn-secondary", name="save_and_new")[
                "Save and log another action"
            ],
            cancel_link(context, text="Skip"),
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context, text="Back"),
        PageShell(
            h1(class_="h3")["Action Result"],
            h2(class_="h5 text-secondary")[campaign.name],
            card,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Action Outcome - {campaign.name}", content=content)
