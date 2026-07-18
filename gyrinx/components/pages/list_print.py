"""Printable list (gang) sheet page component (port of ``core/list_print.html``).

The legacy template extends ``base_print.html`` (a nav/footer-free
``foundation.html`` variant): it swaps in ``print.css``, renders the shared
``core/includes/list.html`` partial in print mode, and appends a small script
that triggers ``window.print()`` on load. The ``list.html`` include is a large
un-ported partial, so it is bridged through the Django loader with the same
``with`` overrides the template passes.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.templatetags.static import static

from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import div, link, script


@register_page("core/list_print.html")
def list_print(context: dict[str, Any]) -> Page:
    lst = context["list"]
    request = context["request"]
    print_config = context.get("print_config")

    # {% block stylesheet %} — replace the default screen.css with print.css.
    stylesheet = link(rel="stylesheet", href=static("core/css/print.css"))

    # {% block content %} — the un-ported ``list.html`` include is bridged through
    # the Django loader. ``{% include ... with list=list print=True
    # print_config=print_config %}`` passes the full parent context plus those
    # overrides, so mirror that here.
    content: Node = div(id="content", class_="p-2")[
        div(class_="col px-0 vstack gap-4")[
            raw(
                render_to_string(
                    "core/includes/list.html",
                    {
                        **context,
                        "list": lst,
                        "print": True,
                        "print_config": print_config,
                    },
                    request=request,
                )
            )
        ]
    ]

    # {% block extra_body %} — auto-open the print dialog once the page loads.
    extra_script = script[
        raw(
            'document.addEventListener("DOMContentLoaded", function() {'
            "window.print();"
            "});"
        )
    ]

    return Page(
        title=f"{lst.name} | {lst.content_house_name}",
        layout="foundation",
        stylesheet=stylesheet,
        content=content,
        extra_script=extra_script,
    )
