"""Campaign "Captured Fighters" display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import date as date_filter
from django.template.defaultfilters import urlencode as urlencode_filter
from django.urls import reverse
from django.utils.timezone import template_localtime

from .. import bridge
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    br,
    div,
    h1,
    i,
    small,
    span,
    strong,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)
from ._shared import back_link


@register_page("core/campaign/campaign_captured_fighters.html")
def campaign_captured_fighters(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    captured_fighters = context["captured_fighters"]
    is_admin = context.get("is_admin", False)
    request = context["request"]

    if captured_fighters:
        body: Node = div(class_="table-responsive")[
            table(class_="table table-hover")[
                thead[
                    tr[
                        th["Fighter"],
                        th["Original Gang"],
                        th["Captured By"],
                        th["Status"],
                        th["Captured Date"],
                        th["Actions"],
                    ]
                ],
                tbody[
                    tuple(
                        _row(campaign, is_admin, request, captured)
                        for captured in captured_fighters
                    )
                ],
            ]
        ]
    else:
        body = div(class_="alert alert-info alert-icon mb-0", role="alert")[
            i(class_="bi-info-circle"),
            div["No fighters have been captured in this campaign yet."],
        ]

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        div(class_="col-lg-12 px-0 vstack gap-3")[
            div(class_="vstack gap-0 mb-2")[
                div(class_="hstack gap-2 mb-2 align-items-start align-items-md-center")[
                    div(
                        class_="d-flex flex-column flex-md-row flex-grow-1 "
                        "align-items-start align-items-md-center gap-2"
                    )[h1(class_="h3 mb-0")["Captured Fighters"]],
                ],
                div(class_="text-secondary")[campaign.name],
            ],
            body,
        ],
    ]
    return Page(title=f"Captured Fighters - {campaign.name}", content=content)


def _row(campaign: Any, is_admin: bool, request: Any, captured: Any) -> Node:
    fighter = captured.fighter
    list_url = reverse("core:list", args=[fighter.list.id])

    if captured.sold_to_guilders:
        status: Node = fragment[
            span(class_="badge text-bg-secondary")["Sold to Guilders"],
            fragment[br, small[f"{captured.ransom_amount}¢"]]
            if captured.ransom_amount
            else None,
        ]
    else:
        status = span(class_="badge text-bg-warning")["Captured"]

    return tr[
        td[
            a(
                href=f"{list_url}#{fighter.id}",
                class_="link-underline-opacity-50 link-underline-opacity-100-hover",
            )[strong[fighter.name]],
            br,
            small(class_="text-secondary")[fighter.content_fighter.type],
        ],
        td[
            a(
                href=list_url,
                class_="link-underline-opacity-50 link-underline-opacity-100-hover",
            )[bridge.list_with_theme(fighter.list)],
        ],
        td[
            a(
                href=reverse("core:list", args=[captured.capturing_list.id]),
                class_="link-underline-opacity-50 link-underline-opacity-100-hover",
            )[bridge.list_with_theme(captured.capturing_list)],
        ],
        td[status],
        td[date_filter(template_localtime(captured.captured_at), "M d, Y")],
        td[_actions(campaign, is_admin, request, captured)],
    ]


def _actions(campaign: Any, is_admin: bool, request: Any, captured: Any) -> Node:
    if captured.sold_to_guilders:
        return span(class_="text-secondary")["—"]

    fighter = captured.fighter
    return_url = urlencode_filter(request.get_full_path())

    def action_url(name: str) -> str:
        return (
            reverse(name, args=[campaign.id, fighter.id]) + f"?return_url={return_url}"
        )

    sell = a(
        href=action_url("core:fighter-sell-to-guilders"),
        class_="btn btn-outline-secondary",
    )["Sell to Guilders"]
    return_to_owner = a(
        href=action_url("core:fighter-return-to-owner"),
        class_="btn btn-outline-secondary",
    )["Return to Owner"]
    release = a(
        href=action_url("core:fighter-release"),
        class_="btn btn-outline-secondary",
    )["Release"]

    if captured.capturing_list.owner == request.user or is_admin:
        return div(class_="btn-group btn-group-sm", role="group")[
            sell, return_to_owner, release
        ]
    if fighter.list.owner == request.user:
        return div(class_="btn-group btn-group-sm", role="group")[
            return_to_owner, release
        ]
    return span(class_="text-secondary")["Not your captive"]
