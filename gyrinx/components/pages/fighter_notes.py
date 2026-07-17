"""Fighter notes edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _field(bound: Any) -> Node:
    """Reproduce the inline label/widget/help-text block used per field."""
    return div[
        label(for_=bound.id_for_label, class_="form-label")[bound.label],
        raw(str(bound)),
        div(class_="form-text")[bound.help_text] if bound.help_text else None,
    ]


@register_page("core/list_fighter_notes_edit.html")
def list_fighter_notes_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = form_obj.instance
    return_url = context.get("return_url")
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-notes-edit",
        },
        request=request,
    )

    body = form(
        action=reverse("core:list-fighter-notes-edit", args=[lst.id, fighter.id]),
        method="post",
    )[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url),
        raw(str(form_obj.media)),
        div(class_="vstack gap-3")[
            _field(form_obj["save_roll"]),
            _field(form_obj["notes"]),
            _field(form_obj["private_notes"]),
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=return_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[
                f"Notes: {fighter.name} - {fighter.content_fighter.name()}"
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Notes - {fighter.name} - {fighter.content_fighter.name()} - {lst.name}"
        ),
        content=content,
    )
