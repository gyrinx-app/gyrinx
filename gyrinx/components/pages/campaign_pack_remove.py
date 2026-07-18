"""Campaign pack remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p, strong
from ._shared import back_link


@register_page("core/campaign/campaign_pack_remove.html")
def campaign_pack_remove(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    pack = context["pack"]
    request = context["request"]

    packs_url = reverse("core:campaign-packs", args=[campaign.id])

    content: Node = fragment[
        back_link(context, url=packs_url, text="Back to Packs"),
        div(class_="col-12 col-xl-6 px-0")[
            h1(class_="h3 mb-3")["Remove Content Pack"],
            p[
                "Are you sure you want to remove ",
                strong[pack.name],
                " from ",
                campaign.name,
                "?",
            ],
            p(class_="text-secondary fs-7")[
                "Gangs already in the Campaign will not be affected, but new Gangs "
                "will not be able to join if they use this pack."
            ],
            form(method="post", class_="d-flex gap-2")[
                CsrfInput(request),
                button(type="submit", class_="btn btn-danger btn-sm")["Remove"],
                a(href=packs_url, class_="btn btn-secondary btn-sm")["Cancel"],
            ],
        ],
    ]
    return Page(
        title=f"Remove Pack - {campaign.name}",
        content=content,
    )
