"""Crew detail (receipt) page component (#1346).

Port of ``core/crew/crew.html``: a battle crew shown as an itemised receipt —
attendees (rating), extras (credits / allowance / free), subtotals and total.
"""

from __future__ import annotations

from typing import Any

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
    i,
    span,
    strong,
    table,
    tbody,
    td,
    tfoot,
    th,
    thead,
    tr,
)


def _unknown_tooltip() -> Node:
    """The ``?`` cell shown while a random draw is still pending."""
    return span(
        bs_tooltip=True,
        data_bs_toggle="tooltip",
        title="Unknown until you roll for selection",
    )["?"]


def _header(crew: Any, battle: Any, can_manage: bool) -> Node:
    actions: list[Node] = [
        a(
            href=reverse("core:list-print", args=[crew.list.id])
            + "?crew="
            + str(crew.id),
            class_="btn btn-secondary btn-sm",
        )[i(class_="bi-printer"), " Print"],
    ]
    if can_manage:
        if not crew.is_locked:
            actions.append(
                a(
                    href=reverse("core:crew-lock", args=[battle.id, crew.id]),
                    class_="btn btn-primary btn-sm",
                )[
                    i(class_="bi-dice-5"),
                    " ",
                    "Roll for selection" if crew.pending_roll else "Confirm crew",
                ]
            )
            actions.append(
                a(
                    href=reverse("core:crew-edit", args=[battle.id, crew.id]),
                    class_="btn btn-secondary btn-sm",
                )[i(class_="bi-pencil"), " Edit"]
            )
        actions.append(
            a(
                href=reverse("core:crew-delete", args=[battle.id, crew.id]),
                class_="btn btn-danger btn-sm",
            )[i(class_="bi-trash"), " Delete"]
        )

    status_badge_class = "text-bg-success" if crew.is_locked else "text-bg-secondary"

    return div(class_="vstack gap-0")[
        div(class_="caps-label")["Crew"],
        div(
            class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2"
        )[
            h1(class_="h2 mb-0")[str(crew)],
            div(class_="ms-md-auto d-flex gap-1 flex-nowrap align-items-center")[
                tuple(actions)
            ],
        ],
        div(class_="d-flex flex-wrap align-items-center gap-2 text-secondary fs-7")[
            span(class_=["badge", status_badge_class])[crew.get_status_display()],
            span[
                i(class_="bi-people"),
                " ",
                a(class_="linked", href=reverse("core:list", args=[crew.list.id]))[
                    crew.list.name
                ],
            ],
            span[i(class_="bi-diagram-3"), " ", crew.method_label()],
        ],
    ]


def _attendee_row(
    att: dict[str, Any], crew: Any, battle: Any, can_manage: bool, has_free: bool
) -> Node:
    loadout_children: list[Node] = []
    if att["loadout"]:
        loadout_children.append(f"· {att['loadout']}")
    elif crew.is_locked:
        loadout_children.append("· Full kit")
    if can_manage and crew.is_locked:
        loadout_children.append(" · ")
        loadout_children.append(
            a(
                href=reverse(
                    "core:crew-member-loadout",
                    args=[battle.id, crew.id, att["member_id"]],
                ),
                class_="linked-secondary",
            )["Loadout"]
        )

    name_cell: list[Node] = [
        strong[att["name"]],
        span(class_="text-secondary fs-7")[f"· {att['category']}"],
    ]
    if att["was_random"]:
        name_cell.append(
            span(
                class_="badge text-bg-info ms-1",
                data_bs_toggle="tooltip",
                data_bs_title="Drawn at random",
            )["Random"]
        )
    name_cell.append(span(class_="text-secondary fs-7")[tuple(loadout_children)])

    return tr[
        td[tuple(name_cell)],
        td(class_="text-end")[f"{att['rating']}¢"],
        td,
        td,
        td if has_free else None,
    ]


def _attendees_empty_row(crew: Any, colspan: int) -> Node:
    if crew.is_locked:
        text: Node = "No attendees."
    elif crew.pending_roll:
        text = "No fighters hand-picked — all drawn from the roll."
    else:
        text = "No fighters chosen — the whole gang attends when the crew is rolled."
    return tr[td(colspan=colspan, class_="text-secondary fs-7")[text]]


def _pending_roll_row(
    receipt: dict[str, Any], crew: Any, battle: Any, can_manage: bool, has_free: bool
) -> Node:
    action = (
        a(
            href=reverse("core:crew-lock", args=[battle.id, crew.id]),
            class_="btn btn-primary btn-sm ms-2",
        )[i(class_="bi-dice-5"), " Roll for selection"]
        if can_manage
        else None
    )
    return tr[
        td[
            span(class_="text-secondary")[
                i(class_="bi-dice-5"),
                f" +{receipt['random_spec']} from the roll",
            ],
            action,
        ],
        td(class_="text-end")[_unknown_tooltip()],
        td,
        td,
        td if has_free else None,
    ]


def _extra_row(
    extra: dict[str, Any],
    crew: Any,
    battle: Any,
    can_manage: bool,
    has_free: bool,
    request: Any,
) -> Node:
    item = extra["item"]
    name_cell: list[Node] = [item.label]
    if item.reason:
        name_cell.append(span(class_="text-secondary fs-7")[f"· {item.reason}"])
    if can_manage:
        name_cell.append(
            a(
                href=reverse(
                    "core:crew-extra-edit", args=[battle.id, crew.id, item.id]
                ),
                class_="linked-secondary fs-7 ms-1",
                aria_label="Edit extra",
            )[i(class_="bi-pencil")]
        )
        name_cell.append(
            form(
                method="post",
                action=reverse(
                    "core:crew-extra-delete", args=[battle.id, crew.id, item.id]
                ),
                class_="d-inline",
            )[
                CsrfInput(request),
                button(
                    type="submit",
                    class_="btn btn-link btn-sm linked-secondary p-0",
                    aria_label="Remove extra",
                )[i(class_="bi-trash")],
            ]
        )

    return tr[
        td[tuple(name_cell)],
        td,
        td(class_="text-end")[
            f"{extra['credits']}¢" if extra["credits"] is not None else None
        ],
        td(class_="text-end")[
            f"{extra['allowance']}¢" if extra["allowance"] is not None else None
        ],
        td(class_="text-end")[
            f"{extra['free']}¢" if extra["free"] is not None else None
        ]
        if has_free
        else None,
    ]


