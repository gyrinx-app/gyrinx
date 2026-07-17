"""Campaign 'remove gang' confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .. import bridge
from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, hr, i, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_remove_list.html")
def campaign_remove_list(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    lst = context["list"]
    campaign_url = reverse("core:campaign", args=[campaign.id])

    campaign_mode_note: Node = None
    if lst.status == lst.CAMPAIGN_MODE:
        campaign_mode_note = fragment[
            hr,
            p(class_="mb-0")[
                "This gang is in campaign mode and will be ",
                strong["archived"],
                " when removed. Assets will be unassigned.",
            ],
        ]

    body = form(
        action=reverse("core:campaign-remove-list", args=[campaign.id, lst.id]),
        method="post",
    )[
        CsrfInput(context["request"]),
        Alert(
            fragment[
                strong["Are you sure?"],
                p(class_="mb-0")[
                    "This will remove ",
                    strong[bridge.list_with_theme(lst)],
                    " from the campaign.",
                ],
                campaign_mode_note,
            ],
            variant="warning",
            class_="mb-0",
        ),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")[
                i(class_="bi-trash"), " Remove from Campaign"
            ],
            a(href=campaign_url, class_="btn btn-link")["Cancel"],
        ],
    ]
    content = fragment[
        back_link(context, url=campaign_url, text="Back to Campaign"),
        PageShell(
            h1(class_="h3")[f"Remove {lst.name} from {campaign.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Remove {lst.name} from Campaign", content=content)
