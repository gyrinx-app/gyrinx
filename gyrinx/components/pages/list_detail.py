"""Gang detail (list) page component — the large gang view.

This page's ``core/list.html`` template is almost entirely a single
``{% include "core/includes/list.html" %}`` (the header, meta strip, action
menu, campaign cards, fighter grid and embed offcanvas — ~420 lines of markup
with many nested sub-includes). Rather than port that whole tree, we reproduce
the thin page-level wrapper and bridge the include through the DjangoTemplates
loader.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div


@register_page("core/list.html")
def list_detail(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]

    # Legacy:
    #   {% include "core/includes/list.html" with list=list
    #      campaign_resources=campaign_resources held_assets=held_assets
    #      has_stash_fighter=has_stash_fighter subscribed_packs=subscribed_packs %}
    #
    # The include has no `only`, so it inherits the full parent context on top of
    # those five overrides. Each override simply rebinds a name to its own current
    # value, so spreading the whole page context reproduces the include's context
    # exactly. Names genuinely absent from the context (e.g. campaign_resources on
    # a list-building gang) resolve to string_if_invalid identically whether they
    # are rebound by the `with` or left to resolve on reference — so we don't add
    # them (adding them as None would diverge from the legacy '' binding).
    body = raw(
        render_to_string(
            "core/includes/list.html",
            {**context, "list": lst},
            request=request,
        )
    )

    content: Node = div(class_="col-lg-12 px-0 vstack gap-4")[body]

    return Page(
        title=f"{lst.name} | {lst.owner_cached}",
        content=content,
    )
