"""Fighter advancement dice-choice form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    em,
    fieldset,
    form,
    h3,
    h4,
    i,
    legend,
    nav,
    option,
    select,
    span,
)


@register_page("core/list_fighter_advancement_dice_choice.html")
def advancement_dice_choice(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    fighter = context["fighter"]
    lst = context["list"]
    can_roll_dice = context["can_roll_dice"]
    fighter_category = context["fighter_category"]
    request = context["request"]

    # Un-ported include: bridge through the DjangoTemplates loader with the same
    # ``with`` overrides the legacy template passes.
    progress = raw(
        render_to_string(
            "core/includes/advancement_progress.html",
            {**context, "current_step": 1, "total_steps": 3, "progress": 33},
            request=request,
        )
    )

    non_field_errors = form_obj.non_field_errors()

    def dice_select(name: str, aria_label: str) -> Node:
        return select(
            name=name,
            class_="form-select",
            disabled=not can_roll_dice,
            aria_label=aria_label,
        )[
            option(value="", selected=True, disabled=True)["-"],
            tuple(option(value=digit)[digit] for digit in "123456"),
        ]

    if can_roll_dice:
        roll_alert: Node = div(class_="alert alert-info alert-icon mb-0", role="alert")[
            i(class_="bi-info-circle"),
            div[
                "The roll will ",
                em["immediately"],
                " be added to the campaign action log.",
            ],
        ]
    else:
        roll_alert = div(class_="alert alert-warning alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[
                f"Only Gangers and Exotic Beasts can roll for advancements. "
                f"{fighter.name} is a {fighter_category} and must choose manually."
            ],
        ]

    body = form(
        method="post",
        class_="vstack gap-2",
        aria_label="Roll for advancement form",
    )[
        CsrfInput(request),
        div(class_="alert alert-danger alert-icon mb-last-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[raw(str(non_field_errors))],
        ]
        if non_field_errors
        else None,
        div(class_="row g-3")[
            div(class_="col-12")[
                div(class_="card h-100 shadow-sm")[
                    div(class_="card-body vstack gap-3")[
                        h4(class_="card-title")["Roll for random advancement"],
                        roll_alert,
                        div(class_="vstack gap-2")[
                            nav(aria_label="Form navigation")[
                                button(
                                    type="submit",
                                    name="roll_action",
                                    value="roll_auto",
                                    class_="btn btn-primary",
                                    disabled=not can_roll_dice,
                                    aria_describedby="roll-help",
                                )["Generate a 2D6 roll"]
                            ],
                            span(id="roll-help", class_="visually-hidden")[
                                "Automatically roll 2D6 for the advancement"
                            ],
                        ],
                        fieldset(class_="vstack gap-2")[
                            legend(id="tabletop-result-label")[
                                "Or enter a tabletop result:"
                            ],
                            div(
                                class_="input-group",
                                aria_describedby="tabletop-result-label",
                            )[
                                dice_select("d6_1", "First D6 result"),
                                dice_select("d6_2", "Second D6 result"),
                                button(
                                    class_="btn btn-outline-primary",
                                    type="submit",
                                    name="roll_action",
                                    value="roll_manual",
                                    disabled=not can_roll_dice,
                                )["Confirm result"],
                            ],
                        ],
                    ]
                ]
            ],
            div(class_="col-12")[
                div(class_="card h-100 shadow-sm")[
                    div(class_="card-body vstack gap-3")[
                        h4(class_="card-title")["Choose advancement"],
                        fieldset(class_="vstack gap-2 mb-0")[
                            legend(
                                class_="form-label mb-1", id="choose-advancement-label"
                            )[
                                "Already rolled? Skip this step and select an "
                                "advancement to apply."
                            ],
                            div(
                                class_="hstack gap-3",
                                aria_describedby="choose-advancement-label",
                            )[
                                a(
                                    href=reverse(
                                        "core:list-fighter-advancement-type",
                                        args=[lst.id, fighter.id],
                                    ),
                                    id="spend_xp_link",
                                    class_="btn btn-outline-secondary",
                                )[
                                    "Select",
                                    i(class_="bi-arrow-right", aria_hidden="true"),
                                ]
                            ],
                        ],
                    ]
                ]
            ],
        ],
    ]

    content: Node = div(class_="col-12 col-md-8 col-lg-6 vstack gap-4")[
        div(class_="vstack gap-1")[
            progress,
            h3(class_="h5 mb-0")[f"How will {fighter.name} advance?"],
        ],
        body,
    ]

    return Page(
        title=f"Advancement Roll - {fighter.name}",
        content=content,
    )
