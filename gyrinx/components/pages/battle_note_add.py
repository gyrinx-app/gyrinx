"""Battle note add/edit form page component."""

from __future__ import annotations

from typing import Any

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, input_, p
from ._shared import back_link


@register_page("core/battle/battle_note_add.html")
def battle_note_add(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    battle = context["battle"]
    existing_note = context.get("existing_note")
    return_url = context["return_url"]
    request = context["request"]

    heading = "Edit Battle Note" if existing_note else "Add Battle Note"
    submit_label = "Update Note" if existing_note else "Add Note"

    non_field_errors = form_obj.non_field_errors()
    non_field_block: Node = (
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[non_field_errors],
        ]
        if non_field_errors
        else None
    )

    body = form(method="post", class_="vstack gap-3")[
        non_field_block,
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url),
        raw(str(form_obj.media)),
        raw(str(form_obj)),
        div(class_="hstack gap-3 align-items-center")[
            button(type="submit", class_="btn btn-success")[
                i(class_="bi-check-lg"),
                submit_label,
            ],
            a(href=return_url)["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=return_url, text="Back"),
        div(class_="col-12 col-md-8 col-lg-6 px-0")[
            h1(class_="h3")[heading],
            p(class_="text-secondary")[battle.name],
            body,
        ],
    ]

    title = f"{'Edit Note' if existing_note else 'Add Note'} - {battle.name}"
    return Page(title=title, content=content)
