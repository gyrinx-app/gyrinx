"""List-fighter equipment upgrade delete confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _refund_checkbox(lst: Any, refund_cost: Any) -> Node:
    """Port of ``core/includes/refund_checkbox.html`` (campaign mode only)."""
    if not lst.is_campaign_mode:
        return None
    return div(class_="form-check mt-3")[
        input_(
            class_="form-check-input",
            type="checkbox",
            name="refund",
            id="refund",
            checked=True,
        ),
        label(class_="form-check-label", for_="refund")[
            f"Apply refund (+{refund_cost}¢ to credits)"
        ],
    ]


@register_page("core/list_fighter_assign_upgrade_delete_confirm.html")
def list_fighter_assign_upgrade_delete_confirm(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    upgrade = context["upgrade"]
    upgrade_cost = context["upgrade_cost"]
    action_url = context["action_url"]
    return_url = context["return_url"]
    request = context["request"]

    equipment = assign.content_equipment
    stack_display = equipment.upgrade_stack_name_display

    querystring = "?" + request.GET.urlencode()
    action = (
        reverse(action_url, args=[lst.id, fighter.id, assign.id, upgrade.id])
        + querystring
    )

    # Heading text only ("Delete X from Y"); the "delete ... from" wording trips
    # bandit's SQL-injection heuristic (B608) on the next line — it is not SQL.
    heading = (
        f"Delete {upgrade.name} {stack_display} from {equipment.name} "  # nosec B608
        f"for {fighter.fully_qualified_name}"
    )
    content: Node = fragment[
        back_link(context, url=return_url),
        PageShell(
            h1(class_="h3")[heading],
            form(action=action, method="post")[
                CsrfInput(request),
                p[
                    f"Are you sure you want to delete the {upgrade.name} "
                    f"{stack_display} from the {equipment.name} assigned to "
                    f"{fighter.name}?"
                ],
                _refund_checkbox(lst, upgrade_cost),
                div(class_="mt-3")[
                    input_(type="hidden", name="remove", value="1"),
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    a(href=return_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Delete - {upgrade.name} - {equipment.name} - "
            f"{fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
