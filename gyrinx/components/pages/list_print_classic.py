"""Classic-mode list print sheet page component.

Port of ``core/list_print_classic.html``, which extends ``base_print.html``
(a chrome-less ``foundation.html``: no navbar/footer, just the document shell).
It overrides three blocks: ``head_title``, ``stylesheet`` (swaps the default
``screen.css`` for ``print_classic.css``), and ``content`` (the classic sheet).

The ``content`` block is a single ``{% include %}`` of the classic sheet, which
in turn tiles ``classic_card.html``; both are un-ported, so we bridge them
through the DjangoTemplates loader with the same ``with`` overrides.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.templatetags.static import static

from ..elements import raw
from ..layout import Page
from ..registry import register_page
from ..tags import link


@register_page("core/list_print_classic.html")
def list_print_classic(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]

    # {% block stylesheet %} replaces foundation's default screen.css.
    stylesheet = link(rel="stylesheet", href=static("core/css/print_classic.css"))

    # {% include "core/includes/classic_sheet.html" with cards=classic_cards
    #   theme="blank" auto_print=True %}
    sheet = raw(
        render_to_string(
            "core/includes/classic_sheet.html",
            {
                "cards": context.get("classic_cards"),
                "theme": "blank",
                "auto_print": True,
            },
            request=request,
        )
    )

    return Page(
        layout="foundation",
        title=f"{lst.name} | {lst.content_house_name}",
        stylesheet=stylesheet,
        content=sheet,
    )
