"""Campaign "Add Gangs" page component (search + add lists to a campaign)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from .. import bridge
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
    h5,
    i,
    input_,
    label,
    li,
    p,
    section,
    span,
    strong,
    table,
    tbody,
    td,
    tr,
    ul,
)
from ._shared import back_link


@register_page("core/campaign/campaign_add_lists.html")
def campaign_add_lists(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    request = context["request"]
    add_lists_url = reverse("core:campaign-add-lists", args=[campaign.id])

    error_message = context.get("error_message")
    error_alert = (
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]
        if error_message
        else None
    )

    pack_confirmation = None
    if context.get("show_pack_confirmation") and context.get("pack_confirm_list"):
        pack_confirmation = _pack_confirmation(context, add_lists_url)

    campaign_gangs = None
    current_lists = context.get("current_lists")
    pending_invitations = context.get("pending_invitations")
    if current_lists or pending_invitations:
        campaign_gangs = section[
            h2(class_="h5 mb-2")["Campaign Gangs"],
            raw(
                render_to_string(
                    "core/campaign/includes/campaign_lists.html",
                    {
                        **context,
                        "lists": current_lists,
                        "pending_invitations": pending_invitations,
                    },
                    request=request,
                )
            ),
        ]

    pagination = raw(
        render_to_string("core/includes/pagination.html", {**context}, request=request)
    )

    body = div(class_="col-12 px-0 vstack gap-4")[
        raw("<!-- Header -->"),
        div[
            h1(class_="h3 mb-1")["Add Gangs"],
            p(class_="text-secondary mb-0")[campaign.name],
        ],
        error_alert,
        pack_confirmation,
        raw("<!-- Current Gangs -->"),
        campaign_gangs,
        raw("<!-- Search -->"),
        _search_section(context, add_lists_url),
        raw("<!-- Available Lists -->"),
        _available_section(context),
        pagination,
    ]

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        body,
    ]
    return Page(title=f"Add Gangs - {campaign.name}", content=content)


def _pack_confirmation(context: dict[str, Any], add_lists_url: str) -> Node:
    request = context["request"]
    pack_confirm_list = context["pack_confirm_list"]
    packs = context.get("pack_confirm_packs") or []
    return div(class_="border border-warning rounded p-3")[
        h5(class_="mb-2")[
            i(class_="bi-box-seam text-warning"),
            " Content Packs Required",
        ],
        p(class_="mb-2")[
            strong[bridge.list_with_theme(pack_confirm_list)],
            " uses Content Packs not yet added to this Campaign:",
        ],
        ul(class_="mb-2")[tuple(li[pack.name] for pack in packs)],
        p(class_="text-secondary fs-7 mb-3")[
            "Adding these packs to the Campaign will allow this and other gangs "
            "using them to join."
        ],
        div(class_="d-flex gap-2")[
            form(method="post", action=add_lists_url)[
                CsrfInput(request),
                input_(type="hidden", name="list_id", value=pack_confirm_list.id),
                input_(type="hidden", name="add_packs", value="true"),
                button(type="submit", class_="btn btn-success btn-sm")[
                    i(class_="bi-plus-lg"), " Add Packs & Gang"
                ],
            ],
            a(href=add_lists_url, class_="btn btn-secondary btn-sm")["Cancel"],
        ],
    ]


def _search_section(context: dict[str, Any], add_lists_url: str) -> Node:
    request = context["request"]
    owner = request.GET.get("owner")
    q_value = request.GET.get("q", "")

    clear_link = (
        a(href="?#search", class_="btn btn-outline-secondary")["Clear"]
        if request.GET.get("q")
        else None
    )

    packs_switch = None
    if context.get("has_campaign_packs"):
        packs_switch = div(class_="form-check form-switch ms-2")[
            input_(
                class_="form-check-input",
                type="checkbox",
                id="packs-filter",
                name="packs",
                value="matching",
                checked=request.GET.get("packs") == "matching",
                data_gy_toggle_submit="search",
            ),
            label(class_="form-check-label fs-7", for_="packs-filter")[
                "Matching Content Packs"
            ],
        ]

    return section[
        form(
            id="search",
            method="get",
            action=add_lists_url + "#search",
            class_="vstack gap-3",
        )[
            input_(type="hidden", name="flash", value="search"),
            div(class_="input-group")[
                span(class_="input-group-text")[i(class_="bi-search")],
                input_(
                    class_="form-control",
                    type="search",
                    placeholder="Search by name, house, or owner",
                    aria_label="Search",
                    name="q",
                    value=q_value,
                ),
                button(class_="btn btn-primary", type="submit")["Search"],
                clear_link,
            ],
            div(class_="hstack gap-2")[
                div(class_="btn-group", role="group")[
                    input_(
                        type="radio",
                        class_="btn-check",
                        data_gy_toggle_submit="search",
                        name="owner",
                        id="owner-all",
                        value="all",
                        checked=(not owner) or owner == "all",
                    ),
                    label(class_="btn btn-outline-primary btn-sm", for_="owner-all")[
                        "All Gangs"
                    ],
                    input_(
                        type="radio",
                        class_="btn-check",
                        data_gy_toggle_submit="search",
                        name="owner",
                        id="owner-mine",
                        value="mine",
                        checked=owner == "mine",
                    ),
                    label(class_="btn btn-outline-primary btn-sm", for_="owner-mine")[
                        "Your Gangs"
                    ],
                    input_(
                        type="radio",
                        class_="btn-check",
                        data_gy_toggle_submit="search",
                        name="owner",
                        id="owner-others",
                        value="others",
                        checked=owner == "others",
                    ),
                    label(class_="btn btn-outline-primary btn-sm", for_="owner-others")[
                        "Others' Gangs"
                    ],
                ],
                packs_switch,
            ],
        ]
    ]


def _available_section(context: dict[str, Any]) -> Node:
    request = context["request"]
    lists = context.get("lists")

    if lists:
        inner: Node = table(class_="table table-sm mb-0 align-middle")[
            tbody[tuple(_available_row(lst, request, context) for lst in lists)]
        ]
    else:
        q = request.GET.get("q")
        owner = request.GET.get("owner") or "all"
        message = (
            "No gangs found matching your search criteria."
            if (q or owner != "all")
            else "No gangs available to add."
        )
        inner = p(class_="text-secondary fs-7 mb-0")[message]

    # The legacy template renders ``<section class="{% flash %}">``; when the
    # flash tag is inactive it still emits ``class=""`` (an empty attribute),
    # which the component's class handling would otherwise drop. Emit the tag
    # verbatim so both the active and inactive cases stay byte-faithful.
    flash_val = "flash-warn" if request.GET.get("flash") == "search" else ""
    return fragment[
        raw(f'<section class="{flash_val}">'),
        h2(class_="h5 mb-2")["Available Gangs"],
        inner,
        raw("</section>"),
    ]


def _available_row(lst: Any, request: Any, context: dict[str, Any]) -> Node:
    campaign = context["campaign"]
    add_lists_url = reverse("core:campaign-add-lists", args=[campaign.id])

    house_span = None
    if lst.content_house:
        house_span = span(class_="text-secondary fw-normal")[
            "· ",
            lst.content_house_name,
            bridge.house_icon(lst.content_house_cached),
        ]

    packs_div = None
    packs = list(lst.packs.all())
    if packs:
        pack_nodes: list[Node] = []
        for index, pack in enumerate(packs):
            if index:
                pack_nodes.append(" , ")
            pack_nodes.append(pack.name)
        packs_div = div(class_="fs-7 text-secondary")[
            i(class_="bi-box-seam"),
            " ",
            tuple(pack_nodes),
        ]

    owner_text = "Your gang" if lst.owner == request.user else lst.owner.username

    return tr[
        td(class_="ps-0")[
            div(class_="fw-semibold")[
                a(
                    href=reverse("core:list", args=[lst.id]),
                    target="_blank",
                    rel="noopener",
                    class_="link-underline-opacity-50 link-underline-opacity-100-hover",
                )[bridge.list_with_theme(lst)],
                house_span,
            ],
            div(class_="fs-7 text-secondary")[
                owner_text,
                " · R: ",
                bridge.credits(lst.rating_current),
                " Cr: ",
                bridge.credits(lst.credits_current),
                " St: ",
                bridge.credits(lst.stash_current),
                " W: ",
                bridge.credits(lst.wealth_current),
            ],
            packs_div,
        ],
        td(class_="text-end")[
            form(method="post", action=add_lists_url)[
                CsrfInput(request),
                input_(type="hidden", name="list_id", value=lst.id),
                button(type="submit", class_="btn btn-outline-primary btn-sm")[
                    i(class_="bi-plus-lg"), " Add"
                ],
            ]
        ],
    ]
