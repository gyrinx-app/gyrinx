"""Fighter stats-edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    h5,
    i,
    input_,
    p,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _error_alert(error_message: Any) -> Node:
    if not error_message:
        return None
    return div(class_="alert alert-danger alert-icon mb-0", role="alert")[
        i(class_="bi-exclamation-triangle"),
        div[error_message],
    ]


def _stat_row(field: Any, has_custom_statline: bool) -> Node:
    short_name = (
        field.field.stat_def.short_name
        if has_custom_statline
        else field.field.short_name
    )
    return tr(
        class_=["align-middle", "border-top" if field.field.is_first_of_group else None]
    )[
        td[field.label],
        td[short_name],
        td(class_="text-secondary")[field.field.base_value],
        td[
            field,
            div(class_="invalid-feedback d-block")[field.errors[0]]
            if field.errors
            else None,
        ],
    ]


@register_page("core/list_fighter_stats_edit.html")
def list_fighter_stats_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    error_message = context.get("error_message")
    return_url = context["return_url"]
    request = context["request"]

    has_custom_statline = form_obj.has_custom_statline

    card = div(class_="card")[
        div(class_="card-body")[
            h5(class_="card-title mb-3")["Stat Overrides"],
            p(class_="text-secondary mb-3")[
                "Leave fields empty to use the default values. Enter new values to override the base stats."
            ],
            div(class_="table-responsive")[
                table(class_="table table-borderless table-sm")[
                    thead[
                        tr[
                            th["Stat"],
                            th["Short"],
                            th["Base Value"],
                            th["Override"],
                        ]
                    ],
                    tbody[
                        tuple(
                            _stat_row(field, has_custom_statline) for field in form_obj
                        )
                    ],
                ]
            ],
        ]
    ]

    body = form(
        action=reverse("core:list-fighter-stats-edit", args=[lst.id, fighter.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url),
        card,
        _error_alert(error_message),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=return_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=return_url, text="Back"),
        PageShell(
            h1(class_="h3")[f"Edit Stats: {fighter.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit Stats - {fighter.name} - {lst.name}", content=content)
