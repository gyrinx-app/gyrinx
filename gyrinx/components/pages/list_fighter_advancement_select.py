"""Advancement select page component (choose skill / equipment for a fighter)."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import title as title_filter
from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h3, i, nav, span


@register_page("core/list_fighter_advancement_select.html")
def list_fighter_advancement_select(context: dict[str, Any]) -> Page:
    request = context["request"]
    lst = context["list"]
    fighter = context["fighter"]
    advancement_type = context.get("advancement_type")
    is_random = context.get("is_random")
    advancement_name = context.get("advancement_name")
    skill_type = context.get("skill_type")

    progress = raw(
        render_to_string(
            "core/includes/advancement_progress.html",
            {**context, "total_steps": context["steps"]},
            request=request,
        )
    )

    if advancement_type == "equipment":
        heading: Node = fragment[
            "Accept" if is_random else "Choose",
            " ",
            advancement_name,
        ]
        fields = raw(
            render_to_string(
                "core/includes/advancement_equipment_form.html",
                context,
                request=request,
            )
        )
    else:
        heading = fragment[
            "Choose ",
            title_filter(skill_type),
            " Skill",
            " Set" if is_random else None,
        ]
        fields = raw(
            render_to_string(
                "core/includes/advancement_skill_form.html",
                context,
                request=request,
            )
        )

    body = div(class_="col-12 col-md-8 col-lg-6 vstack gap-4")[
        div(class_="vstack gap-3")[
            div(class_="vstack gap-1")[
                progress,
                h3(class_="h5 mb-0")[heading],
            ],
        ],
        form(
            method="post",
            class_="vstack gap-3",
            aria_label=f"Choose {advancement_type or 'skill'} form",
        )[
            CsrfInput(request),
            fields,
            nav(class_="hstack gap-3", aria_label="Form navigation")[
                a(
                    href=reverse(
                        "core:list-fighter-advancement-type",
                        args=[lst.id, fighter.id],
                    ),
                    class_="icon-link",
                )[
                    i(class_="bi-chevron-left"),
                    " Back",
                ],
                button(
                    type="submit",
                    class_="btn btn-success",
                    aria_describedby="confirm-help",
                )[
                    i(class_="bi-check-lg", aria_hidden="true"),
                    " Confirm Advancement",
                ],
                span(id="confirm-help", class_="visually-hidden")[
                    "Confirm and save the selected advancement"
                ],
            ],
        ],
    ]

    return Page(title=f"Select Advancement - {fighter.name}", content=body)
