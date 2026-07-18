"""Fighter skills edit page component."""

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
    h3,
    i,
    input_,
    span,
    table,
    tbody,
    td,
    tr,
)


def _skill_card(title: str, rows: list[Node]) -> Node:
    """The card + responsive table shell shared by the two skill tables."""
    return div(class_="card")[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")[title]],
        div(class_="card-body p-0 p-sm-2")[
            div(class_="table-responsive")[
                table(class_="table table-borderless table-sm align-middle mb-0")[
                    tbody[tuple(rows)]
                ]
            ]
        ],
    ]


def _default_skill_row(
    skill_data: dict[str, Any], lst: Any, fighter: Any, request: Any
) -> Node:
    is_disabled = skill_data["is_disabled"]
    skill = skill_data["skill"]
    return tr(
        class_="text-decoration-line-through text-secondary" if is_disabled else None
    )[
        td[skill.name],
        td(class_="text-secondary")[skill.category.name],
        td(class_="text-end")[
            form(
                method="post",
                action=reverse(
                    "core:list-fighter-skill-toggle",
                    args=[lst.id, fighter.id, skill.id],
                ),
                class_="d-inline",
            )[
                CsrfInput(request),
                button(
                    type="submit",
                    class_=[
                        "btn btn-link icon-link fs-7",
                        "link-success" if is_disabled else "link-danger",
                    ],
                )[
                    fragment[i(class_="bi-check-lg"), " Enable"]
                    if is_disabled
                    else fragment[i(class_="bi-x-circle"), " Disable"]
                ],
            ]
        ],
    ]


def _user_added_skill_row(skill: Any, lst: Any, fighter: Any, request: Any) -> Node:
    return tr[
        td[skill.name],
        td(class_="text-secondary")[skill.category.name],
        td(class_="text-end")[
            form(
                method="post",
                action=reverse(
                    "core:list-fighter-skill-remove",
                    args=[lst.id, fighter.id, skill.id],
                ),
                class_="d-inline",
            )[
                CsrfInput(request),
                button(type="submit", class_="btn btn-link icon-link fs-7 link-danger")[
                    i(class_="bi-trash"), " Remove"
                ],
            ]
        ],
    ]


def _empty_row(message: str) -> Node:
    return tr[td(colspan="3", class_="text-center text-secondary")[message]]


def _category_card(
    cat_data: dict[str, Any], lst: Any, fighter: Any, request: Any
) -> Node:
    category = cat_data["category"]
    if cat_data["primary"]:
        badge: Node = span(class_="badge text-bg-primary")["Primary"]
    elif cat_data["secondary"]:
        badge = span(class_="badge text-bg-secondary")["Secondary"]
    else:
        badge = None

    rows = [
        tr[
            td[skill.name],
            td(class_="text-end")[
                form(
                    method="post",
                    action=reverse(
                        "core:list-fighter-skill-add", args=[lst.id, fighter.id]
                    ),
                    class_="d-inline",
                )[
                    CsrfInput(request),
                    input_(type="hidden", name="skill_id", value=skill.id),
                    button(type="submit", class_="btn btn-sm btn-outline-primary")[
                        i(class_="bi-plus-lg"), " Add"
                    ],
                ]
            ],
        ]
        for skill in cat_data["skills"]
    ]

    return div(class_="card g-col-12 g-col-md-6", id=f"category-{category.id}")[
        div(
            class_=[
                "card-header p-2",
                "bg-info-subtle" if cat_data["is_special"] else None,
            ]
        )[
            div(class_="vstack gap-1")[
                div(class_="hstack")[
                    h3(class_="h5 mb-0")[category.name],
                    span(class_="ms-auto")[badge],
                ]
            ]
        ],
        div(class_="card-body p-0 p-sm-2")[
            div(class_="table-responsive")[
                table(class_="table table-borderless table-sm align-middle mb-0")[
                    tbody[tuple(rows)]
                ]
            ]
        ],
    ]


@register_page("core/list_fighter_skills_edit.html")
def edit_list_fighter_skills(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]
    default_skills_display = context["default_skills_display"]
    user_added_skills = context["user_added_skills"]
    categories = context["categories"]
    search_query = context["search_query"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-skills-edit",
        },
        request=request,
    )

    default_rows = [
        _default_skill_row(skill_data, lst, fighter, request)
        for skill_data in default_skills_display
    ] or [_empty_row("No default skills for this fighter.")]

    user_added_rows = [
        _user_added_skill_row(skill, lst, fighter, request)
        for skill in user_added_skills
    ] or [_empty_row("No user-added skills for this fighter.")]

    filter_action = reverse("core:list-fighter-skills-edit", args=[lst.id, fighter.id])
    filter_html = render_to_string(
        "core/includes/fighter_skills_filter.html",
        {**context, "action": filter_action},
        request=request,
    )

    if categories:
        grid_children: list[Node] = [
            _category_card(cat_data, lst, fighter, request) for cat_data in categories
        ]
    else:
        if not search_query and context.get("primary_secondary_only"):
            empty: Node = (
                "No available skills found in primary or secondary categories."
            )
        elif search_query:
            empty = fragment[
                f'No skills found matching "{search_query}".',
                " ",
                a(href="?")["Clear your search"],
                ".",
            ]
        else:
            empty = "No available skills found."
        grid_children = [div(class_="g-col-12")[empty]]

    content: Node = fragment[
        raw(header),
        div(class_="col-12 col-lg-8 px-0 vstack gap-3")[
            h1(class_="h3")[f"Skills: {fighter.fully_qualified_name}"],
            _skill_card("Default Skills", default_rows),
            _skill_card("User-added Skills", user_added_rows),
            div[h3(class_="h5 mb-1")["Skill Categories"]],
            raw(filter_html),
            div(class_="grid")[tuple(grid_children)],
        ],
    ]

    return Page(
        title=f"Skills - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
