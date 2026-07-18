"""Campaign asset transfer form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .. import bridge
from ..design import Alert, CsrfInput, FormField, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, h6, i, input_, p
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_asset_transfer.html")
def campaign_asset_transfer(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    asset = context["asset"]
    request = context["request"]

    return_url = context.get("return_url", "")
    return_url_field: Node = (
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None
    )

    if asset.holder:
        holder_node: Node = p(class_="mb-0")[bridge.list_with_theme(asset.holder)]
    else:
        holder_node = p(class_="mb-0 text-secondary")[
            i(class_="bi-dash-circle"), " Unowned"
        ]

    holder_card = div(class_="card")[
        div(class_="card-body")[
            h6(class_="card-subtitle mb-2 text-secondary")["Current Holder"],
            holder_node,
        ]
    ]

    body = form(
        action=reverse("core:campaign-asset-transfer", args=[campaign.id, asset.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        return_url_field,
        FormField(form_obj["new_holder"]),
        Alert(
            "This action will be recorded in the campaign action log.",
            variant="info",
            class_="mb-0",
        ),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Transfer Asset"],
            cancel_link(context),
        ],
    ]

    content: Node = fragment[
        back_link(context, text="Back"),
        PageShell(
            h1(class_="h3")[f"Transfer {asset.asset_type.name_singular}"],
            h2(class_="h5 text-secondary")[asset.name],
            holder_card,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Transfer {asset.name}", content=content)
