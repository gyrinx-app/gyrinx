"""Campaign assets management/display page component."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import property_nowrap_class

from .. import bridge
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    h1,
    h2,
    i,
    li,
    p,
    section,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
    ul,
)
from ._shared import back_link


@register_page("core/campaign/campaign_assets.html")
def campaign_assets(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    asset_types = context["asset_types"]
    is_admin = context["is_admin"]
    request = context["request"]

    sections: list[Node] = [
        _asset_type_section(campaign, asset_type, is_admin, request)
        for asset_type in asset_types
    ]
    if not sections:
        sections = [_no_asset_types(campaign, is_admin)]

    body = div(class_="col-12 px-0 vstack gap-4")[
        raw("<!-- Header -->"),
        div[
            h1(class_="h3 mb-2")["Campaign Assets"],
            div(
                class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2"
            )[
                p(class_="text-secondary mb-0")[campaign.name],
                _header_admin_links(campaign) if is_admin else None,
            ],
        ],
        tuple(sections),
    ]

    content = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        body,
    ]
    return Page(title=f"Campaign Assets - {campaign.name}", content=content)


def _header_admin_links(campaign: Any) -> Node:
    return div(class_="hstack gap-3 ms-md-auto fs-7")[
        a(
            href=reverse("core:campaign-asset-type-new", args=[campaign.id]),
            class_="icon-link linked",
        )[i(class_="bi-plus-lg"), " Add Asset Type"],
        "or",
        a(
            href=reverse("core:campaign-copy-in", args=[campaign.id]),
            class_="icon-link linked-secondary",
        )[i(class_="bi-box-arrow-in-down"), " Copy from another Campaign"]
        if not campaign.archived
        else None,
    ]


def _asset_type_section(
    campaign: Any, asset_type: Any, is_admin: bool, request: Any
) -> Node:
    assets = list(asset_type.assets.all())
    if assets:
        body: Node = table(class_="table table-sm table-borderless mb-0 align-middle")[
            thead[
                tr[
                    th(class_="caps-label ps-0")["Name"],
                    th(class_="caps-label w-em-10 w-em-sm-12")["Holder"],
                    th(class_="caps-label text-end pe-0 w-em-3 w-em-sm-12")[
                        span(class_="d-none d-sm-inline")["Actions"]
                    ]
                    if (is_admin and not campaign.archived)
                    else None,
                ]
            ],
            tbody[
                tuple(
                    _asset_row(campaign, asset, is_admin, request) for asset in assets
                )
            ],
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")[
            f"No {asset_type.name_plural.lower()} have been created yet.",
            a(
                href=reverse(
                    "core:campaign-asset-new", args=[campaign.id, asset_type.id]
                )
            )[f"Add {asset_type.name_singular} →"]
            if is_admin
            else None,
        ]

    return section[
        div(class_="d-flex justify-content-between align-items-center mb-2")[
            h2(class_="h5 mb-0")[asset_type.name_plural],
            _section_admin_links(campaign, asset_type) if is_admin else None,
        ],
        div(class_="text-secondary fs-7 mb-3 mb-last-0")[
            bridge.safe_rich_text(asset_type.description)
        ]
        if asset_type.description
        else None,
        body,
    ]


def _section_admin_links(campaign: Any, asset_type: Any) -> Node:
    edit_url = reverse(
        "core:campaign-asset-type-edit", args=[campaign.id, asset_type.id]
    )
    remove_url = reverse(
        "core:campaign-asset-type-remove", args=[campaign.id, asset_type.id]
    )
    return div(class_="hstack gap-3")[
        a(
            href=reverse("core:campaign-asset-new", args=[campaign.id, asset_type.id]),
            class_="icon-link linked fs-7",
        )[i(class_="bi-plus-lg"), f" Add {asset_type.name_singular}"],
        raw("<!-- Expanded links for sm and up -->"),
        a(
            href=edit_url,
            class_="icon-link linked-secondary fs-7 d-none d-sm-inline",
        )[i(class_="bi-pencil"), " Edit Type"],
        a(
            href=remove_url,
            class_="icon-link link-danger link-underline-opacity-50 link-underline-opacity-100-hover fs-7 d-none d-sm-inline",
        )[i(class_="bi-trash"), " Remove Type"],
        raw("<!-- Dropdown for mobile -->"),
        div(class_="dropdown d-sm-none")[
            button(
                class_="btn btn-sm btn-link text-secondary p-0",
                type="button",
                data_bs_toggle="dropdown",
                aria_expanded="false",
            )[i(class_="bi-three-dots-vertical")],
            ul(class_="dropdown-menu dropdown-menu-end")[
                li[
                    a(class_="dropdown-item", href=edit_url)[
                        i(class_="bi-pencil"), " Edit Type"
                    ]
                ],
                li[
                    a(class_="dropdown-item text-danger", href=remove_url)[
                        i(class_="bi-trash"), " Remove Type"
                    ]
                ],
            ],
        ],
    ]


def _asset_row(campaign: Any, asset: Any, is_admin: bool, request: Any) -> Node:
    name_cell = td(class_="ps-0")[
        div(class_="fw-semibold")[asset.name],
        div(class_="fs-7 text-secondary mb-last-0")[
            bridge.safe_rich_text(asset.description)
        ]
        if asset.description
        else None,
        _properties_div(asset) if asset.properties_with_labels else None,
        _sub_asset_counts_div(asset) if asset.sub_asset_counts else None,
    ]

    holder_cell = td(class_="fs-7")[
        a(
            href=reverse("core:list", args=[asset.holder.id]),
            class_="link-underline-opacity-50 link-underline-opacity-100-hover",
        )[bridge.list_with_theme(asset.holder)]
        if asset.holder
        else span(class_="text-secondary")["Unowned"]
    ]

    actions_cell = (
        _actions_cell(campaign, asset, request)
        if (is_admin and not campaign.archived)
        else None
    )

    return tr[name_cell, holder_cell, actions_cell]


def _dot_span(nowrap: str, text: str, last: bool) -> Node:
    # ``property_nowrap_class`` can return an empty string; the legacy template
    # renders ``class=""`` in that case, so emit the tag verbatim to preserve it.
    return fragment[
        raw(f'<span class="{nowrap}">'),
        text,
        None if last else raw("&nbsp;·&nbsp;"),
        raw("</span>"),
    ]


def _properties_div(asset: Any) -> Node:
    props = asset.properties_with_labels
    count = len(props)
    spans = [
        _dot_span(
            property_nowrap_class(label, value),
            f"{label}: {value}",
            idx == count - 1,
        )
        for idx, (label, value) in enumerate(props)
    ]
    return div(class_="fs-7 text-secondary")[tuple(spans)]


def _sub_asset_counts_div(asset: Any) -> Node:
    counts = asset.sub_asset_counts
    total = len(counts)
    spans = [
        _dot_span(
            property_nowrap_class(count, label),
            f"{count} {label}",
            idx == total - 1,
        )
        for idx, (label, count) in enumerate(counts)
    ]
    return div(class_="fs-7 text-secondary")[tuple(spans)]


def _actions_cell(campaign: Any, asset: Any, request: Any) -> Node:
    return_url = quote(request.get_full_path())
    transfer_url = (
        reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id])
        + "?return_url="
        + return_url
    )
    edit_url = reverse("core:campaign-asset-edit", args=[campaign.id, asset.id])
    remove_url = reverse("core:campaign-asset-remove", args=[campaign.id, asset.id])
    return td(class_="text-end pe-0 text-nowrap")[
        raw("<!-- Expanded links for sm and up -->"),
        span(class_="d-none d-sm-inline")[
            a(href=transfer_url, class_="linked-secondary fs-7")["Transfer"],
            "·",
            a(href=edit_url, class_="linked-secondary fs-7")["Edit"],
            "·",
            a(
                href=remove_url,
                class_="link-danger link-underline-opacity-50 link-underline-opacity-100-hover fs-7",
            )["Remove"],
        ],
        raw("<!-- Dropdown for mobile -->"),
        div(class_="dropdown d-sm-none d-inline-block")[
            button(
                class_="btn btn-sm btn-link text-secondary p-0",
                type="button",
                data_bs_toggle="dropdown",
                aria_expanded="false",
            )[i(class_="bi-three-dots-vertical")],
            ul(class_="dropdown-menu dropdown-menu-end")[
                li[
                    a(class_="dropdown-item", href=transfer_url)[
                        i(class_="bi-arrow-left-right"), " Transfer"
                    ]
                ],
                li[
                    a(class_="dropdown-item", href=edit_url)[
                        i(class_="bi-pencil"), " Edit"
                    ]
                ],
                li[
                    a(class_="dropdown-item text-danger", href=remove_url)[
                        i(class_="bi-trash"), " Remove"
                    ]
                ],
            ],
        ],
    ]


def _no_asset_types(campaign: Any, is_admin: bool) -> Node:
    return p(class_="text-secondary fs-7 mb-0")[
        "No asset types have been defined for this campaign yet.",
        a(href=reverse("core:campaign-asset-type-new", args=[campaign.id]))[
            "Create first asset type →"
        ]
        if is_admin
        else None,
    ]
