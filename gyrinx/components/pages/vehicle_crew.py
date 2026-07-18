"""Vehicle crew selection (step 2 of the vehicle addition flow) page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h3, i, label


@register_page("core/vehicle_crew.html")
def vehicle_crew(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]
    vehicle_equipment = context["vehicle_equipment"]
    request = context["request"]

    crew_name = form_obj["crew_name"]
    crew_fighter = form_obj["crew_fighter"]

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
            {"step": 2, "total_steps": 3, "title": "Add Vehicle"},
            request=request,
        )
    )

    body = form(method="post", class_="vstack gap-4 mt-3")[
        CsrfInput(request),
        raw(str(form_obj["action"])),
        div[
            label(for_=crew_name.id_for_label, class_="form-label")[crew_name.label],
            raw(str(crew_name.errors)),
            raw(str(crew_name)),
        ],
        div[
            label(for_=crew_fighter.id_for_label, class_="form-label")[
                crew_fighter.label
            ],
            raw(str(crew_fighter.errors)),
            raw(str(crew_fighter)),
        ],
        div(class_="hstack gap-3 align-items-center")[
            button(type="submit", class_="btn btn-primary")[
                "Next ", i(class_="bi-arrow-right")
            ],
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
                h3(class_="h5 mb-0")[
                    f"Select crew for {vehicle_equipment.name} "
                    f"({vehicle_equipment.cost}¢)"
                ],
            ],
            body,
        ],
    ]

    return Page(
        title=f"Select Crew - {lst.name}",
        content=content,
    )
