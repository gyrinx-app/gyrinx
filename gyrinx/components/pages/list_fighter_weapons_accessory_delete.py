"""Weapon-accessory delete confirmation page component."""

from __future__ import annotations

from typing import Any

from django.http import QueryDict
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label, p
from ._shared import back_link

SHELL = "col-lg-12 px-0 vstack gap-3"


def _querystring(request: Any) -> str:
    """Port of Django's built-in ``{% querystring %}`` tag with no arguments:
    rebuild ``request.GET`` and return it prefixed with ``?`` (``"?"`` when
    empty)."""
    params = QueryDict(mutable=True)
    for key, values in request.GET.lists():
        params.setlist(key, [v for v in values if v is not None])
    query_string = params.urlencode() if params else ""
    return f"?{query_string}"


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


@register_page("core/list_fighter_weapons_accessory_delete.html")
def list_fighter_weapons_accessory_delete(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    assign = context["assign"]
    accessory = context["accessory"]
    accessory_cost = context["accessory_cost"]
    return_url = context["return_url"]
    request = context["request"]

    equipment_name = assign.content_equipment.name

    action = reverse(
        "core:list-fighter-weapon-accessory-delete",
        args=[lst.id, fighter.id, assign.id, accessory.id],
    ) + _querystring(request)

    content = fragment[
        back_link(context, url=return_url),
        PageShell(
            h1(class_="h3")[
                f"Delete: {accessory.name} from the {equipment_name} "
                f"assigned to {fighter.fully_qualified_name}"
            ],
            form(action=action, method="post")[
                CsrfInput(request),
                p[
                    f"Are you sure you want to delete the {accessory.name} "
                    f"from the {equipment_name} assigned to {fighter.name}?"
                ],
                _refund_checkbox(lst, accessory_cost),
                div(class_="mt-3")[
                    input_(type="hidden", name="remove", value="1"),
                    button(type="submit", class_="btn btn-danger")["Delete"],
                    a(href=return_url, class_="btn btn-link")["Cancel"],
                ],
            ],
            kind=SHELL,
        ),
    ]
    return Page(
        title=(
            f"Delete - {accessory.name} from {equipment_name} - "
            f"{fighter.fully_qualified_name} - {lst.name}"
        ),
        content=content,
    )
