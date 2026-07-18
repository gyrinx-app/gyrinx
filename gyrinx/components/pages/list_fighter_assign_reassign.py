"""Reassign-equipment form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, strong

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_assign_reassign.html")
def list_fighter_assign_reassign(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    form_obj = context["form"]
    back_url = context["back_url"]
    request = context["request"]

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = render_to_string(
        "core/includes/list_common_header.html",
        {**context, "list": lst, "link_list": "true"},
        request=request,
    )

    target_field = form_obj["target_fighter"]

    field_block = div(class_="mb-3")[
        target_field.label_tag(),
        target_field,
        div(class_="form-text")[target_field.help_text]
        if target_field.help_text
        else None,
        div(class_="invalid-feedback d-block")[target_field.errors[0]]
        if target_field.errors
        else None,
    ]

    body = form(method="post")[
        CsrfInput(request),
        field_block,
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Reassign"],
            a(href=reverse(back_url, args=[lst.id, fighter.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[f"Reassign {assign.content_equipment.name}"],
            p["Currently assigned to: ", strong[fighter.name]],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Reassign - {assign.content_equipment.name} - "
            f"{fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
