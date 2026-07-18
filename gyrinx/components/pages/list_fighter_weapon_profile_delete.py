"""Weapon-profile delete confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label, p
from ._shared import back_link

SHELL = "col-lg-12 px-0 vstack gap-3"


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


@register_page("core/list_fighter_weapon_profile_delete.html")
def list_fighter_weapon_profile_delete(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    profile = context["profile"]
    profile_cost = context["profile_cost"]

    return_url = reverse(
        "core:list-fighter-weapon-edit", args=[lst.id, fighter.id, assign.id]
    )
    equipment_name = assign.content_equipment.name

    content = fragment[
        back_link(context, url=return_url, text="Back to Weapon Edit"),
        PageShell(
            h1(class_="h3")[f"Delete: {profile.name} from {equipment_name}"],
            form(
                action=reverse(
                    "core:list-fighter-weapon-profile-delete",
                    args=[lst.id, fighter.id, assign.id, profile.id],
                ),
                method="post",
            )[
                CsrfInput(context["request"]),
                p[
                    f"Are you sure you want to remove the {profile.name} profile "
                    f"from the {equipment_name} assigned to {fighter.name}?"
                ],
                _refund_checkbox(lst, profile_cost),
                div(class_="mt-3")[
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    a(href=return_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=SHELL,
        ),
    ]
    return Page(
        title=(
            f"Delete - {profile.name} from {equipment_name} - "
            f"{fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
