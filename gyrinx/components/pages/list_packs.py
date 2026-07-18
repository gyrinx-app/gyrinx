"""List content-pack subscription-management page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import join, striptags, truncatewords
from django.template.loader import render_to_string
from django.urls import reverse

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
    i,
    input_,
    label,
    li,
    p,
    section,
    span,
    ul,
)


def _pack_name(pack: Any, request: Any) -> Node:
    """Port of the shared name link/span branch."""
    if pack.listed or pack.owner == request.user:
        return a(href=reverse("core:pack", args=[pack.id]), class_="linked fw-medium")[
            pack.name
        ]
    return span(class_="fw-medium")[pack.name]


def _pack_summary(pack: Any) -> Node:
    if pack.summary:
        return div(class_="text-secondary fs-7")[
            truncatewords(striptags(pack.summary), 20)
        ]
    return None


def _add_form(pack: Any, lst: Any, request: Any, button_text: str) -> Node:
    return form(method="post", action=reverse("core:list-packs", args=[lst.id]))[
        CsrfInput(request),
        input_(type="hidden", name="pack_id", value=str(pack.id)),
        input_(type="hidden", name="action", value="add"),
        button(type="submit", class_="btn btn-sm btn-primary")[button_text],
    ]


def _remove_form(pack: Any, lst: Any, request: Any) -> Node:
    return form(
        method="post",
        action=reverse("core:pack-unsubscribe", args=[pack.id]),
        class_="d-inline",
    )[
        CsrfInput(request),
        input_(type="hidden", name="list_id", value=str(lst.id)),
        input_(type="hidden", name="return_url", value="list"),
        button(type="submit", class_="btn btn-sm btn-outline-danger")["Remove"],
    ]


def _required_badge(pack: Any) -> Node:
    if not pack.required_by_campaigns:
        return None
    joined = join(pack.required_by_campaigns, ", ")
    return span(class_="badge text-bg-warning ms-1", title=f"Required by {joined}")[
        "Required by ", joined
    ]


@register_page("core/list_packs.html")
def list_packs(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]
    campaign_packs = context.get("campaign_packs")
    subscribed_packs = context.get("subscribed_packs")
    available_packs = context.get("available_packs")
    search_query = context.get("search_query")
    show_my_packs = context.get("show_my_packs")

    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    # --- Recommended by Campaign ---
    campaign_section: Node = None
    if campaign_packs:
        campaign_section = fragment[
            raw("<!-- Recommended by Campaign -->"),
            section[
                div(
                    class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
                )[h2(class_="h5 mb-0")["Recommended by Campaign"]],
                div(class_="px-2")[
                    p(class_="text-secondary fs-7")[
                        "These Content Packs are used by a Campaign this gang is in."
                    ],
                    ul(class_="list-unstyled mb-0")[
                        tuple(
                            li(
                                class_="py-2 d-flex justify-content-between align-items-center border-bottom"
                            )[
                                div[
                                    _pack_name(pack, request),
                                    span(class_="text-secondary fs-7")[
                                        "by ", pack.owner
                                    ],
                                    _pack_summary(pack),
                                ],
                                _add_form(pack, lst, request, "Add"),
                            ]
                            for pack in campaign_packs
                        )
                    ],
                ],
            ],
        ]

    # --- Subscribed packs ---
    if subscribed_packs:
        subscribed_body: Node = ul(class_="list-unstyled mb-0")[
            tuple(
                li(
                    class_="py-2 d-flex justify-content-between align-items-center gap-2 border-bottom"
                )[
                    div[
                        _pack_name(pack, request),
                        span(class_="text-secondary fs-7")["by ", pack.owner],
                        _required_badge(pack),
                        _pack_summary(pack),
                    ],
                    _remove_form(pack, lst, request)
                    if not pack.required_by_campaigns
                    else None,
                ]
                for pack in subscribed_packs
            )
        ]
    else:
        subscribed_body = p(class_="text-center text-secondary mb-0")[
            "No content packs subscribed yet."
        ]

    subscribed_section: Node = fragment[
        raw("<!-- Subscribed packs -->"),
        section[
            div(
                class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
            )[
                h2(class_="h5 mb-0")[
                    "Subscribed Packs",
                    span(class_="badge text-bg-primary")[len(subscribed_packs)]
                    if subscribed_packs
                    else None,
                ]
            ],
            div(class_="px-2")[subscribed_body],
        ],
    ]

    # --- Available packs ---
    if available_packs:
        available_body: Node = ul(class_="list-unstyled mb-0")[
            tuple(
                li(
                    class_="py-2 d-flex justify-content-between align-items-center border-bottom"
                )[
                    div[
                        _pack_name(pack, request),
                        span(class_="text-secondary fs-7")["by ", pack.owner],
                        _pack_summary(pack),
                    ],
                    _add_form(pack, lst, request, "Subscribe"),
                ]
                for pack in available_packs
            )
        ]
    else:
        available_body = p(class_="text-center text-secondary mb-0")[
            ['No packs found matching "', search_query, '".']
            if search_query
            else "No additional packs available."
        ]

    available_section: Node = fragment[
        raw("<!-- Available packs -->"),
        section[
            div(
                class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
            )[h2(class_="h5 mb-0")["Available Packs"]],
            div(class_="px-2")[
                form(method="get", class_="mb-3 vstack gap-2")[
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
                        button(type="submit", class_="btn btn-primary btn-sm")[
                            "Search"
                        ],
                        a(
                            href=reverse("core:list-packs", args=[lst.id]),
                            class_="btn btn-outline-secondary",
                        )["Clear"]
                        if (search_query or show_my_packs)
                        else None,
                    ],
                    div(class_="form-check form-switch mb-0")[
                        input_(type="hidden", name="my", value="0"),
                        input_(
                            class_="form-check-input",
                            type="checkbox",
                            role="switch",
                            id="my-packs",
                            name="my",
                            value="1",
                            data_gy_toggle_submit=True,
                            checked=bool(show_my_packs),
                        ),
                        label(class_="form-check-label fs-7 mb-0", for_="my-packs")[
                            "Your Packs only"
                        ],
                    ],
                ],
                available_body,
            ],
        ],
    ]

    content: Node = fragment[
        header,
        div(class_="col-12 col-xl-6 px-0 vstack gap-4")[
            h1(class_="h3")["Content Packs"],
            p(class_="text-secondary fs-7")[
                "Content packs add custom fighters, rules, and other content to your list. "
                "Subscribe to a pack to make its content available when building your list."
            ],
            campaign_section,
            subscribed_section,
            available_section,
        ],
    ]

    return Page(title=f"Content Packs - {lst.name}", content=content)
