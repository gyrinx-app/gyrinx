"""Campaign action-log listing page component (search / filter + action feed)."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import urlencode as urlencode_filter
from django.template.loader import render_to_string
from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import qt_rm

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
    option,
    p,
    select,
    span,
)
from ._shared import back_link


@register_page("core/campaign/campaign_actions.html")
def campaign_actions(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    request = context["request"]
    user = context.get("user")
    can_log_actions = context.get("can_log_actions")
    actions = context.get("actions")

    actions_url = reverse("core:campaign-actions", args=[campaign.id])

    # Header: title + optional "Log Action" button.
    log_action_link = None
    if can_log_actions:
        new_url = reverse("core:campaign-action-new", args=[campaign.id])
        return_url = urlencode_filter(request.get_full_path())
        log_action_link = a(
            href=f"{new_url}?return_url={return_url}",
            class_="btn btn-primary btn-sm",
        )[i(class_="bi-plus-lg"), " Log Action"]

    header = div(class_="d-flex justify-content-between align-items-center")[
        div[
            h1(class_="h3 mb-0")["Campaign Actions"],
            h2(class_="h5 text-secondary")[campaign.name],
        ],
        log_action_link,
    ]

    # Actions feed (bridged item + pagination partials) or empty state.
    if actions:
        actions_section: Node = fragment[
            div(class_="list-group list-group-flush")[
                tuple(
                    raw(
                        render_to_string(
                            "core/includes/campaign_action_item.html",
                            {
                                **context,
                                "action": action,
                                "campaign": campaign,
                                "user": user,
                                "show_truncated": False,
                            },
                            request=request,
                        )
                    )
                    for action in actions
                )
            ],
            raw(
                render_to_string(
                    "core/includes/pagination.html", {**context}, request=request
                )
            ),
        ]
    else:
        actions_section = p(class_="text-secondary")["No actions logged yet."]

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        div(class_="col-12 px-0 vstack gap-4")[
            header,
            raw("<!-- Filter Section -->"),
            _filter_card(context, campaign, request, actions_url),
            actions_section,
        ],
    ]
    return Page(title=f"Actions - {campaign.name}", content=content)


def _filter_card(
    context: dict[str, Any], campaign: Any, request: Any, actions_url: str
) -> Node:
    campaign_lists = context.get("campaign_lists") or []
    action_authors = context.get("action_authors") or []
    campaign_battles = context.get("campaign_battles") or []

    gang_sel = request.GET.get("gang")
    author_sel = request.GET.get("author")
    battle_sel = request.GET.get("battle")
    timeframe = request.GET.get("timeframe")
    q_value = request.GET.get("q", "")

    clear_link = (
        a(href=f"?{qt_rm(request, 'q')}", class_="btn btn-outline-secondary")["Clear"]
        if request.GET.get("q")
        else None
    )

    # Gang option text mirrors the legacy template's whitespace: name, then an
    # optional "(house)", then "- owner".
    def _gang_option(lst: Any) -> Node:
        text = f"{lst.name} "
        if lst.content_house:
            text += f"({lst.content_house_name}) "
        text += f"- {lst.owner.username}"
        return option(value=str(lst.id), selected=gang_sel == str(lst.id))[text]

    return div(class_="card")[
        div(class_="card-body")[
            form(
                method="get",
                action=actions_url,
                class_="vstack gap-3",
                id="filter-form",
            )[
                raw("<!-- Search Input -->"),
                div(class_="row g-2")[
                    div(class_="col-12")[
                        label(for_="search", class_="form-label")["Search"],
                        div(class_="hstack gap-2")[
                            div(class_="input-group")[
                                span(class_="input-group-text")[i(class_="bi-search")],
                                input_(
                                    class_="form-control",
                                    id="search",
                                    type="search",
                                    placeholder="Search actions by description, outcome, or author",
                                    aria_label="Search",
                                    name="q",
                                    value=q_value,
                                ),
                            ],
                            div(class_="btn-group")[
                                button(class_="btn btn-primary", type="submit")[
                                    "Search"
                                ],
                                clear_link,
                            ],
                        ],
                    ]
                ],
                raw("<!-- Gang and Author Filters -->"),
                div(class_="row g-2")[
                    div(class_="col-md-4")[
                        label(for_="gang", class_="form-label")["Gang"],
                        select(class_="form-select", id="gang", name="gang")[
                            option(value="")["All gangs"],
                            tuple(_gang_option(lst) for lst in campaign_lists),
                        ],
                    ],
                    div(class_="col-md-4")[
                        label(for_="author", class_="form-label")["Author"],
                        select(class_="form-select", id="author", name="author")[
                            option(value="")["All authors"],
                            tuple(
                                option(
                                    value=str(author_id),
                                    selected=author_sel == str(author_id),
                                )[author_username]
                                for author_id, author_username in action_authors
                            ),
                        ],
                    ],
                    div(class_="col-md-4")[
                        label(for_="battle", class_="form-label")["Battle"],
                        select(class_="form-select", id="battle", name="battle")[
                            option(value="")["All battles"],
                            tuple(
                                option(
                                    value=str(battle.id),
                                    selected=battle_sel == str(battle.id),
                                )[battle.name]
                                for battle in campaign_battles
                            ),
                        ],
                    ],
                ],
                div(class_="row g-2")[
                    div(class_="col-md-4")[
                        label(for_="timeframe", class_="form-label")["Timeframe"],
                        select(class_="form-select", id="timeframe", name="timeframe")[
                            option(value="", selected=not timeframe)["Any time"],
                            option(value="24h", selected=timeframe == "24h")[
                                "Last 24 hours"
                            ],
                            option(value="7d", selected=timeframe == "7d")[
                                "Last 7 days"
                            ],
                            option(value="30d", selected=timeframe == "30d")[
                                "Last 30 days"
                            ],
                        ],
                    ]
                ],
                raw("<!-- Filter Buttons -->"),
                div(class_="d-flex gap-2 align-items-center")[
                    button(class_="btn btn-link icon-link btn-sm", type="submit")[
                        i(class_="bi-arrow-clockwise"), " Update Filters"
                    ],
                    "•",
                    a(
                        href=actions_url,
                        class_="btn btn-link linked-secondary icon-link btn-sm",
                    )["Reset All"],
                ],
            ]
        ]
    ]
