"""Battle detail page component (port of ``core/battle/battle.html``)."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import (
    date as date_filter,
    urlencode as urlencode_filter,
)
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.timezone import template_localtime

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
    nav,
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


def _date(value: Any, fmt: str) -> str:
    """Match ``{{ value|date:fmt }}`` (the ``date`` filter converts aware
    datetimes to local time first — see ``expects_localtime``)."""
    return date_filter(template_localtime(value), fmt)


def _archived_alert(battle: Any, can_unarchive: bool) -> Node:
    if not battle.archived:
        return None
    return div(
        class_="border border-warning rounded p-2 d-flex align-items-center gap-2"
    )[
        i(class_="bi-archive text-warning"),
        span(class_="fs-7")[
            "This battle is archived.",
            fragment[
                " ",
                a(
                    href=reverse("core:battle-archive", args=[battle.id]),
                    class_="linked",
                )["Unarchive it"],
                " to make changes.",
            ]
            if can_unarchive
            else None,
        ],
    ]


def _header_actions(
    battle: Any,
    *,
    can_start: bool,
    can_end: bool,
    can_edit: bool,
    can_unarchive: bool,
) -> Node:
    if not (can_start or can_end or can_edit or can_unarchive):
        return None

    start_or_end: Node = None
    if can_start:
        start_or_end = a(
            href=reverse("core:battle-start", args=[battle.id]),
            class_="btn btn-primary btn-sm",
        )[i(class_="bi-play-circle"), " Start"]
    elif can_end:
        start_or_end = a(
            href=reverse("core:battle-end", args=[battle.id]),
            class_="btn btn-danger btn-sm",
        )[i(class_="bi-stop-circle"), " End"]

    edit_nav: Node = None
    if can_edit or can_unarchive:
        edit_nav = nav(class_="btn-group flex-nowrap")[
            a(
                href=reverse("core:battle-edit", args=[battle.id]),
                class_="btn btn-secondary btn-sm",
            )[i(class_="bi-pencil"), " Edit"]
            if can_edit
            else None,
            div(class_="btn-group", role="group")[
                button(
                    type="button",
                    class_="btn btn-secondary btn-sm dropdown-toggle",
                    data_bs_toggle="dropdown",
                    aria_expanded="false",
                    aria_label="More options",
                )[i(class_="bi-three-dots")],
                ul(class_="dropdown-menu dropdown-menu-end")[
                    li[
                        a(
                            class_="dropdown-item",
                            href=reverse("core:battle-archive", args=[battle.id]),
                        )[
                            i(
                                class_="bi-box-arrow-up"
                                if battle.archived
                                else "bi-archive"
                            ),
                            " ",
                            "Unarchive" if battle.archived else "Archive",
                        ]
                    ]
                ],
            ],
        ]

    return div(class_="ms-md-auto d-flex gap-1 flex-nowrap align-items-center")[
        start_or_end, edit_nav
    ]


def _meta_row(battle: Any, state_current: str, state_display: Any) -> Node:
    if battle.date:
        date_node: Node = span[
            i(class_="bi-calendar"), " ", _date(battle.date, "M d, Y")
        ]
    else:
        date_node = span(class_="fst-italic")[i(class_="bi-calendar"), " Date TBC"]

    return div(class_="d-flex flex-wrap align-items-center gap-2 text-secondary fs-7")[
        span(
            class_=[
                "badge",
                "text-bg-success"
                if state_current == "in_progress"
                else "text-bg-secondary",
            ]
        )[state_display],
        date_node,
        span[i(class_="bi-flag"), " ", battle.mission],
        span[
            i(class_="bi-person"),
            " ",
            a(
                class_="linked",
                href=reverse("core:user", args=[battle.owner.username]),
            )[str(battle.owner)],
        ],
    ]


def _participants_rows(battle: Any, participant_groups: list) -> list[Node]:
    rows: list[Node] = []
    for index, group in enumerate(participant_groups):
        role_option = group["role_option"]
        rows.append(
            tr[
                td(
                    colspan="2",
                    class_=[
                        "caps-label",
                        "text-secondary",
                        None if index == 0 else "pt-3",
                    ],
                )[role_option.name if role_option else "No role"]
            ]
        )
        for participant in group["participants"]:
            gang = participant["list"]
            rows.append(
                tr[
                    td[
                        a(
                            href=reverse("core:list", args=[gang.id]),
                            class_="link-underline-opacity-50 link-underline-opacity-100-hover fw-semibold",
                        )[bridge.list_with_theme(gang)],
                        i(
                            class_="bi-trophy-fill text-warning",
                            data_bs_toggle="tooltip",
                            data_bs_title="Winner",
                        )
                        if participant["is_winner"]
                        else None,
                    ],
                    td(class_="text-end")[bridge.credits(participant["rating"])],
                ]
            )
            crew = participant["crew"]
            if crew:
                crew_obj = crew["crew"]
                rows.append(
                    tr[
                        td(class_="ps-4")[
                            i(class_="bi-arrow-return-right text-secondary"),
                            " ",
                            a(
                                href=reverse(
                                    "core:crew", args=[battle.id, crew_obj.id]
                                ),
                                class_="linked",
                            )[str(crew_obj)],
                            " ",
                            span(
                                class_=[
                                    "badge",
                                    "text-bg-success"
                                    if crew_obj.is_locked
                                    else "text-bg-secondary",
                                ]
                            )[crew_obj.get_status_display()],
                            " ",
                            span(class_="text-secondary fs-7 ms-1")[
                                crew["method_label"]
                            ],
                        ],
                        td(class_="text-end")[
                            span(
                                bs_tooltip=True,
                                data_bs_toggle="tooltip",
                                title="Unknown until the crew is rolled for selection",
                            )["?"]
                            if crew["pending_roll"]
                            else bridge.credits(crew["rating"])
                        ],
                    ]
                )
            elif participant["can_add_crew"]:
                rows.append(
                    tr[
                        td(colspan="2", class_="ps-4")[
                            a(
                                href=reverse("core:crew-new", args=[battle.id])
                                + f"?list={gang.id}",
                                class_="icon-link linked fs-7",
                            )[i(class_="bi-plus-lg"), " Add crew"]
                        ]
                    ]
                )
    return rows


def _participants_section(
    battle: Any,
    *,
    can_manage: bool,
    participant_groups: list,
    state_current: str,
) -> Node:
    header = div(
        class_="d-flex justify-content-between align-items-center mb-2 bg-body-secondary rounded px-2 py-1"
    )[
        h2(class_="h5 mb-0")["Participants"],
        a(
            href=reverse("core:battle-roles-edit", args=[battle.id]),
            class_="icon-link linked fs-7",
        )[i(class_="bi-pencil"), " Assign roles"]
        if (can_manage and participant_groups)
        else None,
    ]

    if participant_groups:
        body: Node = div(class_="table-responsive")[
            table(class_="table table-sm table-borderless align-middle mb-0")[
                thead[
                    tr(class_="border-bottom")[
                        th(class_="caps-label")["Gang"],
                        th(class_="caps-label text-end")["Rating"],
                    ]
                ],
                tbody[tuple(_participants_rows(battle, participant_groups))],
            ]
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")["No gangs added yet."]

    draw_note: Node = None
    if state_current == "post_battle" and not battle.winners.exists():
        draw_note = p(class_="text-secondary fs-7 mt-2 mb-0")[
            i(class_="bi-info-circle"), " This battle ended in a draw."
        ]

    return section[header, div(class_="px-2")[body, draw_note]]


def _actions_section(battle: Any, actions: Any, user: Any, request: Any) -> Node:
    if not actions:
        return None
    return section[
        div(class_="mb-2 bg-body-secondary rounded px-2 py-1")[
            h2(class_="h5 mb-0")["Related Campaign Actions"]
        ],
        div(class_="px-2 vstack gap-1")[
            tuple(
                raw(
                    render_to_string(
                        "core/includes/campaign_action_item.html",
                        {
                            "action": action,
                            "campaign": battle.campaign,
                            "user": user,
                            "show_truncated": False,
                        },
                        request=request,
                    )
                )
                for action in actions
            )
        ],
    ]


def _reports_section(
    battle: Any,
    *,
    can_add_notes: bool,
    user_note: Any,
    notes: Any,
    user: Any,
    request: Any,
) -> Node:
    header_link: Node = None
    if can_add_notes:
        header_link = a(
            href=reverse("core:battle-note-add", args=[battle.id])
            + "?return_url="
            + urlencode_filter(request.get_full_path()),
            class_="icon-link linked fs-7",
        )[
            fragment[i(class_="bi-pencil"), " Edit my report"]
            if user_note
            else fragment[i(class_="bi-plus-lg"), " Add battle report"]
        ]

    if notes:
        body: Node = div(class_="vstack gap-3")[
            tuple(
                div(class_="border-start border-2 ps-3")[
                    div(class_="d-flex justify-content-between align-items-start mb-1")[
                        div(class_="text-secondary fs-7")[
                            i(class_="bi-person"),
                            " ",
                            a(
                                href=reverse("core:user", args=[note.owner.username]),
                                class_="linked",
                            )[str(note.owner)],
                            " · ",
                            _date(note.created, "M d, Y g:i A"),
                        ],
                        a(
                            href=reverse("core:battle-note-add", args=[battle.id]),
                            class_="linked-secondary fs-7",
                        )[i(class_="bi-pencil"), " Edit"]
                        if note.owner == user
                        else None,
                    ],
                    div(class_="mb-last-0")[bridge.safe_rich_text(note.content)],
                ]
                for note in notes
            )
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")[
            i(class_="bi-info-circle"), " No battle reports have been added yet."
        ]

    return section[
        div(
            class_="d-flex justify-content-between align-items-center mb-2 bg-body-secondary rounded px-2 py-1"
        )[h2(class_="h5 mb-0")["Battle Reports"], header_link],
        div(class_="px-2")[body],
    ]


@register_page("core/battle/battle.html")
def battle_detail(context: dict[str, Any]) -> Page:
    battle = context["battle"]
    request = context["request"]
    user = context.get("user")

    can_edit = context["can_edit"]
    can_manage = context["can_manage"]
    can_unarchive = context["can_unarchive"]
    can_add_notes = context["can_add_notes"]
    can_start = context["can_start"]
    can_end = context["can_end"]
    user_note = context["user_note"]
    state_display = context["state_display"]
    state_current = context["state_current"]
    notes = context["notes"]
    actions = context["actions"]
    participant_groups = context["participant_groups"]

    header = div(class_="vstack gap-0")[
        div(class_="caps-label")["Battle"],
        div(
            class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2"
        )[
            h1(class_="h2 mb-0")[battle.name],
            _header_actions(
                battle,
                can_start=can_start,
                can_end=can_end,
                can_edit=can_edit,
                can_unarchive=can_unarchive,
            ),
        ],
        _meta_row(battle, state_current, state_display),
    ]

    two_column = div(class_="row g-4 g-lg-5")[
        div(class_="col-12 col-lg-6 vstack gap-4")[
            _participants_section(
                battle,
                can_manage=can_manage,
                participant_groups=participant_groups,
                state_current=state_current,
            ),
            _actions_section(battle, actions, user, request),
        ],
        div(class_="col-12 col-lg-6")[
            _reports_section(
                battle,
                can_add_notes=can_add_notes,
                user_note=user_note,
                notes=notes,
                user=user,
                request=request,
            )
        ],
    ]

    content: Node = fragment[
        raw(
            render_to_string(
                "core/includes/campaign_common_header.html",
                {**context, "campaign": battle.campaign, "current": battle.name},
                request=request,
            )
        ),
        div(class_="col-lg-12 px-0 vstack gap-4")[
            _archived_alert(battle, can_unarchive),
            header,
            two_column,
        ],
    ]

    return Page(title=f"{battle.name} - Battle", content=content)
