"""Equipment-assignment delete confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label, p, strong
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


@register_page("core/list_fighter_assign_delete_confirm.html")
def list_fighter_assign_delete_confirm(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    error_message = context.get("error_message")
    request = context["request"]

    equipment_name = assign.content_equipment.name
    full_back_url = reverse(context["back_url"], args=[lst.id, fighter.id])
    action_url = reverse(context["action_url"], args=[lst.id, fighter.id, assign.id])

    error_block: Node = None
    if error_message:
        error_block = Alert(error_message, variant="danger", class_="mb-0")

    if assign.child_fighter:
        reassign_url = reverse(
            "core:list-fighter-gear-reassign", args=[lst.id, fighter.id, assign.id]
        )
        child_block: Node = fragment[
            Alert(
                p[
                    strong["Warning:"],
                    " This will also ",
                    strong["delete ", assign.child_fighter.fully_qualified_name],
                    ", including any modifications, gear, weapons and upgrades.",
                ],
                p["This action cannot be undone."],
                variant="danger",
                class_="mb-last-0",
            ),
            p[
                "If you want to instead keep this ",
                equipment_name,
                " in your stash, or assign it to another fighter, use the ",
                a(href=reassign_url)["Reassign"],
                " option.",
            ],
        ]
    else:
        child_block = Alert(
            strong["Tip:"],
            " If you want to move this equipment to another fighter or to your "
            "stash instead of deleting it, use the Reassign option.",
            variant="info",
            class_="mb-0",
        )

    campaign_block: Node = None
    if lst.is_campaign_mode:
        cost = assign.cost_int()
        if cost < 0:
            campaign_block = fragment[
                Alert(
                    strong["Note:"],
                    " This equipment has a negative cost. Removing it will cost you ",
                    abs(int(cost)),
                    "¢.",
                    variant="warning",
                    class_="mb-0 mt-3",
                ),
                input_(type="hidden", name="refund", value="on"),
            ]
        else:
            campaign_block = _refund_checkbox(lst, cost)

    content: Node = fragment[
        back_link(context, url=full_back_url),
        PageShell(
            h1(class_="h3")[
                "Delete ", equipment_name, " from ", fighter.fully_qualified_name
            ],
            error_block,
            form(action=action_url, method="post")[
                CsrfInput(request),
                p[
                    "Are you sure you want to delete the ",
                    equipment_name,
                    " from ",
                    fighter.name,
                    "?",
                ],
                child_block,
                campaign_block,
                div(class_="mt-3")[
                    input_(type="hidden", name="remove", value="1"),
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    a(href=full_back_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Delete - {equipment_name} - {fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
