"""Print-configuration delete confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/print_config/delete.html")
def print_config_delete(context: dict[str, Any]) -> Page:
    lst = context["list"]
    print_config = context["print_config"]
    request = context["request"]

    index_url = reverse("core:print-config-index", args=[lst.id])

    content: Node = fragment[
        back_link(
            context,
            url="core:print-config-index",
            text="Print Configurations",
        ),
        PageShell(
            h1(class_="h3")["Delete Print Configuration"],
            form(
                action=reverse(
                    "core:print-config-delete", args=[lst.id, print_config.id]
                ),
                method="post",
            )[
                CsrfInput(request),
                p[
                    "Are you sure you want to delete the print configuration ",
                    strong[print_config.name],
                    "?",
                ],
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    a(href=index_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Delete Print Configuration - {print_config.name} - {lst.name}",
        content=content,
    )
