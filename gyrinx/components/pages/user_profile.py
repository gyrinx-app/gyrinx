"""Public user-profile page component (port of ``core/user.html``)."""

from __future__ import annotations

from typing import Any

from django.contrib.humanize.templatetags.humanize import naturaltime
from django.template.defaultfilters import pluralize
from django.template.loader import render_to_string
from django.urls import reverse

from .. import bridge
from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, i, input_, li, p, section, span, ul


def _add_button(url: str) -> Node:
    return a(href=url, class_="btn btn-primary btn-sm")[i(class_="bi-plus-lg"), " Add"]


def _section_header(title: Node, add_button: Node = None) -> Node:
    return div(
        class_="d-flex justify-content-between align-items-center mb-2 "
        "bg-body-tertiary rounded px-2 py-2"
    )[
        h2(class_="h5 mb-0")[title],
        add_button,
    ]


def _star_span(obj: Any) -> Node:
    star = getattr(obj, "star_count", 0) or 0
    icon_class = "bi-star-fill text-warning" if star else "bi-star"
    return span(class_="text-secondary fs-7", title="Stars")[
        i(class_=icon_class),
        " ",
        star,
    ]


def _list_row(list_obj: Any) -> Node:
    return li(class_="py-1")[
        div(class_="d-flex justify-content-between align-items-center")[
            div[
                a(
                    href=reverse("core:list", args=[list_obj.id]),
                    class_="linked fw-medium",
                )[list_obj.name],
                span(class_="text-secondary fs-7 ms-1")[
                    list_obj.content_house_name,
                    bridge.house_icon(list_obj.content_house_cached),
                ],
            ],
            span(class_="hstack gap-2 align-items-center")[
                _star_span(list_obj),
                span(class_="badge text-bg-primary")[
                    bridge.credits(list_obj.wealth_current)
                ],
            ],
        ],
    ]


def _campaign_gang_row(list_obj: Any) -> Node:
    campaign_link = None
    if list_obj.campaign:
        campaign_link = span(class_="text-secondary fs-7 ms-1")[
            a(
                href=reverse("core:campaign", args=[list_obj.campaign.id]),
                class_="linked-secondary",
            )[list_obj.campaign.name]
        ]
    return li(class_="py-1")[
        div(class_="d-flex justify-content-between align-items-center")[
            div[
                a(
                    href=reverse("core:list", args=[list_obj.id]),
                    class_="linked fw-medium",
                )[list_obj.name],
                campaign_link,
                span(class_="text-secondary fs-7 ms-1")[
                    list_obj.content_house_name,
                    bridge.house_icon(list_obj.content_house_cached),
                ],
            ],
            _star_span(list_obj),
        ],
    ]


def _campaign_row(campaign: Any, request: Any) -> Node:
    return li(class_="py-1")[
        div(class_="d-flex justify-content-between align-items-center")[
            div[
                a(
                    href=reverse("core:campaign", args=[campaign.id]),
                    class_="linked fw-medium",
                )[campaign.name],
            ],
            span(class_="hstack gap-2 align-items-center")[
                _star_span(campaign),
                # ``status.html`` (with its nested indicator include) is un-ported;
                # bridge it with the same ``campaign`` override the legacy
                # ``{% include ... with campaign=campaign %}`` passes.
                raw(
                    render_to_string(
                        "core/campaign/includes/status.html",
                        {"campaign": campaign},
                        request=request,
                    )
                ),
            ],
        ],
    ]


def _pack_row(pack: Any) -> Node:
    if pack.listed:
        status = span(class_="text-secondary fs-7")[i(class_="bi-eye"), " Public"]
    else:
        status = span(class_="text-secondary fs-7")[
            i(class_="bi-eye-slash"), " Unlisted"
        ]
    return li(class_="py-1")[
        div(class_="d-flex justify-content-between align-items-center")[
            div[
                a(href=reverse("core:pack", args=[pack.id]), class_="linked fw-medium")[
                    pack.name
                ]
            ],
            status,
        ],
    ]


