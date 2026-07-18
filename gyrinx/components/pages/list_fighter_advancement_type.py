"""Advancement type selection form page component (choose advancement + costs)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import json_script

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h3, i, label, nav, script, span, strong


def _dice_roll_alert(campaign_action: Any) -> Node:
    """Port of the ``{% if campaign_action %}`` dice-roll summary alert."""
    results = list(campaign_action.dice_results or [])
    inner: list[Node] = []
    for index, result in enumerate(results):
        inner.append(str(result))
        if index != len(results) - 1:
            inner.append(" + ")
    return div(class_="alert alert-info alert-icon mb-0", role="alert")[
        i(class_="bi-dice-6"),
        div[
            strong["Dice Roll:"],
            " ",
            tuple(inner),
            " = ",
            strong[campaign_action.dice_total],
        ],
    ]


def _extra_script(context: dict[str, Any], form_obj: Any) -> Node:
    """Verbatim port of the template's {% block extra_script %} — pushes the
    per-advancement config JSON and wires the select's change handler to the
    XP/cost inputs."""
    choice_id = form_obj["advancement_choice"].id_for_label
    xp_id = form_obj["xp_cost"].id_for_label
    cost_id = form_obj["cost_increase"].id_for_label
    js = f"""
    // Advancement configurations passed from the server
    const advancementConfigs = JSON.parse(
        document.getElementById('advancement-configs').textContent
    );

    // Get references to form elements
    const advancementSelect = document.getElementById('{choice_id}');
    const xpCostInput = document.getElementById('{xp_id}');
    const costIncreaseInput = document.getElementById('{cost_id}');

    // Update costs when advancement type changes
    function updateCosts() {{
        const selectedValue = advancementSelect.value;
        const config = advancementConfigs[selectedValue];

        if (config) {{
            // Update XP cost and fighter cost increase
            xpCostInput.value = config.xp_cost;
            costIncreaseInput.value = config.cost_increase;
        }}
    }}

    // Listen for changes to the advancement selection
    if (advancementSelect) {{
        advancementSelect.addEventListener('change', updateCosts);

        // Update costs on page load if a value is already selected
        if (advancementSelect.value) {{
            updateCosts();
        }}
    }}
    """
    return fragment[
        json_script(context["advancement_configs"], "advancement-configs"),
        script[raw(js)],
    ]


@register_page("core/list_fighter_advancement_type.html")
def list_fighter_advancement_type(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    campaign_action = context.get("campaign_action")
    request = context["request"]

    # Un-ported {% include advancement_progress.html with total_steps=steps %}:
    # bridge it through the DjangoTemplates loader with the same context the
    # legacy include receives (full page context + the with-override).
    progress = raw(
        render_to_string(
            "core/includes/advancement_progress.html",
            {**context, "total_steps": context["steps"]},
            request=request,
        )
    )

    choice_field = form_obj["advancement_choice"]
    xp_cost_field = form_obj["xp_cost"]
    cost_increase_field = form_obj["cost_increase"]
    non_field_errors = form_obj.non_field_errors()

    # The legacy template guards the Back link with {% if step > 1 %}; the view
    # never supplies ``step`` so it renders nothing, but reproduce the guard.
    step = context.get("step")
    show_back = isinstance(step, int) and step > 1

    body = form(
        method="post",
        class_="vstack gap-4",
        aria_label="Select advancement form",
    )[
        CsrfInput(request),
        raw(str(form_obj["campaign_action_id"])),
        div(class_="alert alert-danger alert-icon mb-last-0 mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[non_field_errors],
        ]
        if non_field_errors
        else None,
        div(class_="vstack gap-3")[
            div(class_="alert alert-secondary alert-icon mb-0", role="alert")[
                i(class_="bi-info-circle"),
                div[
                    "Available XP: ",
                    span(class_="badge text-bg-primary")[fighter.xp_current],
                ],
            ],
            div[
                label(class_="form-label")["Advancement"],
                div(class_="vstack gap-2")[raw(str(choice_field))],
                div(class_="invalid-feedback d-block")[choice_field.errors[0]]
                if choice_field.errors
                else None,
            ],
            div(class_="row")[
                div(class_="col-md-6")[
                    label(for_=xp_cost_field.id_for_label, class_="form-label")[
                        "XP Spend"
                    ],
                    raw(str(xp_cost_field)),
                    div(class_="form-text")[xp_cost_field.help_text],
                    div(class_="invalid-feedback d-block")[xp_cost_field.errors[0]]
                    if xp_cost_field.errors
                    else None,
                ],
                div(class_="col-md-6")[
                    label(for_=cost_increase_field.id_for_label, class_="form-label")[
                        "Fighter Rating Increase"
                    ],
                    raw(str(cost_increase_field)),
                    div(class_="form-text")[cost_increase_field.help_text],
                    div(class_="invalid-feedback d-block")[
                        cost_increase_field.errors[0]
                    ]
                    if cost_increase_field.errors
                    else None,
                ],
            ],
        ],
        nav(class_="vstack gap-3", aria_label="Form navigation")[
            div(class_="hstack gap-3")[
                a(
                    href=reverse(
                        "core:list-fighter-advancement-dice-choice",
                        args=[lst.id, fighter.id],
                    ),
                    class_="icon-link",
                )[
                    i(class_="bi-chevron-left"),
                    " Back",
                ]
                if show_back
                else None,
                button(
                    type="submit",
                    class_="btn btn-primary",
                    aria_describedby="nav-help",
                )[
                    "Next ",
                    i(class_="bi-arrow-right", aria_hidden="true"),
                ],
            ],
            span(id="nav-help", class_="visually-hidden")[
                "Navigate to the next step of the advancement workflow"
            ],
        ],
    ]

    content: Node = div(class_="col-12 col-md-8 col-lg-6 vstack gap-4")[
        div(class_="vstack gap-1")[
            progress,
            h3(class_="h5 mb-0")["Select Advancement"],
        ],
        _dice_roll_alert(campaign_action) if campaign_action else None,
        body,
    ]

    return Page(
        title=f"New Advancement - {fighter.name}",
        content=content,
        extra_script=_extra_script(context, form_obj),
    )
