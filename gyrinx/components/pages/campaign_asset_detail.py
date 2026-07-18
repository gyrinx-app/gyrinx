"""Campaign asset detail (read-only) page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import urlencode as urlencode_filter
from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import property_nowrap_class

from .. import bridge
from ..design import PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i, span, table, tbody, td, tr

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_asset_detail.html")
def campaign_asset_detail(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    asset = context["asset"]
    sub_assets_by_type = context["sub_assets_by_type"]
    is_admin = context.get("is_admin", False)
    request = context["request"]

    # The campaign context header is an un-ported include; bridge it through the
    # DjangoTemplates loader with the same ``with`` overrides the template passes.
    header = render_to_string(
        "core/includes/campaign_common_header.html",
        {
            **context,
            "campaign": campaign,
            "current": asset.name,
            "parent": asset.asset_type.name_singular,
        },
        request=request,
    )

    title_block = div[
        div(class_="caps-label text-secondary mb-1")[asset.asset_type.name_singular],
        h1(class_="h3 mb-0")[asset.name],
    ]

    shell = PageShell(
        title_block,
        _meta_row(request, campaign, asset, is_admin),
        _properties(asset),
        _sub_assets(sub_assets_by_type),
        div(class_="mb-last-0")[bridge.safe_rich_text(asset.description)]
        if asset.description
        else None,
        _about(asset),
        kind=FORM_SHELL,
    )

    content: Node = fragment[raw(header), shell]
    return Page(title=asset.name, content=content)


def _meta_row(request: Any, campaign: Any, asset: Any, is_admin: bool) -> Node:
    if asset.holder:
        holder = span(class_="text-secondary")[
            "Held by ",
            a(
                href=reverse("core:list", args=[asset.holder.id]),
                class_="link-secondary link-underline-opacity-25 link-underline-opacity-100-hover",
            )[bridge.list_with_theme(asset.holder)],
        ]
    else:
        holder = span(class_="text-secondary")["Unowned"]

    admin = None
    if is_admin and not campaign.archived:
        transfer_href = (
            reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id])
            + "?return_url="
            + urlencode_filter(request.get_full_path())
        )
        admin = span(class_="ms-auto d-flex gap-2")[
            a(href=transfer_href, class_="icon-link linked")[
                i(class_="bi-arrow-left-right", aria_hidden="true"),
                " Transfer",
            ],
            a(
                href=reverse("core:campaign-asset-edit", args=[campaign.id, asset.id]),
                class_="icon-link linked",
            )[
                i(class_="bi-pencil", aria_hidden="true"),
                " Edit",
            ],
        ]

    return div(class_="hstack gap-2 flex-wrap fs-7")[holder, admin]


def _properties(asset: Any) -> Node:
    props = asset.properties_with_labels
    if not props:
        return None
    return div[
        div(class_="caps-label mb-1")["Properties"],
        table(class_="table table-sm table-borderless mb-0")[
            tbody[
                tuple(
                    tr[
                        td(class_="ps-0 text-secondary w-em-10")[label],
                        td[value],
                    ]
                    for label, value in props
                )
            ]
        ],
    ]


def _sub_assets(sub_assets_by_type: Any) -> Node:
    if not sub_assets_by_type:
        return None
    return div(class_="border-top pt-3 vstack gap-3")[
        tuple(
            div[
                div(class_="caps-label mb-2")[label],
                div(class_="vstack gap-2")[
                    tuple(_sub_asset(sub_asset) for sub_asset in sub_assets)
                ],
            ]
            for label, sub_assets in sub_assets_by_type
        )
    ]


def _sub_asset(sub_asset: Any) -> Node:
    props = sub_asset.properties_with_labels
    props_node = None
    if props:
        last = len(props) - 1
        props_node = div(class_="fs-7 text-secondary")[
            tuple(
                span(class_=property_nowrap_class(plabel, pvalue))[
                    f"{plabel}: {pvalue}",
                    raw("&nbsp;·&nbsp;") if index != last else None,
                ]
                for index, (plabel, pvalue) in enumerate(props)
            )
        ]
    return div[
        div(class_="fw-semibold")[sub_asset.name],
        props_node,
    ]


def _about(asset: Any) -> Node:
    if not asset.asset_type.description:
        return None
    return div(class_="border-top pt-3")[
        div(class_="caps-label mb-1")[f"About {asset.asset_type.name_plural}"],
        div(class_="text-secondary fs-7 mb-last-0")[
            bridge.safe_rich_text(asset.asset_type.description)
        ],
    ]
