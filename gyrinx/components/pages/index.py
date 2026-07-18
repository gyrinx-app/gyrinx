"""Home / dashboard page component (port of ``core/index.html``)."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse

from .. import bridge
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h2,
    i,
    input_,
    label,
    p,
    span,
    strong,
)


def _include(template_name: str, ctx: dict[str, Any], request: Any) -> Node:
    """Bridge an un-ported ``{% include %}`` through the Django template loader."""
    return raw(render_to_string(template_name, ctx, request=request))


def _cachebuster_input() -> Node:
    from gyrinx.core.templatetags.custom_tags import cachebuster

    return input_(type="hidden", name="cb", value=cachebuster())


def _search_form(
    *,
    request: Any,
    form_id: str,
    aria_label: str,
    search_name: str,
    search_value: Any,
    extra_hidden: list[Node],
) -> Node:
    return form(
        id=form_id,
        method="get",
        action=reverse("core:index"),
        class_="vstack gap-2",
    )[
        _cachebuster_input(),
        extra_hidden,
        div(class_="input-group input-group-sm")[
            span(class_="input-group-text")[i(class_="bi-search")],
            input_(
                class_="form-control",
                type="search",
                placeholder="Search",
                aria_label=aria_label,
                name=search_name,
                value=search_value or "",
            ),
            button(class_="btn btn-primary btn-sm", type="submit")["Search"],
        ],
    ]


def _pinned_block(*, has_active: Any, rows: list[Node]) -> Node:
    return div(class_="border-bottom pb-3" if has_active else None)[
        div(class_="caps-label mb-2")["Pinned"],
        div(class_="vstack gap-3")[rows],
    ]


def _campaign_gangs_column(context: dict[str, Any]) -> Node:
    request = context["request"]
    campaign_gangs = context["campaign_gangs"]
    pinned_gangs = context["pinned_gangs"]
    search_query = context.get("search_query")
    search_gangs_query = context.get("search_gangs_query")
    search_campaigns_query = context.get("search_campaigns_query")

    show_all = reverse("core:lists") + "?my=1&type=gang"

    extra_hidden: list[Node] = [
        input_(type="hidden", name="q", value=search_query) if search_query else None,
        input_(type="hidden", name="q_campaigns", value=search_campaigns_query)
        if search_campaigns_query
        else None,
    ]

    if campaign_gangs:
        rows: Node = [
            _include("core/includes/home/gang_row.html", {"gang": gang}, request)
            for gang in campaign_gangs
        ]
    elif search_gangs_query:
        rows = p(class_="text-secondary")["No Campaign Gangs matched your search."]
    elif not pinned_gangs:
        rows = p["You have no Campaign Gangs."]
    else:
        rows = None

    return div(class_="col-12 col-lg-4")[
        div(class_="d-flex justify-content-between align-items-center mb-3")[
            h2(class_="h4 mb-0")["Campaign Gangs"],
            span(class_="ms-auto fs-7")[
                a(href=show_all, class_="linked-secondary")["Show all"]
            ]
            if campaign_gangs
            else None,
        ],
        div(class_="vstack gap-3")[
            _search_form(
                request=request,
                form_id="search-gangs",
                aria_label="Search campaign gangs",
                search_name="q_gangs",
                search_value=search_gangs_query,
                extra_hidden=extra_hidden,
            )
            if (campaign_gangs or search_gangs_query)
            else None,
            _pinned_block(
                has_active=campaign_gangs,
                rows=[
                    _include(
                        "core/includes/home/gang_row.html", {"gang": gang}, request
                    )
                    for gang in pinned_gangs
                ],
            )
            if pinned_gangs
            else None,
            rows,
            div(class_="text-secondary fs-7")[
                "Showing most recently edited ·",
                a(href=show_all, class_="linked-secondary")["Show all"],
            ]
            if campaign_gangs
            else None,
        ],
    ]


def _campaigns_column(context: dict[str, Any]) -> Node:
    request = context["request"]
    campaigns = context["campaigns"]
    pinned_campaigns = context["pinned_campaigns"]
    search_query = context.get("search_query")
    search_gangs_query = context.get("search_gangs_query")
    search_campaigns_query = context.get("search_campaigns_query")

    show_all = reverse("core:campaigns") + "?my=1"

    extra_hidden: list[Node] = [
        input_(type="hidden", name="q", value=search_query) if search_query else None,
        input_(type="hidden", name="q_gangs", value=search_gangs_query)
        if search_gangs_query
        else None,
    ]

    if campaigns:
        rows: Node = [
            _include("core/includes/home/campaign_row.html", {"campaign": c}, request)
            for c in campaigns
        ]
    elif search_campaigns_query:
        rows = p(class_="text-secondary")["No Campaigns matched your search."]
    elif not pinned_campaigns:
        rows = p(class_="text-secondary")[
            "You are not part of any Campaigns. ",
            a(href=reverse("core:campaigns"))["Create a new Campaign"],
            ".",
        ]
    else:
        rows = None

    return div(class_="col-12 col-lg-4")[
        div(class_="d-flex justify-content-between align-items-center mb-3")[
            h2(class_="h4 mb-0")["Campaigns"],
            span(class_="ms-auto fs-7")[
                a(href=reverse("core:campaigns-new"), class_="icon-link linked")[
                    i(class_="bi-plus-lg"), " New Campaign"
                ],
                fragment[
                    " · ",
                    a(href=show_all, class_="linked-secondary")["Show all"],
                ]
                if campaigns
                else None,
            ],
        ],
        div(class_="vstack gap-3")[
            _search_form(
                request=request,
                form_id="search-campaigns",
                aria_label="Search campaigns",
                search_name="q_campaigns",
                search_value=search_campaigns_query,
                extra_hidden=extra_hidden,
            )
            if (len(campaigns) > 0 or search_campaigns_query)
            else None,
            _pinned_block(
                has_active=campaigns,
                rows=[
                    _include(
                        "core/includes/home/campaign_row.html",
                        {"campaign": c},
                        request,
                    )
                    for c in pinned_campaigns
                ],
            )
            if pinned_campaigns
            else None,
            rows,
            div(class_="text-secondary fs-7")[
                "Showing most recently edited ·",
                a(href=show_all, class_="linked-secondary")["Show all"],
            ]
            if campaigns
            else None,
        ],
    ]


def _lists_column(context: dict[str, Any]) -> Node:
    request = context["request"]
    lists = context["lists"]
    pinned_lists = context["pinned_lists"]
    houses = context["houses"]
    has_any_lists = context["has_any_lists"]
    search_query = context.get("search_query")

    show_all = reverse("core:lists") + "?my=1&type=list"

    if lists:
        rows: Node = [
            _include("core/includes/home/list_row.html", {"list": lst}, request)
            for lst in lists
        ]
    else:
        rows = fragment[
            p(class_="text-secondary")["No lists matched your search."]
            if (search_query and has_any_lists)
            else None,
            div(class_="py-2")[
                form(
                    action=reverse("core:lists-new"),
                    method="get",
                    class_="card card-body vstack gap-4",
                )[
                    div[
                        label(for_="id_name")[
                            "Create a new list?"
                            if has_any_lists
                            else "What will you name your first List?"
                        ],
                        input_(
                            type="text",
                            name="name",
                            placeholder="Shadowskin Spectres",
                            required="required",
                            class_="form-control",
                            id="id_name",
                        ),
                    ],
                    button(type="submit", class_="btn btn-primary")["Get started"],
                ]
            ],
        ]

    return div(class_="col-12 col-lg-4")[
        div(class_="d-flex justify-content-between align-items-center mb-3")[
            h2(class_="h4 mb-0")["Lists"],
            span(class_="ms-auto fs-7")[
                a(href=reverse("core:lists-new"), class_="icon-link linked")[
                    i(class_="bi-plus-lg"), " New List"
                ],
                fragment[
                    " · ",
                    a(href=show_all, class_="linked-secondary")["Show all"],
                ]
                if lists
                else None,
            ],
        ],
        div(class_="vstack gap-3")[
            _include(
                "core/includes/lists_filter.html",
                {
                    "action": reverse("core:index"),
                    "houses": houses,
                    "compact": True,
                },
                request,
            )
            if has_any_lists
            else None,
            _pinned_block(
                has_active=lists,
                rows=[
                    _include("core/includes/home/list_row.html", {"list": lst}, request)
                    for lst in pinned_lists
                ],
            )
            if pinned_lists
            else None,
            rows,
            div(class_="text-secondary fs-7")[
                "Showing most recently edited ·",
                a(href=show_all, class_="linked-secondary")["Show all"],
            ]
            if lists
            else None,
        ],
    ]


def _featured_section(context: dict[str, Any]) -> Node:
    request = context["request"]
    featured_packs = context["featured_packs"]
    if not featured_packs:
        return None
    return div[
        div(class_="d-flex justify-content-between align-items-center mb-3")[
            h2(class_="h4 mb-0")["Featured Content Packs"],
            span(class_="ms-auto fs-7")[
                a(href=reverse("core:packs"), class_="linked-secondary")["Browse all"]
            ],
        ],
        div(class_="row g-3")[
            [
                div(class_="col-12 col-md-4")[
                    _include(
                        "core/includes/featured_pack_card.html",
                        {"pack": pack},
                        request,
                    )
                ]
                for pack in featured_packs
            ]
        ],
    ]


def _authenticated_content(context: dict[str, Any]) -> Node:
    user = context["request"].user
    return div(class_="vstack gap-4")[
        div(class_="alert alert-warning alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div(class_="flex-grow-1")[
                strong["Update your username!"],
                " Your current username contains an '@' symbol, which is no longer "
                "allowed. Please update it to continue using all features. ",
                a(
                    href=reverse("core:change-username"),
                    class_="btn btn-warning btn-sm ms-3",
                )["Change Username"],
            ],
        ]
        if "@" in user.username
        else None,
        raw("<!-- Three column layout for desktop, stacked for mobile -->"),
        div(class_="row g-4")[
            raw("<!-- Campaign gangs column -->"),
            _campaign_gangs_column(context),
            raw("<!-- Campaigns column -->"),
            _campaigns_column(context),
            raw("<!-- Lists column -->"),
            _lists_column(context),
        ],
        _featured_section(context),
    ]


def _anonymous_content(context: dict[str, Any]) -> Node:
    about_page = bridge.get_page_by_url("/about/")
    account_signups = getattr(settings, "ACCOUNT_ALLOW_SIGNUPS", "")

    if account_signups:
        if about_page:
            intro: Node = fragment[
                a(class_="d-inline-block", href=about_page.url)["Find out more"],
                ", ",
                a(class_="d-inline-block", href=reverse("account_login"))["sign in"],
                " or ",
                a(class_="d-inline-block", href=reverse("account_signup"))["sign up"],
                ".",
            ]
        else:
            intro = fragment[
                a(class_="d-inline-block", href=reverse("account_login"))["Sign in"],
                " or ",
                a(class_="d-inline-block", href=reverse("account_signup"))["sign up"],
                ".",
            ]
    else:
        if about_page:
            intro = fragment[
                a(class_="d-inline-block", href=about_page.url)["Find out more"],
                " or ",
                a(class_="d-inline-block", href=reverse("account_login"))["sign in"],
                ".",
            ]
        else:
            intro = fragment[
                a(class_="d-inline-block", href=reverse("account_login"))["Sign in"],
                ".",
            ]

    return div(class_="mt-4 vstack gap-4")[
        p(class_="lead fs-2 text-center")[intro],
        div(class_="row")[
            div(class_="col-md-4")[
                h2["Build and manage your gangs"],
                p[
                    "Gyrinx is a powerful set of tools for building and running your "
                    "Necromunda gangs — making the game simpler whatever your level "
                    "of experience."
                ],
            ],
            div(class_="col-md-4")[
                h2["All the latest content"],
                p[
                    "Gyrinx is kept up to date with the latest Necromunda rules as "
                    "they drop."
                ],
            ],
            div(class_="col-md-4")[
                h2["Take the hassle out of arbitration"],
                p[
                    "Running a campaign can get complicated. Gyrinx helps you manage "
                    "all the key parts of campaigns, and supports custom content and "
                    "rules."
                ],
            ],
        ],
    ]


def _prebody(context: dict[str, Any]) -> Node:
    user = context["request"].user
    bg = static("core/img/content/93daeffd-9587-404a-b3e1-33eff4ce7398.jpg")
    style = (
        "background-image:linear-gradient(rgba(0, 0, 0, 0.1), rgba(0, 0, 0, 0.7)), "
        f"url({bg})"
    )
    if user.is_authenticated:
        heading: Node = fragment[
            strong["Welcome"],
            " to Gyrinx’s Necromunda tools, ",
            a(
                class_="link-light link-underline-opacity-50 "
                "link-underline-opacity-100-hover",
                href=reverse("core:user", args=[user.id]),
            )[user.username],
            ".",
        ]
    else:
        heading = fragment[
            strong["Gyrinx"],
            " is a free set of tools for the Necromunda community.",
        ]
    return div(id="hero", class_="hero", style=style)[
        div(class_="container h-100 d-flex align-items-end py-4 z-1")[
            h2(class_="h1 fw-light text-light")[heading]
        ]
    ]


@register_page("core/index.html")
def index(context: dict[str, Any]) -> Page:
    user = context["request"].user
    if user.is_authenticated:
        title = "Home"
        inner: Node = _authenticated_content(context)
    else:
        title = "A free set of tools for the Necromunda community"
        inner = _anonymous_content(context)

    content = div(class_="mb-5 pb-5")[inner]
    return Page(title=title, content=content, prebody=_prebody(context))