def _tfoot(receipt: dict[str, Any], has_free: bool, colspan: int) -> Node:
    pending_roll = receipt["pending_roll"]
    rows: list[Node] = []

    if receipt["has_extras"]:
        rows.append(
            tr(class_="border-top")[
                td(colspan=colspan, class_="pt-3")[
                    span(class_="caps-label")["Subtotals"]
                ]
            ]
        )
        rows.append(
            tr[
                td(class_="text-secondary")["Rating"],
                td(class_="text-end")[
                    _unknown_tooltip()
                    if pending_roll
                    else f"{receipt['fighters_total']}¢"
                ],
                td,
                td,
                td if has_free else None,
            ]
        )
        rows.append(
            tr[
                td(class_="text-secondary")["Credits"],
                td,
                td(class_="text-end")[f"{receipt['credits_total']}¢"],
                td,
                td if has_free else None,
            ]
        )
        rows.append(
            tr[
                td(class_="text-secondary")["Allowance"],
                td,
                td,
                td(class_="text-end")[f"{receipt['allowance_total']}¢"],
                td if has_free else None,
            ]
        )
        if has_free:
            rows.append(
                tr[
                    td(class_="text-secondary")["Free"],
                    td,
                    td,
                    td,
                    td(class_="text-end")[f"{receipt['free_total']}¢"],
                ]
            )

    total_colspan = 4 if has_free else 3
    rows.append(
        tr(class_="border-top fs-5 fw-semibold")[
            td["Total"],
            td(class_="text-end", colspan=total_colspan)[
                _unknown_tooltip() if pending_roll else f"{receipt['total']}¢"
            ],
        ]
    )

    return tfoot[tuple(rows)]


@register_page("core/crew/crew.html")
def crew_detail(context: dict[str, Any]) -> Page:
    crew = context["crew"]
    battle = context["battle"]
    can_manage = context.get("can_manage", False)
    receipt = context["receipt"]
    request = context["request"]

    has_free = receipt["has_free"]
    colspan = 5 if has_free else 4

    battle_url = reverse("core:battle", args=[battle.id])

    # The campaign context header is an un-ported include; bridge it through the
    # DjangoTemplates loader with the same ``with`` overrides the template passes.
    header = raw(
        render_to_string(
            "core/includes/campaign_common_header.html",
            {
                **context,
                "campaign": battle.campaign,
                "parent": battle.name,
                "parent_url": battle_url,
                "current": crew,
            },
            request=request,
        )
    )

    # --- Fighters section ---
    body_rows: list[Node] = [
        tr[
            td(colspan=colspan)[
                div(class_="d-flex justify-content-between align-items-center")[
                    span(class_="caps-label")["Fighters"],
                    a(
                        href=reverse("core:crew-edit", args=[battle.id, crew.id]),
                        class_="icon-link linked fs-7",
                    )[i(class_="bi-pencil"), " Edit choices"]
                    if (can_manage and not crew.is_locked)
                    else None,
                ]
            ]
        ]
    ]
    if receipt["attendees"]:
        body_rows.extend(
            _attendee_row(att, crew, battle, can_manage, has_free)
            for att in receipt["attendees"]
        )
    else:
        body_rows.append(_attendees_empty_row(crew, colspan))

    if receipt["pending_roll"]:
        body_rows.append(_pending_roll_row(receipt, crew, battle, can_manage, has_free))

    # --- Extras section ---
    body_rows.append(
        tr[
            td(colspan=colspan, class_="pt-3")[
                div(class_="d-flex justify-content-between align-items-center")[
                    span(class_="caps-label")["Extras"],
                    a(
                        href=reverse("core:crew-extra-new", args=[battle.id, crew.id]),
                        class_="icon-link linked fs-7",
                    )[i(class_="bi-plus-lg"), " Add extra"]
                    if can_manage
                    else None,
                ]
            ]
        ]
    )
    if receipt["extras"]:
        body_rows.extend(
            _extra_row(extra, crew, battle, can_manage, has_free, request)
            for extra in receipt["extras"]
        )
    else:
        body_rows.append(
            tr[td(colspan=colspan, class_="text-secondary fs-7")["No extras."]]
        )

    sheet = div(class_="table-responsive")[
        table(class_="table table-sm table-borderless align-middle mb-0")[
            thead[
                tr(class_="border-bottom")[
                    th,
                    th(class_="caps-label text-end")["Rating"],
                    th(class_="caps-label text-end")["Credits"],
                    th(class_="caps-label text-end")["Allowance"],
                    th(class_="caps-label text-end")["Free"] if has_free else None,
                ]
            ],
            tbody[tuple(body_rows)],
            _tfoot(receipt, has_free, colspan),
        ]
    ]

    content: Node = fragment[
        header,
        div(class_="col-12 col-md-10 col-lg-7 px-0 vstack gap-4")[
            _header(crew, battle, can_manage),
            sheet,
        ],
    ]
    return Page(title=f"{crew} - {battle.name}", content=content)
