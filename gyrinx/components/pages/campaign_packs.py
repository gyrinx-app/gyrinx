"""Campaign content-packs management page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
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
    hr,
    i,
    input_,
    label,
    li,
    p,
    section,
    span,
    ul,
)
from ._shared import back_link

SHELL = "col-12 col-xl-6 px-0 vstack gap-4"


def _required_form(context: dict[str, Any], campaign: Any, pack: Any) -> Node:
    """Port of the arbitrator required-toggle form."""
    return form(
        method="post",
        action=reverse("core:campaign-pack-set-required", args=[campaign.id, pack.id]),
        class_="form-check form-switch mb-0",
    )[
        CsrfInput(context["request"]),
        input_(type="hidden", name="required", value="0"),
        input_(
            {"data-gy-toggle-submit": True},
            class_="form-check-input",
            type="checkbox",
            role="switch",
            id=f"required-{pack.id}",
            name="required",
            value="1",
            checked=pack.is_required,
        ),
        label(class_="form-check-label fs-7 mb-0", for_=f"required-{pack.id}")[
            "Required"
        ],
    ]


def _add_to_dropdown(context: dict[str, Any], campaign: Any, pack: Any) -> Node:
    """Port of the "Add to…" gang subscribe dropdown."""
    if pack.unsubscribed_user_lists:
        menu_items: Node = tuple(
            li[
                form(
                    method="post",
                    action=reverse("core:pack-subscribe", args=[pack.id]),
                )[
                    CsrfInput(context["request"]),
                    input_(type="hidden", name="list_id", value=lst.id),
                    input_(type="hidden", name="return_url", value="campaign-packs"),
                    input_(type="hidden", name="campaign_id", value=campaign.id),
                    button(type="submit", class_="dropdown-item")[lst.name],
                ]
            ]
            for lst in pack.unsubscribed_user_lists
        )
    else:
        menu_items = li[
            span(class_="dropdown-item-text text-secondary fs-7")[
                "All gangs subscribed"
            ]
        ]

    return div(class_="btn-group", role="group")[
        button(
            type="button",
            class_="btn btn-outline-primary btn-sm dropdown-toggle",
            data_bs_toggle="dropdown",
            aria_expanded="false",
        )["Add to…"],
        ul(class_="dropdown-menu dropdown-menu-end")[
            menu_items,
            li[hr(class_="dropdown-divider")],
            li[
                a(
                    href=reverse("core:pack-lists", args=[pack.id]),
                    class_="dropdown-item",
                )["Other…"]
            ],
        ],
    ]


def _allowed_pack_li(
    context: dict[str, Any],
    campaign: Any,
    pack: Any,
    *,
    can_edit_required: bool,
    user_campaign_lists: Any,
    can_modify: bool,
) -> Node:
    return li(
        class_="py-2 d-flex justify-content-between align-items-center gap-2 border-bottom"
    )[
        div[
            a(href=reverse("core:pack", args=[pack.id]), class_="linked fw-medium")[
                pack.name
            ],
            span(class_="text-secondary fs-7")["by ", pack.owner.username],
            span(class_="badge text-bg-warning ms-1")["Required"]
            if (pack.is_required and not can_edit_required)
            else None,
        ],
        div(class_="d-flex align-items-center gap-2")[
            _required_form(context, campaign, pack) if can_edit_required else None,
            _add_to_dropdown(context, campaign, pack) if user_campaign_lists else None,
            a(
                href=reverse("core:campaign-pack-remove", args=[campaign.id, pack.id]),
                class_="icon-link link-danger fs-7",
                aria_label=f"Remove {pack.name} from campaign",
            )[i(class_="bi-trash", aria_hidden="true")]
            if can_modify
            else None,
        ],
    ]


def _allowed_section(
    context: dict[str, Any],
    campaign: Any,
    campaign_packs: Any,
    *,
    is_admin: bool,
    can_edit_required: bool,
    user_campaign_lists: Any,
    can_modify: bool,
) -> Node:
    if campaign_packs:
        body: Node = ul(class_="list-unstyled mb-0")[
            tuple(
                _allowed_pack_li(
                    context,
                    campaign,
                    pack,
                    can_edit_required=can_edit_required,
                    user_campaign_lists=user_campaign_lists,
                    can_modify=can_modify,
                )
                for pack in campaign_packs
            )
        ]
    else:
        body = p(class_="text-secondary mb-0")[
            "No packs configured. Any gang can join regardless of their packs."
            if is_admin
            else "No Content Packs configured for this Campaign."
        ]

    return section[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
        )[
            h2(class_="h5 mb-0")[
                "Allowed Packs",
                span(class_="badge text-bg-primary")[len(campaign_packs)]
                if campaign_packs
                else None,
            ]
        ],
        div(class_="px-2")[body],
    ]


def _available_pack_li(context: dict[str, Any], campaign: Any, pack: Any) -> Node:
    return li(
        class_="py-2 d-flex justify-content-between align-items-center border-bottom"
    )[
        div[
            a(href=reverse("core:pack", args=[pack.id]), class_="linked fw-medium")[
                pack.name
            ],
            span(class_="text-secondary fs-7")["by ", pack.owner.username],
        ],
        form(
            method="post",
            action=reverse("core:campaign-pack-add", args=[campaign.id, pack.id]),
        )[
            CsrfInput(context["request"]),
            button(type="submit", class_="btn btn-sm btn-primary")["Add"],
        ],
    ]


def _add_section(
    context: dict[str, Any],
    campaign: Any,
    available_packs: Any,
    *,
    search_query: str,
    show_my_packs: bool,
) -> Node:
    search_form = form(method="get", class_="mb-3 vstack gap-2")[
        div(class_="input-group input-group-sm")[
            span(class_="input-group-text")[i(class_="bi-search")],
            input_(
                type="search",
                name="q",
                class_="form-control",
                placeholder="Search packs...",
                aria_label="Search packs",
                value=search_query,
            ),
            button(type="submit", class_="btn btn-primary btn-sm")["Search"],
            a(
                href=reverse("core:campaign-packs", args=[campaign.id]),
                class_="btn btn-outline-secondary",
            )["Clear"]
            if (search_query or show_my_packs)
            else None,
        ],
        div(class_="form-check form-switch mb-0")[
            input_(type="hidden", name="my", value="0"),
            input_(
                {"data-gy-toggle-submit": True},
                class_="form-check-input",
                type="checkbox",
                role="switch",
                id="my-packs",
                name="my",
                value="1",
                checked=show_my_packs,
            ),
            label(class_="form-check-label fs-7 mb-0", for_="my-packs")[
                "Your Packs only"
            ],
        ],
    ]

    if available_packs:
        results: Node = ul(class_="list-unstyled mb-0")[
            tuple(
                _available_pack_li(context, campaign, pack) for pack in available_packs
            )
        ]
    else:
        results = p(class_="text-secondary mb-0")[
            fragment['No packs found matching "', search_query, '".']
            if search_query
            else "No additional packs available."
        ]

    return section[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
        )[h2(class_="h5 mb-0")["Add Packs"]],
        div(class_="px-2")[search_form, results],
    ]


@register_page("core/campaign/campaign_packs.html")
def campaign_packs(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    campaign_packs_list = context["campaign_packs"]
    available_packs = context["available_packs"]
    is_admin = context["is_admin"]
    user_campaign_lists = context["user_campaign_lists"]
    search_query = context["search_query"]
    show_my_packs = context["show_my_packs"]
    can_edit_required = context["can_edit_required"]

    can_modify = is_admin and not campaign.archived and not campaign.is_post_campaign

    intro = (
        "Gangs joining this Campaign can use content from these packs and the "
        "core game content. Add packs below to restrict which packs can be used."
        if is_admin
        else fragment["Content Packs allowed in ", campaign.name, "."]
    )

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        PageShell(
            h1(class_="h3")["Content Packs"],
            p(class_="text-secondary fs-7")[intro],
            raw("<!-- Allowed packs -->"),
            _allowed_section(
                context,
                campaign,
                campaign_packs_list,
                is_admin=is_admin,
                can_edit_required=can_edit_required,
                user_campaign_lists=user_campaign_lists,
                can_modify=can_modify,
            ),
            raw("<!-- Add packs (owner only) -->"),
            _add_section(
                context,
                campaign,
                available_packs,
                search_query=search_query,
                show_my_packs=show_my_packs,
            )
            if can_modify
            else None,
            kind=SHELL,
        ),
    ]

    return Page(title=f"Content Packs - {campaign.name}", content=content)
