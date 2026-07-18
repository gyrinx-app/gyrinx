"""Fighter equipment-set (Tools of the Trade) membership edit page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, i, input_, label, p
from ._shared import back_link

SHELL = "col-12 col-lg-8 px-0 vstack gap-3"


def _item_row(item: dict[str, Any]) -> Node:
    icon_class = (
        "bi-crosshair text-secondary me-1"
        if item["is_weapon"]
        else "bi-box text-secondary me-1"
    )
    return div(class_="form-check mb-0")[
        input_(
            class_="form-check-input",
            type="checkbox",
            name="assignment",
            value=item["id"],
            id=f"assignment-{item['id']}",
            checked=item["included"],
        ),
        label(class_="form-check-label", for_=f"assignment-{item['id']}")[
            i(class_=icon_class),
            item["name"],
        ],
    ]


@register_page("core/list_fighter_equipment_set_edit.html")
def edit_list_fighter_equipment_set(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    equipment_set = context["equipment_set"]
    items = context["items"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-equipment-sets",
        },
        request=request,
    )

    back_url = reverse("core:list-fighter-equipment-sets", args=[lst.id, fighter.id])

    if items:
        item_nodes: Node = tuple(_item_row(item) for item in items)
    else:
        item_nodes = p(class_="text-secondary mb-0")[
            "This Fighter has no equipment to choose from yet."
        ]

    body = form(
        method="post",
        action=reverse(
            "core:list-fighter-equipment-set-edit",
            args=[lst.id, fighter.id, equipment_set.id],
        ),
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        div[
            label(for_="card-name", class_="form-label")["Set name"],
            input_(
                type="text",
                id="card-name",
                name="name",
                class_="form-control",
                value=equipment_set.name,
                maxlength="255",
                required=True,
            ),
        ],
        div[
            div(class_="bg-body-secondary rounded px-2 py-1 mb-2")[
                h2(class_="h5 mb-0")["Weapons and gear"]
            ],
            p(class_="text-secondary fs-7 px-2 mb-2")[
                "Tick what this card carries. Unticked items stay assigned to the Fighter "
                "but are hidden while this card is showing."
            ],
            div(class_="px-2 vstack gap-2")[item_nodes],
        ],
        div(class_="hstack gap-2")[
            button(type="submit", class_="btn btn-success")[
                i(class_="bi-check-lg"),
                " Save",
            ],
            a(class_="btn btn-link btn-sm", href=back_url)["Cancel"],
        ],
    ]

    content: Node = fragment[
        raw(header),
        PageShell(
            div[
                back_link(context, url=back_url, text="Back to sets"),
                h1(class_="h3 mb-0")["Edit set"],
            ],
            body,
            kind=SHELL,
        ),
    ]
    return Page(
        title=f"{equipment_set.name} - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
