"""Campaign asset remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, hr, i, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_asset_remove.html")
def campaign_asset_remove(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    asset = context["asset"]
    request = context["request"]

    campaign_assets_url = reverse("core:campaign-assets", args=[campaign.id])

    alert_body: list[Node] = [
        strong["Are you sure?"],
        p(class_="mb-0")[
            "This will permanently remove the ",
            asset.asset_type.name_singular.lower(),
            " ",
            strong[asset.name],
            " from the campaign.",
        ],
    ]
    if asset.holder:
        alert_body += [
            hr,
            p(class_="mb-0")[
                "This asset is currently held by ",
                strong[asset.holder.name],
                ".",
            ],
        ]

    body = form(
        action=reverse(
            "core:campaign-asset-remove",
            args=[campaign.id, asset.id],
        ),
        method="post",
    )[
        CsrfInput(request),
        Alert(*alert_body, variant="warning", class_="mb-0"),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")[
                i(class_="bi-trash"), " Remove Asset"
            ],
            a(href=campaign_assets_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(
            context,
            url=campaign_assets_url,
            text="Back to Campaign Assets",
        ),
        PageShell(
            h1(class_="h3")[f"Remove {asset.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove {asset.name} - {campaign.name}",
        content=content,
    )
