"""Print-configuration create/edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, i, label, p, script, small, span
from ._shared import cancel_link

# The legacy shell keeps ``px-0`` (unlike the ``form`` preset), so pass the exact
# class string as ``kind`` (PageShell falls back to the string verbatim).
FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"

# Verbatim client-side enhancement script from the legacy template. The golden
# test collapses whitespace, so exact indentation is not load-bearing.
_SCRIPT = """
        document.addEventListener('DOMContentLoaded', () => {
            const modeRadios = document.querySelectorAll('input[name="fighter_selection_mode"]');
            const fighterCheckboxes = document.querySelectorAll('#fighter-checkboxes input[type="checkbox"]');
            const fighterCheckboxesContainer = document.getElementById('fighter-checkboxes');

            function updateFighterCheckboxesState() {
                const selectedMode = document.querySelector('input[name="fighter_selection_mode"]:checked')?.value;

                if (selectedMode === 'specific') {
                    // Enable fighter checkboxes
                    fighterCheckboxes.forEach(checkbox => {
                        checkbox.disabled = false;
                    });
                    if (fighterCheckboxesContainer) {
                        fighterCheckboxesContainer.style.opacity = '1';
                    }
                } else {
                    // Disable and uncheck fighter checkboxes
                    fighterCheckboxes.forEach(checkbox => {
                        checkbox.disabled = true;
                        checkbox.checked = false;
                    });
                    if (fighterCheckboxesContainer) {
                        fighterCheckboxesContainer.style.opacity = '0.5';
                    }
                }
            }

            // Update state when mode changes
            modeRadios.forEach(radio => {
                radio.addEventListener('change', updateFighterCheckboxesState);
            });

            // Set initial state
            updateFighterCheckboxesState();
        });
    """


def _labeled_field(bf: Any) -> Node:
    """Label / errors / widget / help-text block (name + blank-card fields)."""
    return div[
        label(for_=bf.id_for_label, class_="form-label")[bf.label],
        raw(str(bf.errors)),
        raw(str(bf)),
        small(class_="form-text text-secondary")[bf.help_text],
    ]


def _radio_rows(bound_field: Any) -> Node:
    """A ``form-check`` row per radio subwidget (card style / selection mode)."""
    return tuple(
        div(class_="form-check")[
            raw(str(choice.tag())),
            label(class_="form-check-label", for_=choice.id_for_label)[
                choice.choice_label
            ],
        ]
        for choice in bound_field
    )


def _checkbox_row(bf: Any, text: str) -> Node:
    """A ``form-check`` row for a single boolean field with a fixed label."""
    return div(class_="form-check")[
        raw(str(bf)),
        label(class_="form-check-label", for_=bf.id_for_label)[text],
    ]


@register_page("core/print_config/form.html")
def print_config_form(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    title = context["title"]
    print_config = context.get("print_config")
    request = context.get("request")

    # {% include "core/includes/list_common_header.html" with list=list link_list="true" %}
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {**context, "list": lst, "link_list": "true"},
            request=request,
        )
    )

    included_fighters = form_obj["included_fighters"]
    if included_fighters.field.queryset:
        fighter_block: Node = div(class_="vstack gap-2", id="fighter-checkboxes")[
            tuple(raw(str(choice)) for choice in included_fighters)
        ]
    else:
        fighter_block = p(class_="text-secondary mb-0", id="no-fighters-message")[
            "No fighters available."
        ]

    body = form(method="post", class_="vstack gap-4")[
        CsrfInput(request),
        raw("<!-- Configuration Name -->"),
        _labeled_field(form_obj["name"]),
        raw("<!-- Card Style Section -->"),
        div[
            h2(class_="h5 mb-3")["Card style"],
            div(class_="vstack gap-2")[_radio_rows(form_obj["card_style"])],
            p(class_="text-secondary fs-7 mb-0 mt-2")[
                "Classic cards print Fighter cards only — the Asset, Attribute, "
                "Action, and Stash options below apply to Web cards."
            ],
        ],
        raw("<!-- Card Types Section -->"),
        div[
            h2(class_="h5 mb-3")["Card Types"],
            p(class_="text-secondary fs-7 mb-3")[
                "Select which types of cards to include in the print output."
            ],
            div(class_="vstack gap-2")[
                _checkbox_row(form_obj["include_assets"], "Include Asset Card"),
                _checkbox_row(form_obj["include_attributes"], "Include Attribute Card"),
                _checkbox_row(form_obj["include_stash"], "Include Stash Card"),
                _checkbox_row(form_obj["include_actions"], "Include Action Card"),
                _checkbox_row(
                    form_obj["include_dead_fighters"], "Include Dead Fighters"
                ),
            ],
        ],
        raw("<!-- Fighter Selection Section -->"),
        div[
            h2(class_="h5 mb-3")["Fighter Selection"],
            p(class_="text-secondary fs-7 mb-3")[included_fighters.help_text],
            div(class_="border rounded p-3 overflow-auto")[
                div(class_="vstack gap-2 mb-3 border-bottom pb-3")[
                    _radio_rows(form_obj["fighter_selection_mode"])
                ],
                fighter_block,
            ],
        ],
        raw("<!-- Blank Cards Section -->"),
        div(class_="border rounded p-3")[
            h2(class_="h5 mb-0")[
                button(
                    class_="btn btn-link text-decoration-none p-0 text-start w-100 d-flex align-items-center",
                    type="button",
                    data_bs_toggle="collapse",
                    data_bs_target="#blankCardsCollapse",
                    aria_expanded="false",
                    aria_controls="blankCardsCollapse",
                )[
                    span(class_="me-2")["Blank Cards"],
                    i(
                        class_="bi-chevron-down ms-auto",
                        data_gy_collapse_icon="blankCardsCollapse",
                    ),
                ]
            ],
            p(class_="text-secondary fs-7 mb-0")[
                "Add blank cards to fill in at the table (e.g., when gaining new fighters)."
            ],
            div(class_="collapse", id="blankCardsCollapse")[
                div(class_="vstack gap-3 mt-3")[
                    _labeled_field(form_obj["blank_fighter_cards"]),
                    _labeled_field(form_obj["blank_vehicle_cards"]),
                ]
            ],
        ],
        raw("<!-- Form Actions -->"),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")[
                "Update" if print_config else "Create",
                " Configuration",
            ],
            cancel_link(
                context,
                url=reverse("core:print-config-index", args=[lst.id]),
            ),
        ],
    ]

    content: Node = fragment[
        header,
        PageShell(h1(class_="h3")[title], body, kind=FORM_SHELL),
        script[raw(_SCRIPT)],
    ]
    return Page(title=f"{title} - {lst.name}", content=content)