def _header(context: dict[str, Any]) -> Node:
    profile_user = context["profile_user"]
    request = context["request"]
    public_lists = context["public_lists"]
    unlisted_lists = context["unlisted_lists"]
    public_count = len(public_lists)

    count_text = f" {public_count} public list{pluralize(public_count)}"
    if unlisted_lists:
        count_text += f" , {len(unlisted_lists)} unlisted"

    meta_row = div(class_="d-flex flex-wrap gap-2 text-secondary fs-7")[
        span[i(class_="bi-clock"), " Joined ", naturaltime(profile_user.date_joined)],
        span[i(class_="bi-list-ul"), count_text],
        span(class_="badge text-bg-success")["Staff"]
        if profile_user.is_staff
        else None,
    ]

    impersonate = None
    if context["can_impersonate_user"]:
        impersonate = form(
            method="post",
            action=reverse("core:impersonate-start", args=[profile_user.id]),
            class_="mt-2 m-0",
        )[
            CsrfInput(request),
            input_(type="hidden", name="next", value=request.get_full_path()),
            button(type="submit", class_="btn btn-danger btn-sm")[
                i(class_="bi-person-bounding-box"), " Impersonate this user"
            ],
        ]

    return div(class_="vstack gap-0")[
        h1(class_="h2 mb-0")[profile_user.username, bridge.user_badge(profile_user)],
        meta_row,
        impersonate,
    ]


def _public_section(context: dict[str, Any]) -> Node:
    public_lists = context["public_lists"]
    is_own = context["is_own_profile"]
    if not (public_lists or is_own):
        return None
    add = _add_button(reverse("core:lists-new")) if is_own else None
    if public_lists:
        body: Node = ul(class_="list-unstyled mb-0")[
            tuple(_list_row(lst) for lst in public_lists)
        ]
    else:
        body = p(class_="text-secondary mb-0")["No public lists yet."]
    return section[_section_header("Public lists", add), div(class_="px-2")[body]]


def _unlisted_section(context: dict[str, Any]) -> Node:
    unlisted_lists = context["unlisted_lists"]
    if not unlisted_lists:
        return None
    return section[
        _section_header(fragment[i(class_="bi-eye-slash"), " Unlisted"]),
        div(class_="px-2")[
            ul(class_="list-unstyled mb-0")[
                tuple(_list_row(lst) for lst in unlisted_lists)
            ]
        ],
    ]


def _campaign_gangs_section(context: dict[str, Any]) -> Node:
    campaign_gangs = context["campaign_gangs"]
    is_own = context["is_own_profile"]
    if not (campaign_gangs or is_own):
        return None
    if campaign_gangs:
        body: Node = ul(class_="list-unstyled mb-0")[
            tuple(_campaign_gang_row(lst) for lst in campaign_gangs)
        ]
    else:
        body = p(class_="text-secondary mb-0")["No Campaign Gangs yet."]
    return section[_section_header("Campaign Gangs"), div(class_="px-2")[body]]


def _campaigns_section(context: dict[str, Any]) -> Node:
    campaigns = context["campaigns"]
    is_own = context["is_own_profile"]
    request = context["request"]
    if not (campaigns or is_own):
        return None
    add = _add_button(reverse("core:campaigns-new")) if is_own else None
    if campaigns:
        body: Node = ul(class_="list-unstyled mb-0")[
            tuple(_campaign_row(campaign, request) for campaign in campaigns)
        ]
    else:
        body = p(class_="text-secondary mb-0")["No Campaigns yet."]
    return section[_section_header("Campaigns", add), div(class_="px-2")[body]]


def _packs_section(context: dict[str, Any]) -> Node:
    show_packs = context["show_packs"]
    packs = context["packs"]
    is_own = context["is_own_profile"]
    if not ((show_packs and packs) or (show_packs and is_own)):
        return None
    add = _add_button(reverse("core:packs-new")) if is_own else None
    if packs:
        body: Node = ul(class_="list-unstyled mb-0")[
            tuple(_pack_row(pack) for pack in packs)
        ]
    else:
        body = p(class_="text-secondary mb-0")["No Content Packs yet."]
    return section[_section_header("Content Packs", add), div(class_="px-2")[body]]


@register_page("core/user.html")
def user_profile(context: dict[str, Any]) -> Page:
    profile_user = context["profile_user"]
    content: Node = div(class_="col-12 col-xl-8 px-0 vstack gap-4")[
        _header(context),
        _public_section(context),
        _unlisted_section(context),
        _campaign_gangs_section(context),
        _campaigns_section(context),
        _packs_section(context),
    ]
    return Page(title=profile_user.username, content=content)
