"""Campaign resources management/display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import urlencode
from django.urls import reverse

from .. import bridge
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    div,
    h1,
    h2,
    i,
    p,
    section,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)
from ._shared import back_link


@register_page("core/campaign/campaign_resources.html")
def campaign_resources(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    resource_types = context["resource_types"]
    is_admin = context["is_admin"]
    user_lists = context["user_lists"]
    request = context["request"]

    admin_actions: Node = None
    if is_admin:
        copy_link: Node = None
        if not campaign.archived:
            copy_link = a(
                href=reverse("core:campaign-copy-in", args=[campaign.id]),
                class_="icon-link linked-secondary fs-7",
            )[i(class_="bi-box-arrow-in-down"), " Copy from another Campaign"]
        admin_actions = div(class_="hstack gap-3 ms-md-auto")[
            copy_link,
            a(
                href=reverse("core:campaign-resource-type-new", args=[campaign.id]),
                class_="icon-link linked fs-7",
            )[i(class_="bi-plus-lg"), " Add Resource Type"],
        ]

    header = div[
        h1(class_="h3 mb-2")["Campaign Resources"],
        div(
            class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2"
        )[
            p(class_="text-secondary mb-0")[campaign.name],
            admin_actions,
        ],
    ]

    sections: list[Node] = [
        _section(campaign, resource_type, is_admin, user_lists, request)
        for resource_type in resource_types
    ]
    if not sections:
        sections = [_empty_state(campaign, is_admin)]

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        div(class_="col-12 px-0 vstack gap-4")[
            raw("<!-- Header -->"),
            header,
            tuple(sections),
        ],
    ]
    return Page(title=f"Campaign Resources - {campaign.name}", content=content)


def _section(
    campaign: Any,
    resource_type: Any,
    is_admin: bool,
    user_lists: Any,
    request: Any,
) -> Node:
    type_actions: Node = None
    if is_admin:
        type_actions = div(class_="hstack gap-3")[
            a(
                href=reverse(
                    "core:campaign-resource-type-edit",
                    args=[campaign.id, resource_type.id],
                ),
                class_="icon-link linked-secondary fs-7",
            )[i(class_="bi-pencil"), " Edit"],
            a(
                href=reverse(
                    "core:campaign-resource-type-remove",
                    args=[campaign.id, resource_type.id],
                ),
                class_="icon-link link-danger link-underline-opacity-50 link-underline-opacity-100-hover fs-7",
            )[i(class_="bi-trash"), " Remove"],
        ]

    description: Node = None
    if resource_type.description:
        description = div(class_="text-secondary fs-7 mb-3 mb-last-0")[
            bridge.safe_rich_text(resource_type.description)
        ]

    resources = list(resource_type.list_resources.all())
    if resources:
        body: Node = table(class_="table table-sm table-borderless mb-0 align-middle")[
            thead[
                tr[
                    th(class_="caps-label ps-0")["Gang"],
                    th(class_="caps-label text-end")["Amount"],
                    th(class_="caps-label text-end pe-0")["Actions"],
                ]
            ],
            tbody[
                tuple(
                    _resource_row(campaign, resource, is_admin, user_lists, request)
                    for resource in resources
                )
            ],
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")[
            "Resources will be allocated when the campaign starts."
            if campaign.is_pre_campaign
            else "No gangs have this resource yet."
        ]

    return section[
        div(class_="d-flex justify-content-between align-items-center mb-2")[
            h2(class_="h5 mb-0")[resource_type.name],
            type_actions,
        ],
        description,
        body,
    ]


def _resource_row(
    campaign: Any,
    resource: Any,
    is_admin: bool,
    user_lists: Any,
    request: Any,
) -> Node:
    if campaign.is_pre_campaign:
        actions: Node = span(class_="text-secondary fs-7")["Campaign not started"]
    elif (not campaign.archived and is_admin) or (
        not campaign.archived and resource.list in user_lists
    ):
        modify_url = (
            reverse("core:campaign-resource-modify", args=[campaign.id, resource.id])
            + "?return_url="
            + urlencode(request.get_full_path())
        )
        actions = a(href=modify_url, class_="icon-link linked-secondary fs-7")[
            i(class_="bi-pencil"), " Modify"
        ]
    else:
        actions = None

    return tr[
        td(class_="ps-0")[
            a(
                href=reverse("core:list", args=[resource.list.id]),
                class_="link-underline-opacity-50 link-underline-opacity-100-hover",
            )[bridge.list_with_theme(resource.list)]
        ],
        td(class_="text-end")[resource.amount],
        td(class_="text-end pe-0")[actions],
    ]


def _empty_state(campaign: Any, is_admin: bool) -> Node:
    return p(class_="text-secondary fs-7 mb-0")[
        "No resource types have been defined for this campaign yet.",
        a(href=reverse("core:campaign-resource-type-new", args=[campaign.id]))[
            "Create first resource type →"
        ]
        if is_admin
        else None,
    ]
