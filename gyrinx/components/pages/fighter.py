"""Fighter page components."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, input_, label, p
from ._shared import back_link, cancel_link


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


@register_page("core/list_fighter_delete.html")
def list_fighter_delete(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    fighter_cost = context.get("fighter_cost")

    content = fragment[
        back_link(context, text=lst.name),
        PageShell(
            h1(class_="h3")[f"Delete: {fighter.fully_qualified_name}"],
            form(
                action=reverse("core:list-fighter-delete", args=[lst.id, fighter.id]),
                method="post",
            )[
                CsrfInput(context["request"]),
                p["Are you sure you want to delete this fighter?"],
                _refund_checkbox(lst, fighter_cost),
                div(class_="mt-3")[
                    input_(type="hidden", name="archive", value="1"),
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    cancel_link(context, url=reverse("core:list", args=[lst.id])),
                ],
            ],
            kind="col-12 col-md-8 col-lg-6 px-0 vstack gap-3",
        ),
    ]
    return Page(
        title=f"Delete - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
