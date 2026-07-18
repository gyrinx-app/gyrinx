"""Campaign sub-asset edit form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_sub_asset_edit.html")
def campaign_sub_asset_edit(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    asset = context["asset"]
    sub_asset = context["sub_asset"]
    sub_asset_type_def = context["sub_asset_type_def"]
    form_obj = context["form"]
    request = context["request"]

    asset_edit_url = reverse("core:campaign-asset-edit", args=[campaign.id, asset.id])

    body = form(
        action=reverse(
            "core:campaign-sub-asset-edit",
            args=[campaign.id, asset.id, sub_asset.id],
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name"]),
        [FormField(field) for field in form_obj if field.name.startswith("prop_")],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=asset_edit_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=asset_edit_url, text="Back to Asset"),
        PageShell(
            h1(class_="h3")["Edit ", sub_asset_type_def.get("label", "")],
            h2(class_="h5 text-secondary")[asset.name, " · ", campaign.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Edit {sub_asset.name} - {asset.name}",
        content=content,
    )
