"""Vehicle selection (step 1 of the vehicle addition flow) page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h3, i, label


@register_page("core/vehicle_select.html")
def vehicle_select(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]
    request = context["request"]

    field = form_obj["vehicle_equipment"]

    # Un-ported includes bridged through the DjangoTemplates loader with the same
    # ``with`` overrides the legacy template passes.
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )
    step_progress = raw(
        render_to_string(
            "core/includes/step_progress.html",
            {"step": 1, "total_steps": 3, "title": "Add Vehicle"},
            request=request,
        )
    )

    body = form(method="post", class_="vstack gap-4 mt-3")[
        CsrfInput(request),
        div[
            label(for_=field.id_for_label, class_="form-label")[field.label],
            raw(str(field.errors)),
            raw(str(field)),
        ],
        div(class_="hstack gap-3 align-items-center")[
            button(
                type="submit",
                name="action",
                value="select_crew",
                class_="btn btn-primary",
            )["Select Crew fighter ", i(class_="bi-arrow-right")],
            "or",
            button(
                type="submit",
                name="action",
                value="add_to_stash",
                class_="btn btn-secondary",
            )["Add to Stash ", i(class_="bi-arrow-right")],
            a(href=reverse("core:list", args=[lst.id]), class_="link-secondary")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        header,
        div(class_="col-12 col-md-8 col-lg-6")[
            div(class_="vstack gap-1")[
                step_progress,
                h3(class_="h5 mb-0")["Select a vehicle"],
            ],
            body,
        ],
    ]

    return Page(
        title=f"Select Vehicle - {lst.name}",
        content=content,
    )
