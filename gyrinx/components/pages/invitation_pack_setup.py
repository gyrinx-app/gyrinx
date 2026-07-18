"""Invitation content-pack setup page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import lower, striptags, truncatewords
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, input_, label, p, span, strong

NARROW_SHELL = "col-12 col-xl-6 px-0 vstack gap-3"


@register_page("core/list/invitation_pack_setup.html")
def invitation_pack_setup(context: dict[str, Any]) -> Page:
    lst = context["list"]
    campaign = context["campaign"]
    suggested_packs = context["suggested_packs"]
    request = context["request"]

    def pack_row(pack: Any) -> Node:
        return label(
            class_="border rounded p-2 d-flex align-items-start gap-2",
            data_name=lower(pack.name),
        )[
            input_(
                type="checkbox",
                name="pack_ids",
                value=pack.id,
                class_="form-check-input mt-1",
                checked=True,
                disabled=pack.is_required,
            ),
            input_(type="hidden", name="pack_ids", value=pack.id)
            if pack.is_required
            else None,
            div(class_="flex-grow-1")[
                div(class_="fw-medium small")[
                    pack.name,
                    span(class_="badge text-bg-warning ms-1")["Required"]
                    if pack.is_required
                    else None,
                ],
                div(class_="text-muted small")["by ", pack.owner],
                div(class_="text-muted small mt-1")[
                    truncatewords(striptags(pack.summary), 20)
                ]
                if pack.summary
                else None,
            ],
        ]

    if suggested_packs:
        pack_nodes: Node = [pack_row(pack) for pack in suggested_packs]
    else:
        pack_nodes = p(class_="text-muted small mb-0")[
            "No additional Content Packs to add."
        ]

    body = form(
        method="post",
        action=reverse("core:invitation-pack-setup", args=[lst.id, campaign.id]),
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        div(class_="vstack gap-2")[pack_nodes],
        div(class_="d-flex gap-2")[
            button(type="submit", class_="btn btn-primary")["Add selected"],
            a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")["Skip"],
        ],
    ]

    content = PageShell(
        h1(class_="h3")["Content Packs"],
        p(class_="text-muted small")[
            campaign.name,
            " uses the following Content Packs. Select the ones you'd like to add to ",
            strong[lst.name],
            ". Packs marked ",
            span(class_="badge text-bg-warning")["Required"],
            " must be added to join this Campaign.",
        ],
        body,
        kind=NARROW_SHELL,
    )
    return Page(title=f"Content Packs - {campaign.name}", content=content)
