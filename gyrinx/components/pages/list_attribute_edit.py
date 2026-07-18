"""List attribute-edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h2, i, input_, p
from ._shared import back_link, cancel_link


@register_page("core/list_attribute_edit.html")
def edit_list_attribute(context: dict[str, Any]) -> Page:
    lst = context["list"]
    attribute = context["attribute"]
    form_obj = context["form"]
    return_url = context.get("return_url")
    request = context["request"]

    list_url = reverse("core:list", args=[lst.id])

    if return_url:
        back = back_link(context, url=return_url, text="Back to attributes")
        cancel = cancel_link(context, url=return_url)
    else:
        back = back_link(context, url=list_url, text="Back to list")
        cancel = cancel_link(context, url=list_url)

    body: Node = form(method="post")[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None,
        div(class_="mb-3")[raw(str(form_obj["values"]))],
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[raw(str(form_obj.errors))],
        ]
        if form_obj.errors
        else None,
        div(class_="hstack gap-2")[
            button(type="submit", class_="btn btn-success btn-sm")[
                i(class_="bi-check-lg"),
                " Save",
            ],
            cancel,
        ],
    ]

    content: Node = fragment[
        back,
        div(class_="row g-3 mb-3")[
            div(class_="col-lg-8")[
                div(class_="card")[
                    div(class_="card-body")[
                        h2(class_="h5")[attribute.name],
                        p(class_="text-secondary")["Select one option"]
                        if attribute.is_single_select
                        else p(class_="text-secondary")["Select multiple options"],
                        body,
                    ]
                ]
            ]
        ],
    ]
    return Page(
        title=f"Edit {attribute.name} - {lst.name}",
        content=content,
    )
