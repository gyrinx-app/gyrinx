"""List campaign-invitations display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import date as date_filter
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import template_localtime

from ..design import CsrfInput
from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h5, p, small, span
from ._shared import back_link


@register_page("core/list/list_invitations.html")
def list_invitations(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]
    invitations = list(context.get("invitations") or [])

    if invitations:
        body: Node = div(class_="mb-3")[
            tuple(_invitation_card(request, lst, inv) for inv in invitations)
        ]
    else:
        clones = getattr(lst, "active_campaign_clones", None)
        show_clones_link = lst.is_list_building and bool(clones and len(clones))
        body = p[
            "No pending invitations.",
            a(
                href=reverse("core:list-campaign-clones", args=[lst.id]),
                class_="linked",
            )["See campaign gang versions of this list."]
            if show_clones_link
            else None,
        ]

    content: Node = div(class_="col-12 col-xl-6")[
        div(class_="mb-3")[
            back_link(context, url=reverse("core:list", args=[lst.id]), text=lst.name)
        ],
        h1(class_="h3")["Campaign Invitations"],
        body,
    ]
    return Page(title=f"Invitations - {lst.name}", content=content)


def _invitation_card(request: Any, lst: Any, invitation: Any) -> Node:
    campaign = invitation.campaign
    status = raw(
        render_to_string(
            "core/campaign/includes/status.html",
            {"campaign": campaign},
            request=request,
        )
    )
    return div(class_="border rounded p-3 mb-3")[
        div(class_="d-flex justify-content-between align-items-start mb-2")[
            div[
                h5(class_="mb-1")[
                    a(href=reverse("core:campaign", args=[campaign.id]))[campaign.name],
                    span(class_="fs-7")[status],
                ],
                p(class_="text-secondary mb-0")[
                    small["From: ", campaign.owner.username]
                ],
                p(class_="mt-2 mb-0")[invitation.message]
                if invitation.message
                else None,
            ],
            small(class_="text-secondary")[
                date_filter(template_localtime(invitation.created), "M d, Y")
            ],
        ],
        div(class_="mt-3")[
            form(
                method="post",
                action=reverse("core:invitation-accept", args=[lst.id, invitation.id]),
                class_="d-inline",
            )[
                CsrfInput(request),
                button(type="submit", class_="btn btn-success btn-sm")["Accept"],
            ],
            form(
                method="post",
                action=reverse("core:invitation-decline", args=[lst.id, invitation.id]),
                class_="d-inline ms-2",
            )[
                CsrfInput(request),
                button(type="submit", class_="btn btn-link text-secondary btn-sm")[
                    "Decline"
                ],
            ],
        ],
    ]
