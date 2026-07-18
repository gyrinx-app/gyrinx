"""Gang skill-trees management (display) page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import urlencode as urlencode_filter
from django.template.loader import render_to_string
from django.urls import reverse

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i, p, table, tbody, td, tr


@register_page("core/list_skill_trees_manage.html")
def manage_list_skill_trees(context: dict[str, Any]) -> Page:
    lst = context["list"]
    assignments = context["assignments"]
    request = context["request"]

    manage_url = reverse("core:list-skill-trees-manage", args=[lst.id])

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    house = lst.content_house
    intro = p(class_="text-secondary")[
        f"{house.name} gangs pick {house.gang_skill_tree_count} "
        "ranked skill trees. Fighters gain these as primary or secondary skills based on "
        "their rank."
    ]

    if assignments:
        picks: Node = table(class_="table table-sm fs-7")[
            tbody[
                tuple(
                    tr[
                        td(class_="ps-0 text-nowrap")[f"Tree {assignment.slot}"],
                        td[assignment.skill_category.name],
                    ]
                    for assignment in assignments
                )
            ]
        ]
    else:
        picks = div(class_="border rounded p-2 mb-3 text-secondary")[
            "No skill trees picked yet. Fighters won't gain gang skill trees until you "
            "choose them."
        ]

    edit_link: Node = None
    if not lst.archived:
        edit_href = (
            reverse("core:list-skill-trees-edit", args=[lst.id])
            + "?return_url="
            + urlencode_filter(manage_url)
        )
        edit_link = a(href=edit_href, class_="btn btn-primary btn-sm")[
            i(class_="bi-pencil", aria_hidden="true"),
            " Edit skill trees",
        ]

    content: Node = fragment[
        header,
        div(class_="row g-3 mb-3")[
            div(class_="col-12 col-xl-6")[
                h1(class_="h3")["Gang skill trees"],
                intro,
                picks,
                edit_link,
            ]
        ],
    ]

    return Page(title=f"Gang skill trees - {lst.name}", content=content)
