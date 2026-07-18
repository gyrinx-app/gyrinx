"""Content-pack "Add to Lists & Gangs" subscription-management page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import timesince
from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.models.list import List
from gyrinx.core.templatetags.color_tags import house_icon
from gyrinx.core.templatetags.custom_tags import qt, qt_rm

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, h3, i, input_, li, p, section, ul
from ._shared import back_link


def _list_card(
    lst: Any,
    *,
    pack: Any,
    request: Any,
    action_view: str,
    button_class: str,
    button_text: str,
) -> Node:
    """One list/gang row with its subscribe/unsubscribe form."""
    if lst.status == List.CAMPAIGN_MODE:
        badge = div(class_="badge text-bg-success")["Campaign: ", lst.campaign.name]
    else:
        badge = div(class_="badge text-bg-secondary")[i(class_="bi-list-ul"), " List"]

    return div(class_="hstack gap-3")[
        div(class_="d-flex flex-column gap-1 flex-grow-1")[
            div(class_="hstack column-gap-2 row-gap-1 flex-wrap align-items-baseline")[
                h3(class_="mb-0 h5")[
                    a(href=reverse("core:list", args=[lst.id]))[lst.name]
                ],
            ],
            div(class_="hstack column-gap-2 row-gap-1 flex-wrap")[
                div[lst.content_house, house_icon(lst.content_house_cached)],
                badge,
            ],
            div(class_="hstack column-gap-2 row-gap-1 flex-wrap")[
                div(class_="text-secondary fs-7")[
                    "Last edit: ", timesince(lst.modified), " ago"
                ],
            ],
        ],
        div(class_="ms-auto")[
            form(
                method="post",
                action=reverse(action_view, args=[pack.id]),
                class_="d-inline",
            )[
                CsrfInput(request),
                input_(type="hidden", name="list_id", value=str(lst.id)),
                input_(type="hidden", name="return_url", value="pack-lists"),
                button(type="submit", class_=button_class)[button_text],
            ],
        ],
    ]


def _tab(label: str, is_active: bool, href: str) -> Node:
    return li(class_="nav-item")[
        a(
            class_=["nav-link", {"active": is_active}],
            aria_current="page" if is_active else None,
            href=href,
        )[label]
    ]


@register_page("core/pack/pack_lists.html")
def pack_lists(context: dict[str, Any]) -> Page:
    request = context["request"]
    pack = context["pack"]
    subscribed_lists = list(context.get("subscribed_lists") or [])
    lists = list(context.get("lists") or [])
    houses = context.get("houses")
    current_tab = context.get("current_tab")

    action = reverse("core:pack-lists", args=[pack.id])

    # {% include lists_filter.html with action=action houses=houses hide_toggles=True %}
    lists_filter = raw(
        render_to_string(
            "core/includes/lists_filter.html",
            {"action": action, "houses": houses, "hide_toggles": True},
            request=request,
        )
    )
    # {% include pagination.html %} — inherits is_paginated/page_obj/request.
    pagination = raw(
        render_to_string(
            "core/includes/pagination.html",
            {
                "is_paginated": context.get("is_paginated"),
                "page_obj": context.get("page_obj"),
            },
            request=request,
        )
    )

    tabs = ul(class_="nav nav-tabs mb-4")[
        _tab("All", current_tab == "all", f"?{qt_rm(request, 'type', 'page')}"),
        _tab(
            "Lists",
            current_tab == "list",
            f"?{qt(request, type='list', page=None)}",
        ),
        _tab(
            "Campaign Gangs",
            current_tab == "gang",
            f"?{qt(request, type='gang', page=None)}",
        ),
    ]

    if lists:
        list_body: Node = fragment[
            tuple(
                _list_card(
                    lst,
                    pack=pack,
                    request=request,
                    action_view="core:pack-subscribe",
                    button_class="btn btn-success btn-sm",
                    button_text="Add",
                )
                for lst in lists
            )
        ]
    else:
        list_body = div(class_="py-2 text-secondary fs-7")["No lists found."]

    subscribed_section: Node = None
    if subscribed_lists:
        subscribed_section = section[
            h2(class_="h5 mb-2")["Subscribed"],
            div(class_="vstack gap-4")[
                tuple(
                    _list_card(
                        lst,
                        pack=pack,
                        request=request,
                        action_view="core:pack-unsubscribe",
                        button_class="btn btn-outline-danger btn-sm",
                        button_text="Remove",
                    )
                    for lst in subscribed_lists
                )
            ],
        ]

    content: Node = fragment[
        back_link(context, url=pack.get_absolute_url(), text=pack.name),
        div(class_="col-12 col-xl-8 px-0 vstack gap-4")[
            div[
                h1(class_="h3 mb-1")["Add ", pack.name, " to Lists & Gangs"],
                p(class_="text-secondary fs-7 mb-0")[
                    "Manage which of your Lists & Gangs use this Content Pack."
                ],
            ],
            subscribed_section,
            section[
                h2(class_="h5 mb-3")["Available"],
                div(class_="grid mb-3")[lists_filter],
                tabs,
                div(class_="vstack gap-4")[list_body, pagination],
            ],
        ],
    ]

    return Page(title=f"Add {pack.name} to Lists & Gangs", content=content)
