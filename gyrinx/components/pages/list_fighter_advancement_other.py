"""'Other' free-text advancement description form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h3, i, label, nav, span


@register_page("core/list_fighter_advancement_other.html")
def list_fighter_advancement_other(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    params = context["params"]
    request = context["request"]

    from gyrinx.core.templatetags.custom_tags import qt

    progress = render_to_string(
        "core/includes/advancement_progress.html",
        {
            **context,
            "current_step": 2,
            "total_steps": 3,
            "progress": 66,
        },
        request=request,
    )

    field = form_obj["description"]
    non_field_errors = form_obj.non_field_errors()

    back_href = (
        reverse("core:list-fighter-advancement-type", args=[lst.id, fighter.id])
        + "?"
        + qt(request)
    )

    body = form(
        method="post",
        class_="vstack gap-4",
        aria_label="Describe advancement form",
    )[
        CsrfInput(request),
        div(class_="alert alert-danger alert-icon mb-last-0 mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[non_field_errors],
        ]
        if non_field_errors
        else None,
        div(class_="vstack gap-3")[
            div(class_="alert alert-secondary alert-icon mb-0", role="alert")[
                i(class_="bi-info-circle"),
                div(class_="d-flex justify-content-between flex-grow-1")[
                    div[
                        "Available XP: ",
                        span(class_="badge text-bg-primary")[fighter.xp_current],
                    ],
                    div[
                        "Cost: ",
                        span(class_="badge text-bg-warning")[params.xp_cost, " XP"],
                    ],
                ],
            ],
            div[
                label(for_=field.id_for_label, class_="form-label")[field.label],
                raw(str(field)),
                div(class_="form-text")[field.help_text] if field.help_text else None,
                div(class_="invalid-feedback d-block")[field.errors]
                if field.errors
                else None,
            ],
        ],
        nav(class_="hstack gap-3", aria_label="Form navigation")[
            a(href=back_href, class_="icon-link")[
                i(class_="bi-chevron-left"),
                " Back",
            ],
            button(
                type="submit",
                class_="btn btn-primary",
                aria_describedby="continue-help",
            )["Continue"],
            span(id="continue-help", class_="visually-hidden")[
                "Continue to the next step of the advancement workflow"
            ],
        ],
    ]

    content: Node = div(class_="col-12 col-md-8 col-lg-6 vstack gap-4")[
        div(class_="vstack gap-1")[
            raw(progress),
            h3(class_="h5 mb-0")["Describe Advancement"],
        ],
        body,
    ]

    return Page(title=f"New Advancement - {fighter.name}", content=content)
