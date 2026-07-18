"""Campaign detail page component (port of ``core/campaign/campaign.html``).

A large read-mostly dashboard: header + info grid, then the Gangs, Assets,
Resources, Battles, Action Log and Captured Fighters sections. The many legacy
``{% include %}`` partials (campaign_lists, resource_row, battle_summary_card,
campaign_action_item, campaign_captured_fighters, notification_banners,
breadcrumb) are bridged through the Django template loader with the same
``with`` overrides the template passes; the page structure and inline markup are
reproduced as component nodes.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import escapejs

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    h2,
    h6,
    hr,
    i,
    input_,
    li,
    nav,
    p,
    script,
    section,
    span,
    strong,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
    ul,
)
from .. import bridge


def _url(name: str, *args: Any) -> str:
    return reverse(f"core:{name}", args=list(args))


@register_page("core/campaign/campaign.html")
def campaign_detail(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    request = context["request"]
    user = context.get("user")

    is_admin = context.get("is_admin", False)
    can_pin = context.get("can_pin", False)
    is_pinned = context.get("is_pinned", False)
    is_starred = context.get("is_starred", False)
    star_count = context.get("star_count", 0)
    can_impersonate_arbitrator = context.get("can_impersonate_arbitrator", False)
    campaign_packs = list(context.get("campaign_packs") or [])
    attribute_types = context.get("attribute_types")
    asset_types = context.get("asset_types")
    resource_types = context.get("resource_types")
    grouped_lists = context.get("grouped_lists")
    recent_battles = list(context.get("recent_battles") or [])
    battles_count = context.get("battles_count", 0)
    battles_limit = context.get("battles_limit", 0)
    can_log_actions = context.get("can_log_actions", False)
    has_cloning_lists = context.get("has_cloning_lists", False)

    authenticated = bool(user and user.is_authenticated)

    content: Node = fragment[
        _archived_banner(context, campaign, request, is_admin),
        div(class_="col-lg-12 px-0 vstack gap-4")[
            _header(
                context,
                campaign,
                request,
                user,
                authenticated,
                is_admin,
                can_pin,
                is_pinned,
                is_starred,
                star_count,
                can_impersonate_arbitrator,
                campaign_packs,
            ),
            _info_section(context, campaign, request, is_admin, campaign_packs),
            raw(
                render_to_string(
                    "core/includes/notification_banners.html",
                    {**context},
                    request=request,
                )
            ),
            _gangs_section(
                context, campaign, request, is_admin, attribute_types, grouped_lists
            ),
            div(class_="row g-5")[
                _assets_section(context, campaign, request, is_admin, asset_types),
                _resources_section(
                    context, campaign, request, is_admin, resource_types, grouped_lists
                ),
            ],
            div(class_="row g-5")[
                _battles_section(
                    context,
                    campaign,
                    request,
                    can_log_actions,
                    recent_battles,
                    battles_count,
                    battles_limit,
                ),
                _action_log_section(context, campaign, request, user, can_log_actions),
            ],
            _captured_section(context, campaign, request)
            if campaign.is_in_progress
            else None,
        ],
        _cloning_script(context) if has_cloning_lists else None,
    ]

    return Page(title=f"{campaign.name} - Campaign", content=content)


# ---------------------------------------------------------------------------
# Archived banner
# ---------------------------------------------------------------------------


def _archived_banner(context, campaign, request, is_admin) -> Node:
    if not campaign.archived:
        return None
    return div(class_="border rounded p-2 text-secondary mb-3")[
        i(class_="bi-archive"),
        " This campaign has been archived. ",
        form(
            action=_url("campaign-archive", campaign.id),
            method="post",
            class_="d-inline",
        )[
            CsrfInput(request),
            button(
                type="submit",
                name="archive",
                value="0",
                class_="btn btn-sm btn-secondary",
            )["Unarchive"],
        ]
        if is_admin
        else None,
    ]


# ---------------------------------------------------------------------------
# Header (breadcrumb, title + actions, visibility)
# ---------------------------------------------------------------------------


def _header(
    context,
    campaign,
    request,
    user,
    authenticated,
    is_admin,
    can_pin,
    is_pinned,
    is_starred,
    star_count,
    can_impersonate_arbitrator,
    campaign_packs,
) -> Node:
    breadcrumb = raw(
        render_to_string(
            "core/includes/breadcrumb.html",
            {
                "type": "Campaign",
                "owner": campaign.owner,
                "name": campaign.name,
                "type_url": _url("campaigns"),
            },
            request=request,
        )
    )

    return div(class_="vstack gap-0")[
        breadcrumb,
        div(
            class_="d-flex flex-column flex-md-row align-items-start "
            "align-items-md-center gap-2 mb-2"
        )[
            h1(class_="h2 mb-0")[campaign.name],
            div(class_="ms-md-auto d-flex gap-1 flex-nowrap align-items-center")[
                _pin_form(request, campaign, is_pinned) if can_pin else None,
                _star_form(request, campaign, is_starred, star_count),
                _admin_actions(campaign)
                if is_admin
                else _non_admin_actions(request, campaign, can_impersonate_arbitrator),
            ]
            if authenticated
            else None,
        ],
        div(class_="d-flex flex-wrap gap-2 text-secondary fs-7")[
            span(
                data_bs_toggle="tooltip",
                data_bs_title="This campaign is visible to all users",
            )[i(class_="bi-eye"), " Public"]
            if campaign.public
            else span(
                data_bs_toggle="tooltip",
                data_bs_title="This campaign can only be accessed by users "
                "with the direct link",
            )[i(class_="bi-eye-slash"), " Unlisted"]
        ],
    ]


def _pin_form(request, campaign, is_pinned) -> Node:
    return form(
        method="post", action=_url("campaign-pin", campaign.id), class_="d-inline"
    )[
        CsrfInput(request),
        button(
            type="submit",
            class_=["btn btn-sm", "btn-success" if is_pinned else "btn-secondary"],
            title=("Unpin" if is_pinned else "Pin") + " this campaign",
        )[
            i(class_="bi-pin-angle-fill" if is_pinned else "bi-pin-angle"),
            span(class_="visually-hidden")["Unpin" if is_pinned else "Pin"],
        ],
    ]


def _star_form(request, campaign, is_starred, star_count) -> Node:
    return form(
        method="post", action=_url("campaign-star", campaign.id), class_="d-inline"
    )[
        CsrfInput(request),
        button(
            type="submit",
            class_=[
                "btn btn-sm icon-link",
                "btn-warning" if is_starred else "btn-secondary",
            ],
            title=("Unstar" if is_starred else "Star") + " this campaign",
        )[
            i(class_="bi-star-fill" if is_starred else "bi-star"),
            " ",
            star_count if star_count else 0,
        ],
    ]


def _admin_actions(campaign) -> Node:
    if campaign.can_start_campaign():
        state_link = a(
            href=_url("campaign-start", campaign.id), class_="btn btn-primary btn-sm"
        )[i(class_="bi-play-circle"), " Start"]
    elif campaign.can_end_campaign():
        state_link = a(
            href=_url("campaign-end", campaign.id), class_="btn btn-danger btn-sm"
        )[i(class_="bi-stop-circle"), " End"]
    elif campaign.can_reopen_campaign():
        state_link = a(
            href=_url("campaign-reopen", campaign.id), class_="btn btn-primary btn-sm"
        )[i(class_="bi-arrow-clockwise"), " Reopen"]
    else:
        state_link = None

    if not campaign.archived:
        dropdown_head = fragment[
            li[h6(class_="dropdown-header")["Assets, Resources & Attributes"]],
            li[
                a(
                    class_="dropdown-item",
                    href=_url("campaign-copy-in", campaign.id),
                )[i(class_="bi-box-arrow-in-down"), " Copy to this Campaign"]
            ],
            li[
                a(
                    class_="dropdown-item",
                    href=_url("campaign-copy-out", campaign.id),
                )[i(class_="bi-box-arrow-up"), " Copy from this Campaign"]
            ],
            li[
                a(
                    class_="dropdown-item",
                    href=_url("campaign-attributes", campaign.id),
                )[i(class_="bi-tags"), " Attributes"]
            ],
            li[
                a(
                    class_="dropdown-item",
                    href=_url("campaign-packs", campaign.id),
                )[i(class_="bi-box-seam"), " Content Packs"]
            ],
            li[hr(class_="dropdown-divider")],
        ]
    else:
        dropdown_head = None

    return fragment[
        state_link,
        nav(class_="btn-group")[
            a(
                href=_url("campaign-edit", campaign.id),
                class_="btn btn-secondary btn-sm",
            )[i(class_="bi-pencil"), " Edit"],
            div(class_="btn-group", role="group")[
                button(
                    type="button",
                    class_="btn btn-secondary btn-sm dropdown-toggle",
                    data_bs_toggle="dropdown",
                    aria_expanded="false",
                    aria_label="More options",
                )[i(class_="bi-three-dots")],
                ul(class_="dropdown-menu dropdown-menu-end")[
                    dropdown_head,
                    li[
                        a(
                            class_="dropdown-item",
                            href=_url("campaign-archive", campaign.id),
                        )[
                            i(
                                class_="bi-box-arrow-up"
                                if campaign.archived
                                else "bi-archive"
                            ),
                            " ",
                            "Unarchive" if campaign.archived else "Archive",
                        ]
                    ],
                ],
            ],
        ],
    ]


def _non_admin_actions(request, campaign, can_impersonate_arbitrator) -> Node:
    return fragment[
        a(
            href=_url("campaign-copy-out", campaign.id),
            class_="icon-link linked-secondary fs-7",
        )[i(class_="bi-box-arrow-up"), " Copy from this Campaign"],
        form(
            method="post",
            action=_url("impersonate-start", campaign.owner.id),
            class_="d-inline m-0 ms-2",
        )[
            CsrfInput(request),
            input_(type="hidden", name="next", value=request.get_full_path()),
            button(type="submit", class_="btn btn-danger btn-sm")[
                i(class_="bi-person-bounding-box"), " Impersonate arbitrator"
            ],
        ]
        if can_impersonate_arbitrator
        else None,
    ]


# ---------------------------------------------------------------------------
# Campaign info section (status grid + summary/narrative)
# ---------------------------------------------------------------------------


def _info_section(context, campaign, request, is_admin, campaign_packs) -> Node:
    if campaign.is_pre_campaign:
        status = "Pre-Campaign"
    elif campaign.is_in_progress:
        status = "In Progress"
    elif campaign.is_post_campaign:
        status = "Post-Campaign"
    else:
        status = None

    grid_children: list[Node] = [
        div(class_="g-col-6 g-col-md-3")[
            div(class_="caps-label")["Status"],
            div[status],
        ],
        div(class_="g-col-6 g-col-md-3")[
            div(class_="caps-label")["Arbitrators"],
            div[
                a(
                    href=_url("user", campaign.owner.username),
                    class_="linked-body",
                )[campaign.owner],
                tuple(
                    fragment[
                        span[", "],
                        a(
                            href=_url("user", admin.username),
                            class_="linked-body",
                        )[admin],
                    ]
                    for admin in campaign.admins.all()
                ),
            ],
        ],
    ]

    if campaign.phase:
        grid_children.append(
            div(class_="g-col-6 g-col-md-3")[
                div(class_="caps-label")["Phase"],
                div[campaign.phase],
                div(class_="text-secondary fs-7")[
                    bridge.safe_rich_text(campaign.phase_notes)
                ]
                if campaign.phase_notes
                else None,
            ]
        )

    if campaign.budget > 0:
        grid_children.append(
            div(class_="g-col-6 g-col-md-3")[
                div(class_="caps-label")["Budget"],
                div[campaign.budget, "¢"],
            ]
        )

    if campaign_packs or is_admin:
        grid_children.append(
            div(class_="g-col-6 g-col-md-3")[
                div(class_="caps-label")["Content Packs"],
                _packs_body(campaign, request, is_admin, campaign_packs),
            ]
        )

    summary_block = None
    if campaign.summary or campaign.narrative:
        summary_block = div(class_="vstack gap-1 col-md-9")[
            div(class_="mb-last-0")[bridge.safe_rich_text(campaign.summary)]
            if campaign.summary
            else None,
            div(class_="text-secondary fs-7 mb-last-0")[
                bridge.safe_rich_text(campaign.narrative)
            ]
            if campaign.narrative
            else None,
        ]

    return div(class_="vstack gap-2")[
        div(class_="grid gap-3 border-bottom pb-3 mb-2")[tuple(grid_children)],
        summary_block,
    ]


def _packs_body(campaign, request, is_admin, campaign_packs) -> Node:
    if campaign_packs:
        pack_nodes: list[Node] = []
        last = len(campaign_packs) - 1
        for idx, pack in enumerate(campaign_packs):
            if pack.listed or pack.owner == request.user:
                name_node: Node = a(href=_url("pack", pack.id), class_="linked-body")[
                    pack.name
                ]
            else:
                name_node = span[pack.name]
            pack_nodes.append(
                fragment[
                    name_node,
                    span[", "] if idx != last else None,
                ]
            )
        return fragment[
            div[tuple(pack_nodes)],
            a(
                href=_url("campaign-packs", campaign.id),
                class_="fs-7 linked-secondary",
            )["Edit"]
            if is_admin
            else None,
        ]
    return fragment[
        div(class_="text-secondary")["None – any gang can join"],
        a(href=_url("campaign-packs", campaign.id), class_="fs-7 linked")["Add packs"],
    ]


# ---------------------------------------------------------------------------
# Gangs section
# ---------------------------------------------------------------------------


def _gangs_section(
    context, campaign, request, is_admin, attribute_types, grouped_lists
) -> Node:
    return section[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 "
            "bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")["Gangs"],
            div(class_="hstack gap-3")[
                a(
                    href=_url("campaign-attributes", campaign.id),
                    class_="linked fs-7",
                )["Manage Attributes →"]
                if attribute_types
                else None,
                a(
                    href=_url("campaign-add-lists", campaign.id),
                    class_="icon-link linked fs-7",
                )[i(class_="bi-plus-lg"), " Add Gangs"]
                if (
                    is_admin and not campaign.is_post_campaign and not campaign.archived
                )
                else None,
            ],
        ],
        div(class_="px-2")[
            raw(
                render_to_string(
                    "core/campaign/includes/campaign_lists.html",
                    {
                        **context,
                        "lists": campaign.lists.all(),
                        "pending_invitations": context.get("pending_invitations"),
                        "attribute_types": attribute_types,
                        "attribute_assignment_lookup": context.get(
                            "attribute_assignment_lookup"
                        ),
                        "grouped_lists": grouped_lists,
                    },
                    request=request,
                )
            )
        ],
    ]


# ---------------------------------------------------------------------------
# Assets section
# ---------------------------------------------------------------------------


def _assets_section(context, campaign, request, is_admin, asset_types) -> Node:
    return section(class_="col-xl-6")[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 "
            "bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")[
                "Assets",
                i(
                    class_="bi-info-circle text-secondary fs-6 ms-1",
                    data_bs_toggle="tooltip",
                    data_bs_title="Assets are physical items or locations that gangs "
                    "fight to control during the campaign.",
                ),
            ],
            a(href=_url("campaign-assets", campaign.id), class_="linked fs-7")[
                "Manage Assets →"
            ],
        ],
        div(class_="px-2")[_assets_body(campaign, request, is_admin, asset_types)],
    ]


def _assets_body(campaign, request, is_admin, asset_types) -> Node:
    if asset_types:
        blocks: list[Node] = []
        for idx, asset_type in enumerate(asset_types):
            blocks.append(
                div(class_="border-top pt-3 mt-3" if idx != 0 else None)[
                    div(class_="caps-label mb-2")[asset_type.name_plural],
                    _asset_type_body(campaign, request, is_admin, asset_type),
                ]
            )
        return fragment[tuple(blocks)]

    if is_admin and not campaign.archived:
        branch: Node = fragment[
            a(href=_url("campaign-copy-in", campaign.id), class_="linked")[
                "Copy from another Campaign"
            ],
            " or ",
            a(href=_url("campaign-asset-type-new", campaign.id), class_="linked")[
                "add an asset type →"
            ],
        ]
    elif is_admin:
        branch = a(href=_url("campaign-assets", campaign.id), class_="linked")[
            "Manage Assets →"
        ]
    else:
        branch = None
    return p(class_="text-secondary fs-7 mb-0")["No asset types defined yet. ", branch]


def _asset_type_body(campaign, request, is_admin, asset_type) -> Node:
    assets = list(asset_type.assets.all())
    if not assets:
        return p(class_="text-secondary fs-7 mb-0")[
            f"No {asset_type.name_plural.lower()} yet."
        ]
    return table(class_="table table-sm table-borderless mb-0 align-middle")[
        tbody[tuple(_asset_row(campaign, request, is_admin, asset) for asset in assets)]
    ]


def _asset_row(campaign, request, is_admin, asset) -> Node:
    from gyrinx.core.templatetags.custom_tags import property_nowrap_class

    name_node: Node = (
        a(
            href=_url("campaign-asset-detail", campaign.id, asset.id),
            class_="linked",
        )[asset.name]
        if request.user.is_authenticated
        else asset.name
    )

    holder_node: Node = (
        fragment[
            "Held by ",
            a(
                href=_url("list", asset.holder.id),
                class_="link-secondary link-underline-opacity-25 "
                "link-underline-opacity-100-hover",
            )[bridge.list_with_theme(asset.holder)],
        ]
        if asset.holder
        else "Unowned"
    )

    properties = None
    if asset.properties_with_labels:
        prop_labels = list(asset.properties_with_labels)
        prop_last = len(prop_labels) - 1
        properties = div(class_="fs-7 text-secondary")[
            tuple(
                span(class_=property_nowrap_class(label, value))[
                    f"{label}: {value}",
                    raw("&nbsp;·&nbsp;") if pidx != prop_last else None,
                ]
                for pidx, (label, value) in enumerate(prop_labels)
            )
        ]

    sub_counts = None
    if asset.sub_asset_counts:
        count_items = list(asset.sub_asset_counts)
        count_last = len(count_items) - 1
        sub_counts = div(class_="fs-7 text-secondary")[
            tuple(
                span(class_=property_nowrap_class(count, label))[
                    f"{count} {label}",
                    raw("&nbsp;·&nbsp;") if cidx != count_last else None,
                ]
                for cidx, (label, count) in enumerate(count_items)
            )
        ]

    return tr[
        td(class_="ps-0")[
            div(class_="fw-semibold")[name_node],
            div(class_="fs-7 text-secondary")[holder_node],
            properties,
            sub_counts,
            div(class_="fs-7 text-secondary text-clamp-2 mb-last-0")[
                bridge.safe_rich_text(asset.description)
            ]
            if asset.description
            else None,
        ],
        td(class_="text-end align-top text-nowrap")[
            a(
                href=_url("campaign-asset-transfer", campaign.id, asset.id)
                + "?return_url="
                + quote(request.get_full_path()),
                class_="icon-link linked fs-7",
            )[i(class_="bi-arrow-left-right"), " Transfer"]
            if (is_admin and not campaign.archived)
            else None
        ],
    ]


# ---------------------------------------------------------------------------
# Resources section
# ---------------------------------------------------------------------------


def _resources_section(
    context, campaign, request, is_admin, resource_types, grouped_lists
) -> Node:
    return section(class_="col-xl-6")[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 "
            "bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")[
                "Resources",
                i(
                    class_="bi-info-circle text-secondary fs-6 ms-1",
                    data_bs_toggle="tooltip",
                    data_bs_title="Resources are abstract commodities that gangs "
                    "accumulate during the campaign.",
                ),
            ],
            a(href=_url("campaign-resources", campaign.id), class_="linked fs-7")[
                "Manage Resources →"
            ],
        ],
        div(class_="px-2")[
            _resources_body(
                context, campaign, request, is_admin, resource_types, grouped_lists
            )
        ],
    ]


def _resources_body(
    context, campaign, request, is_admin, resource_types, grouped_lists
) -> Node:
    if resource_types and campaign.has_lists:
        return div(class_="table-responsive")[
            table(class_="table table-sm table-borderless mb-0 align-middle")[
                thead[
                    tr[
                        th(class_="caps-label")["Gang"],
                        tuple(
                            th(class_="caps-label text-end")[rt.name]
                            for rt in resource_types
                        ),
                    ]
                ],
                tbody[_resource_tbody(context, campaign, request, grouped_lists)],
            ]
        ]
    if resource_types:
        return p(class_="text-secondary fs-7 mb-0")[
            "Resource types are defined but no gangs have joined this campaign yet."
        ]

    if is_admin and not campaign.archived:
        branch: Node = fragment[
            a(href=_url("campaign-copy-in", campaign.id), class_="linked")[
                "Copy from another Campaign"
            ],
            " or ",
            a(href=_url("campaign-resource-type-new", campaign.id), class_="linked")[
                "add a resource type →"
            ],
        ]
    elif is_admin:
        branch = a(href=_url("campaign-resources", campaign.id), class_="linked")[
            "Manage Resources →"
        ]
    else:
        branch = None
    return p(class_="text-secondary fs-7 mb-0")[
        "No resource types defined yet. ", branch
    ]


def _resource_row(context, request, lst) -> Node:
    return raw(
        render_to_string(
            "core/campaign/includes/resource_row.html",
            {**context, "list": lst},
            request=request,
        )
    )


def _resource_tbody(context, campaign, request, grouped_lists) -> Node:
    if grouped_lists:
        rows: list[Node] = []
        for gidx, group in enumerate(grouped_lists):
            colour = group["colour"]
            rows.append(
                tr[
                    td(colspan="100", class_=["pt-3" if gidx != 0 else None, "pb-1"])[
                        div(class_="d-flex align-items-center gap-2")[
                            span(
                                class_="d-inline-block rounded-circle",
                                style=f"width: 10px; height: 10px; "
                                f"background-color: {colour}",
                            )
                            if colour
                            else None,
                            strong(class_="fs-7 text-uppercase text-secondary")[
                                group["name"]
                            ],
                        ],
                        hr(
                            class_="mt-1 mb-0",
                            style=f"border-color: {colour}; border-width: 2px; "
                            "opacity: 0.5"
                            if colour
                            else None,
                        ),
                    ]
                ]
            )
            for lst in group["lists"]:
                if not lst.is_cloning:
                    rows.append(_resource_row(context, request, lst))
        return fragment[tuple(rows)]

    return fragment[
        tuple(
            _resource_row(context, request, lst)
            for lst in campaign.lists.all()
            if not lst.is_cloning
        )
    ]


# ---------------------------------------------------------------------------
# Battles section
# ---------------------------------------------------------------------------


def _battles_section(
    context,
    campaign,
    request,
    can_log_actions,
    recent_battles,
    battles_count,
    battles_limit,
) -> Node:
    if recent_battles:
        body: Node = fragment[
            div(class_="vstack gap-2")[
                tuple(
                    raw(
                        render_to_string(
                            "core/includes/battle_summary_card.html",
                            {**context, "battle": battle},
                            request=request,
                        )
                    )
                    for battle in recent_battles
                )
            ],
            a(href=_url("campaign-battles", campaign.id), class_="fs-7")[
                f"View all {battles_count} battles →"
            ]
            if battles_count > battles_limit
            else None,
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")[
            "No battles yet. ",
            a(href=_url("battle-new", campaign.id), class_="linked")[
                "Create first battle →"
            ]
            if can_log_actions
            else None,
        ]

    return section(class_="col-xl-6")[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 "
            "bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")["Battles"],
            a(href=_url("battle-new", campaign.id), class_="icon-link linked fs-7")[
                i(class_="bi-plus-lg"), " New Battle"
            ]
            if can_log_actions
            else None,
        ],
        div(class_="px-2")[body],
    ]


# ---------------------------------------------------------------------------
# Action log section
# ---------------------------------------------------------------------------


def _action_log_section(context, campaign, request, user, can_log_actions) -> Node:
    recent_actions = list(campaign.actions.all()[:5])
    actions_count = campaign.actions.count()

    if recent_actions:
        body: Node = fragment[
            div(class_="vstack gap-2")[
                tuple(
                    raw(
                        render_to_string(
                            "core/includes/campaign_action_item.html",
                            {
                                **context,
                                "action": action,
                                "campaign": campaign,
                                "user": user,
                                "show_truncated": True,
                            },
                            request=request,
                        )
                    )
                    for action in recent_actions
                )
            ],
            a(
                href=_url("campaign-actions", campaign.id),
                class_="fs-7 mt-2 d-inline-block",
            )[f"View all {actions_count} actions →"]
            if actions_count > 5
            else None,
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")["No actions logged yet."]

    return section(class_="col-xl-6")[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 "
            "bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")[
                "Action Log",
                i(
                    class_="bi-info-circle text-secondary fs-6 ms-1",
                    data_bs_toggle="tooltip",
                    data_bs_title="The Action Log tracks all significant events and "
                    "activities that occur during the campaign.",
                ),
            ],
            div(class_="hstack gap-3")[
                a(
                    href=_url("campaign-action-new", campaign.id)
                    + "?return_url="
                    + quote(request.get_full_path()),
                    class_="icon-link linked fs-7",
                )[i(class_="bi-plus-lg"), " Log Action"]
                if (can_log_actions and not campaign.archived)
                else None,
                a(
                    href=_url("campaign-actions", campaign.id),
                    class_="linked fs-7",
                )["View all →"],
            ],
        ],
        div(class_="px-2")[body],
    ]


# ---------------------------------------------------------------------------
# Captured fighters section
# ---------------------------------------------------------------------------


def _captured_section(context, campaign, request) -> Node:
    return section[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 "
            "bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")["Captured Fighters"],
            a(
                href=_url("campaign-captured-fighters", campaign.id),
                class_="linked fs-7",
            )["View all →"],
        ],
        div(class_="px-2")[
            raw(
                render_to_string(
                    "core/includes/campaign_captured_fighters.html",
                    {
                        **context,
                        "campaign": campaign,
                        "captured_fighters": context.get("captured_fighters"),
                    },
                    request=request,
                )
            )
        ],
    ]


# ---------------------------------------------------------------------------
# Cloning-status poller (progressive enhancement)
# ---------------------------------------------------------------------------


def _cloning_script(context) -> Node:
    url = escapejs(context.get("cloning_status_url", ""))
    return script[
        raw(
            """
            (function () {
                var url = \""""
            + str(url)
            + """\";
                var INTERVAL = 4000;
                var MAX_ELAPSED = 300000; // give up polling after 5 minutes
                var elapsed = 0;
                var RELOAD_GUARD = "campaignCloningReloaded:" + url;

                function schedule() {
                    elapsed += INTERVAL;
                    if (elapsed < MAX_ELAPSED) {
                        window.setTimeout(poll, INTERVAL);
                    }
                }

                function poll() {
                    fetch(url, { headers: { "X-Requested-With": "XMLHttpRequest" } })
                        .then(function (response) {
                            return response.ok ? response.json() : null;
                        })
                        .then(function (data) {
                            if (!data) {
                                schedule();
                                return;
                            }
                            if (data.complete) {
                                if (!data.counts || data.counts.failed === 0) {
                                    var reloaded = false;
                                    try {
                                        reloaded = !!sessionStorage.getItem(RELOAD_GUARD);
                                        if (!reloaded) {
                                            sessionStorage.setItem(RELOAD_GUARD, "1");
                                        }
                                    } catch (e) {
                                    }
                                    if (!reloaded) {
                                        window.location.reload();
                                    }
                                }
                                return;
                            }
                            try {
                                sessionStorage.removeItem(RELOAD_GUARD);
                            } catch (e) {}
                            schedule();
                        })
                        .catch(schedule);
                }

                poll();
            })();
            """
        )
    ]
