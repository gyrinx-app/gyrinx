"""Gang notes display page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div


@register_page("core/list_notes.html")
def list_notes(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {**context, "list": lst, "link_list": "true"},
        request=request,
    )
    notes = render_to_string(
        "core/includes/list_notes.html",
        {**context, "list": lst},
        request=request,
    )

    content: Node = fragment[
        raw(header),
        div(class_="col-lg-12 px-0 vstack gap-4")[raw(notes)],
    ]
    return Page(
        title=f"Notes {lst.name} by {lst.owner_cached}",
        content=content,
    )
