"""List credits-edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, li, span, ul


@register_page("core/list_credits_edit.html")
def edit_list_credits(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    request = context["request"]

    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
        },
        request=request,
    )

    body = form(method="post")[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="hstack gap-2 mt-3 align-items-center")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        div(class_="container")[
            raw(header),
            div(class_="row")[
                div(class_="col-12 col-md-8 col-lg-6")[
                    h1(class_="h3")[f"Edit Credits for {lst.name}"],
                    ul(class_="fs-5 mb-3 list-group list-group-flush")[
                        li(class_="list-group-item")[
                            span(class_="badge text-bg-primary")[
                                f"{lst.credits_current}¢"
                            ],
                            " Current",
                        ],
                        li(class_="list-group-item")[
                            span(class_="badge text-bg-secondary")[
                                f"{lst.credits_earned}¢"
                            ],
                            " Total Earned",
                        ],
                    ],
                    body,
                ],
            ],
        ],
    ]
    return Page(title=f"Credits - {lst.name}", content=content)
