"""List "About" (gang lore) display page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div


@register_page("core/list_about.html")
def list_about(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]

    # Both {% include %}s in the legacy template are un-ported, so bridge them
    # through the DjangoTemplates loader with the same ``with`` overrides the
    # template passes. Context processors (request, user, gyrinx_debug, ...) are
    # applied identically to both the legacy full-page render and these calls.
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )
    about = raw(
        render_to_string(
            "core/includes/list_about.html",
            {"list": lst},
            request=request,
        )
    )

    content: Node = fragment[
        header,
        div(class_="col-lg-12 px-0 vstack gap-4")[about],
    ]
    return Page(
        title=f"Lore {lst.name} by {lst.owner_cached}",
        content=content,
    )
