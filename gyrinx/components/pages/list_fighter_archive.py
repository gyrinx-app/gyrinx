"""List fighter archive confirmation page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label, p

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


@register_page("core/list_fighter_archive.html")
def list_fighter_archive(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    fighter_cost = context.get("fighter_cost")
    request = context["request"]

    # The legacy template's {% include list_common_header.html %} is un-ported;
    # bridge it through the DjangoTemplates loader with the same ``with``
    # overrides (full parent context + overrides, matching {% include %}).
    header = render_to_string(
        "core/includes/list_common_header.html",
        {
            **context,
            "list": lst,
            "link_list": "true",
            "fighter": fighter,
            "fighter_url_name": "core:list-fighter-edit",
        },
        request=request,
    )

    content: Node = fragment[
        raw(header),
        PageShell(
            h1(class_="h3")[f"Archive: {fighter.fully_qualified_name}"],
            form(
                action=reverse("core:list-fighter-archive", args=[lst.id, fighter.id]),
                method="post",
            )[
                CsrfInput(request),
                p["Are you sure you want to archive this fighter?"],
                _refund_checkbox(lst, fighter_cost),
                div(class_="mt-3")[
                    input_(type="hidden", name="archive", value="1"),
                    button(type="submit", class_="btn btn-danger")["Archive"],
                    a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")[
                        "Cancel"
                    ],
                ],
            ],
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Archive - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
    )
