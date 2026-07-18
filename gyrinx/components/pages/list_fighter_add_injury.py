"""Add-injury form page component (campaign mode)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, script
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"

# Port of the inline <script> in the legacy template. ``__OUTCOMES__`` is
# replaced with the per-injury ``'id': 'phase',`` lines the ``{% for %}`` loop
# emits. Whitespace is insignificant (the golden test collapses it).
_SCRIPT_TEMPLATE = """
        // Get injury default outcomes from the server
        const injuryDefaultOutcomes = {
            __OUTCOMES__
        };

        // Update fighter state when injury selection changes
        document.getElementById('id_injury').addEventListener('change', function() {
            const selectedInjuryId = this.value;
            const fighterStateSelect = document.getElementById('id_fighter_state');

            if (selectedInjuryId && injuryDefaultOutcomes[selectedInjuryId]) {
                const defaultOutcome = injuryDefaultOutcomes[selectedInjuryId];
                // Only update if not "no_change"
                if (defaultOutcome !== 'no_change') {
                    fighterStateSelect.value = defaultOutcome;
                }
            }
        });

        // Trigger change event on page load if an injury is already selected
        const injurySelect = document.getElementById('id_injury');
        if (injurySelect.value) {
            injurySelect.dispatchEvent(new Event('change'));
        }
    """


@register_page("core/list_fighter_add_injury.html")
def list_fighter_add_injury(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]

    injury_term = fighter.term_injury_singular
    injury_lower = injury_term.lower()
    proximal_lower = fighter.proximal_demonstrative.lower()

    outcomes = "".join(
        f"\n                '{injury.id}': '{injury.phase}',\n            "
        for injury in form_obj.fields["injury"].queryset
    )
    script_body = _SCRIPT_TEMPLATE.replace("__OUTCOMES__", outcomes)

    body = form(
        action=reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")[f"Add {injury_term}"],
            a(
                href=reverse(
                    "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
                ),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(
            context,
            url=reverse("core:list", args=[lst.id]),
            text=lst.name,
        ),
        PageShell(
            h1(class_="h3")[f"Add {injury_term}: {fighter.name}"],
            p[
                f"Adding {proximal_lower}'s {injury_lower} will automatically log "
                "this event to the campaign action log. "
                f"The {injury_lower}'s modifiers will be applied to "
                f"{proximal_lower}'s stats immediately."
            ],
            body,
            kind=FORM_SHELL,
        ),
        script[raw(script_body)],
    ]
    return Page(
        title=f"Add {injury_term} - {fighter.name} - {lst.name}",
        content=content,
    )
