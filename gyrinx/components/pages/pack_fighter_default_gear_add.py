"""Add default gear to a pack fighter (equipment picker page)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, em, form, h1, h3, h4, i, input_, span
from ._shared import back_link


@register_page("core/pack/pack_fighter_default_gear_add.html")
def pack_fighter_default_gear_add(context: dict[str, Any]) -> Page:
    request = context["request"]
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    categories = context["categories"]
    search_q = context["search_q"]
    error_message = context.get("error_message")

    back_url = reverse("core:pack-item-default-equipment", args=[pack.id, pack_item.id])
    add_url = reverse(
        "core:pack-fighter-default-gear-add", args=[pack.id, pack_item.id]
    )

    error_alert = (
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]
        if error_message
        else None
    )

    search_form = form(method="get", id="search")[
        div(class_="d-flex gap-2 align-items-center")[
            div(class_="input-group")[
                span(class_="input-group-text")[i(class_="bi-search")],
                input_(
                    type="search",
                    name="q",
                    value=search_q,
                    class_="form-control",
                    placeholder="Search gear...",
                ),
                button(type="submit", class_="btn btn-primary")["Search"],
            ],
            a(href=add_url, class_="fs-7 text-nowrap")["Clear"] if search_q else None,
        ]
    ]

    category_cards = [
        div(class_="card g-col-12 g-col-md-6")[
            div(class_="card-header p-2")[h3(class_="h5 mb-0")[category_name],],
            div(class_="card-body vstack p-0 px-sm-2 py-sm-1")[
                tuple(
                    form(
                        action=add_url,
                        method="post",
                        class_="p-2 p-sm-0 py-sm-2 hstack gap-2",
                    )[
                        CsrfInput(request),
                        input_(
                            type="hidden",
                            name="content_equipment",
                            value=item.id,
                        ),
                        div(class_="vstack gap-1")[
                            h4(class_="h6 mb-0")[item.name],
                            button(
                                type="submit",
                                class_="btn btn-outline-primary btn-sm",
                            )[
                                i(class_="bi-plus"),
                                " Add ",
                                item.name,
                            ],
                        ],
                    ]
                    for item in items
                )
            ],
        ]
        for category_name, items in categories.items()
    ]

    if category_cards:
        grid_children: Node = tuple(category_cards)
    else:
        grid_children = div(class_="g-col-12")[
            "No gear found.",
            a(href=add_url)[em["Clear your search"]] if search_q else None,
        ]

    content: Node = fragment[
        back_link(context, url=back_url, text=content_fighter.type),
        div(class_="col-12 col-xl-8 px-0 vstack gap-3")[
            h1(class_="h3")["Add default gear: ", content_fighter.type],
            error_alert,
            raw("<!-- Search -->"),
            search_form,
            raw("<!-- Gear by category -->"),
            div(class_="grid")[grid_children],
        ],
    ]
    return Page(
        title=f"Add default gear - {content_fighter.type} - {pack.name}",
        content=content,
    )
