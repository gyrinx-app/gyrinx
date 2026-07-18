"""Pack "Your Campaigns" subscription-management page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    h2,
    input_,
    li,
    option,
    p,
    section,
    select,
    span,
    ul,
)
from ._shared import back_link


@register_page("core/pack/pack_campaigns.html")
def pack_campaigns(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    request = context["request"]
    unsubscribed_campaigns = context["unsubscribed_campaigns"]
    subscribed_campaigns = context["subscribed_campaigns"]

    add_section: Node = None
    if unsubscribed_campaigns:
        add_section = section[
            div(
                class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
            )[h2(class_="h5 mb-0")["Add to Campaign"]],
            div(class_="px-2")[
                form(
                    method="post",
                    action=reverse("core:pack-campaign-subscribe", args=[pack.id]),
                    class_="mb-3",
                )[
                    CsrfInput(request),
                    div(class_="d-flex gap-2 align-items-end")[
                        div(class_="flex-grow-1")[
                            select(
                                name="campaign_id",
                                id="campaign_id",
                                class_="form-select form-select-sm",
                            )[
                                tuple(
                                    option(value=campaign.id)[campaign.name]
                                    for campaign in unsubscribed_campaigns
                                )
                            ]
                        ],
                        button(type="submit", class_="btn btn-success btn-sm")[
                            "Add to Campaign"
                        ],
                    ],
                ]
            ],
        ]

    subscribed_section: Node = None
    if subscribed_campaigns:
        subscribed_section = section[
            div(
                class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
            )[
                h2(class_="h5 mb-0")[
                    "Subscribed Campaigns",
                    span(class_="badge text-bg-primary")[len(subscribed_campaigns)],
                ]
            ],
            div(class_="px-2")[
                ul(class_="list-unstyled mb-0")[
                    tuple(
                        li(
                            class_="py-2 d-flex justify-content-between align-items-center border-bottom"
                        )[
                            span[
                                a(
                                    href=reverse("core:campaign", args=[campaign.id]),
                                    class_="linked",
                                )[campaign.name]
                            ],
                            form(
                                method="post",
                                action=reverse(
                                    "core:pack-campaign-unsubscribe", args=[pack.id]
                                ),
                                class_="d-inline",
                            )[
                                CsrfInput(request),
                                input_(
                                    type="hidden",
                                    name="campaign_id",
                                    value=campaign.id,
                                ),
                                button(
                                    type="submit",
                                    class_="btn btn-link btn-sm link-danger link-underline-opacity-50 link-underline-opacity-100-hover p-0",
                                )["Remove"],
                            ],
                        ]
                        for campaign in subscribed_campaigns
                    )
                ]
            ],
        ]

    empty_message: Node = None
    if not unsubscribed_campaigns and not subscribed_campaigns:
        empty_message = p(class_="text-secondary fs-7 mb-0")[
            "You have no Campaigns to use with this Content Pack."
        ]

    content: Node = fragment[
        back_link(context, url=pack.get_absolute_url(), text=pack.name),
        div(class_="col-12 col-xl-6 px-0 vstack gap-4")[
            h1(class_="h3")["Your Campaigns"],
            p(class_="text-secondary fs-7")[
                "Manage which of your Campaigns use the ",
                pack.name,
                " Content Pack.",
            ],
            add_section,
            subscribed_section,
            empty_message,
        ],
    ]
    return Page(
        title=f"Your Campaigns - {pack.name}",
        content=content,
    )
