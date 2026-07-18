"""Vehicle confirmation (step 3 of the vehicle addition flow) page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, dd, div, dl, dt, form, h3, i, strong


@register_page("core/vehicle_confirm.html")
def vehicle_confirm(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]
    vehicle_equipment = context["vehicle_equipment"]
    crew_fighter = context.get("crew_fighter")
    crew_name = context.get("crew_name")
    vehicle_cost = context["vehicle_cost"]
    crew_cost = context["crew_cost"]
    total_cost = context["total_cost"]
    request = context["request"]

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
            {"step": 3, "total_steps": 3, "title": "Buy Vehicle"},
            request=request,
        )
    )

    if crew_fighter:
        crew_rows: Node = fragment[
            dt(class_="col-sm-4")["Crew"],
            dd(class_="col-sm-8")[
                strong[crew_name],
                f" — {crew_fighter.type} ({crew_cost}¢)",
            ],
        ]
    else:
        crew_rows = fragment[
            dt(class_="col-sm-4 text-secondary")["Crew"],
            dd(class_="col-sm-8 text-secondary")["Adding to stash, no crew selected."],
        ]

    content: Node = fragment[
        header,
        div(class_="col-12 col-md-8 col-lg-6")[
            div(class_="vstack gap-1")[
                step_progress,
                h3(class_="h5 mb-0")["Confirm vehicle and crew"],
            ],
            div(class_="vstack gap-4 mt-3")[
                dl(class_="row my-3")[
                    dt(class_="col-sm-4")["Vehicle"],
                    dd(class_="col-sm-8")[
                        strong[vehicle_equipment.name],
                        f" ({vehicle_cost}¢)",
                    ],
                    crew_rows,
                    dt(class_="col-sm-4 border-top pt-2 mt-1")["Total Cost"],
                    dd(class_="col-sm-8 border-top pt-2 mt-1")[
                        strong[f"{total_cost}¢"],
                    ],
                ],
                form(method="post")[
                    CsrfInput(request),
                    raw(str(form_obj["confirm"])),
                    div(class_="hstack gap-3 align-items-center")[
                        button(type="submit", class_="btn btn-success")[
                            i(class_="bi-check-lg"), " Buy Vehicle"
                        ],
                        a(
                            href=reverse("core:list", args=[lst.id]),
                            class_="link-secondary",
                        )["Cancel"],
                    ],
                ],
            ],
        ],
    ]

    return Page(
        title=f"Confirm Vehicle - {lst.name}",
        content=content,
    )
