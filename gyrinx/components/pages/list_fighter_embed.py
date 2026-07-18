"""Embedded single-fighter print card (iframe-resizer target)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div, script


@register_page("core/list_fighter_embed.html")
def list_fighter_embed(context: dict[str, Any]) -> Page:
    fighter = context["fighter"]
    lst = context["list"]
    request = context["request"]

    # The legacy template extends base_print.html (foundation with no
    # navbar/footer) and drops the fighter card into a bare ``#content`` wrapper.
    # ``fighter_card.html`` is un-ported, so bridge it through the DjangoTemplates
    # loader with the same ``with`` overrides the template passes.
    card = raw(
        render_to_string(
            "core/includes/fighter_card.html",
            {
                "fighter": fighter,
                "list": lst,
                "print": True,
                "classes": "d-block",
            },
            request=request,
        )
    )

    content: Node = fragment[
        div(id="content", class_="p-2")[card],
        script(
            src="https://cdn.jsdelivr.net/npm/@iframe-resizer/child@5.3.2",
            type="text/javascript",
            async_=True,
        ),
    ]

    return Page(
        layout="foundation",
        title=f"{fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
