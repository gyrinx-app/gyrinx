"""Fighter advancements listing page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    div,
    h1,
    i,
    li,
    p,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
    ul,
)

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _type_label(advancement: Any) -> str:
    if advancement.advancement_type == advancement.ADVANCEMENT_STAT:
        return "Stat"
    elif advancement.advancement_type == advancement.ADVANCEMENT_SKILL:
        return "Skill"
    return "Other"


@register_page("core/list_fighter_advancements.html")
def list_fighter_advancements(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    advancements = context["advancements"]
    request = context["request"]
    user = context.get("user")

    is_owner = lst.owner_cached == user

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-advancements",
        },
        request=request,
    )

    if advancements:
        rows: list[Node] = []
        for advancement in advancements:
            actions_cell: Node = None
            if is_owner:
                remove_link: Node = None
                if not advancement.archived:
                    remove_link = a(
                        href=reverse(
                            "core:list-fighter-advancement-delete",
                            args=[lst.id, fighter.id, advancement.id],
                        ),
                        class_="link-secondary icon-link link-underline-opacity-50 link-underline-opacity-100-hover",
                        title="Remove advancement",
                    )[i(class_="bi-trash"), " Remove"]
                actions_cell = td(class_="text-end fs-7")[remove_link]
            rows.append(
                tr[
                    td[_type_label(advancement)],
                    td[advancement.display_description],
                    td[f"{advancement.xp_cost} XP"],
                    td[f"+{advancement.cost_increase}¢"],
                    actions_cell,
                ]
            )

        table_block: Node = div(class_="table-responsive")[
            table(class_="table table-borderless table-sm")[
                thead[
                    tr[
                        th["Type"],
                        th["Advancement"],
                        th["XP"],
                        th["Rating"],
                        th[span(class_="visually-hidden")["Actions"]]
                        if is_owner
                        else None,
                    ]
                ],
                tbody[tuple(rows)],
            ]
        ]
    else:
        table_block = p(class_="text-secondary")["No advancements yet."]

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[f"Advancements for {fighter.name}"],
            ul(class_="fs-5 mb-3 list-group list-group-flush")[
                li(class_="list-group-item")[
                    span(class_="badge text-bg-primary")[f"{fighter.xp_current} XP"],
                    " Current",
                    a(
                        href=reverse(
                            "core:list-fighter-xp-edit", args=[lst.id, fighter.id]
                        ),
                        class_="fs-7 linked-secondary ms-2",
                    )["Add XP"]
                    if is_owner
                    else None,
                ],
                li(class_="list-group-item")[
                    span(class_="badge text-bg-secondary")[f"{fighter.xp_total} XP"],
                    " Total",
                ],
            ],
            div[
                table_block,
                div(class_="d-flex align-items-center")[
                    a(
                        href=reverse(
                            "core:list-fighter-advancement-start",
                            args=[lst.id, fighter.id],
                        ),
                        class_="btn btn-primary",
                    )[i(class_="bi-plus-lg"), " Add Advancement"],
                    a(
                        href=f"{reverse('core:list', args=[lst.id])}#{fighter.id}",
                        class_="btn btn-link",
                    )["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Advancements - {fighter.name}",
        content=content,
    )
