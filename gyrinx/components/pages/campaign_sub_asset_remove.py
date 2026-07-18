"""Campaign sub-asset remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_sub_asset_remove.html")
def campaign_sub_asset_remove(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    asset = context["asset"]
    sub_asset = context["sub_asset"]
    sub_asset_type_def = context["sub_asset_type_def"]
    request = context["request"]

    label = sub_asset_type_def.get("label", "")

    back_url = reverse("core:campaign-asset-edit", args=[campaign.id, asset.id])

    body = form(
        action=reverse(
            "core:campaign-sub-asset-remove",
            args=[campaign.id, asset.id, sub_asset.id],
        ),
        method="post",
    )[
        CsrfInput(request),
        Alert(
            strong["Are you sure?"],
            p(class_="mb-0")[
                f"This will permanently remove the {label.lower()} ",
                strong[sub_asset.name],
                " from ",
                asset.name,
                ".",
            ],
            variant="warning",
            class_="mb-0",
        ),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")[
                i(class_="bi-trash"), f" Remove {label}"
            ],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text="Back to Asset"),
        PageShell(
            h1(class_="h3")[f"Remove {sub_asset.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove {sub_asset.name} - {asset.name}",
        content=content,
    )
