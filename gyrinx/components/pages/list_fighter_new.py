"""Add-a-Fighter form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from .. import bridge
from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_fighter_new.html")
def new_list_fighter(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]
    request = context["request"]

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    body = form(
        action=reverse("core:list-fighter-new", args=[lst.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Add Fighter"],
            a(
                # Template writes {% safe_referer list.get_absolute_url %}, but List has
                # no get_absolute_url, so Django resolves it to "" (silent invalid var).
                href=bridge.safe_referer(request, ""),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        header,
        PageShell(h1(class_="h3")["Add a Fighter"], body, kind=FORM_SHELL),
    ]
    return Page(title=f"Add a Fighter to {lst.name}", content=content)
