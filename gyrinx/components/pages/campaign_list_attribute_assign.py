"""Campaign list-attribute assignment form page component."""

from __future__ import annotations

from typing import Any

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h2, i, p
from ._shared import back_link, cancel_link


@register_page("core/campaign/campaign_list_attribute_assign.html")
def campaign_list_attribute_assign(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    list_obj = context["list"]
    attribute_type = context["attribute_type"]
    return_url = context["return_url"]
    request = context["request"]

    error_alert: Node = None
    if form_obj.errors:
        error_alert = div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[raw(str(form_obj.errors))],
        ]

    select_hint = (
        "Select one option"
        if attribute_type.is_single_select
        else "Select multiple options"
    )

    the_form = form(method="post")[
        CsrfInput(request),
        div(class_="mb-3")[raw(str(form_obj["values"]))],
        error_alert,
        div(class_="hstack gap-2")[
            button(type="submit", class_="btn btn-primary btn-sm")[
                i(class_="bi-check-lg"),
                " Save",
            ],
            cancel_link(context, url=return_url),
        ],
    ]

    content: Node = fragment[
        back_link(context, url=return_url, text="Back to Attributes"),
        div(class_="row g-3 mb-3")[
            div(class_="col-lg-8")[
                div(class_="card")[
                    div(class_="card-body")[
                        h2(class_="h5")[attribute_type.name],
                        p(class_="text-secondary mb-3")[list_obj.name],
                        p(class_="text-secondary fs-7")[select_hint],
                        the_form,
                    ]
                ]
            ]
        ],
    ]

    return Page(
        title=f"Assign {attribute_type.name} - {list_obj.name}",
        content=content,
    )
