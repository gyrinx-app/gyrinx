"""Campaign sub-asset create form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_sub_asset_new.html")
def campaign_sub_asset_new(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    asset = context["asset"]
    sub_asset_type_key = context["sub_asset_type_key"]
    sub_asset_type_def = context["sub_asset_type_def"]
    form_obj = context["form"]
    request = context["request"]

    label = sub_asset_type_def.get("label", "")
    description = sub_asset_type_def.get("description")

    edit_url = reverse("core:campaign-asset-edit", args=[campaign.id, asset.id])

    prop_fields = [FormField(field) for field in form_obj if field.name[:5] == "prop_"]

    body = form(
        action=reverse(
            "core:campaign-sub-asset-new",
            args=[campaign.id, asset.id, sub_asset_type_key],
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name"]),
        prop_fields,
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")[f"Add {label}"],
            a(href=edit_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=edit_url, text="Back to Asset"),
        PageShell(
            h1(class_="h3")[f"Add {label}"],
            h2(class_="h5 text-secondary")[f"{asset.name} · {campaign.name}"],
            p(class_="text-secondary")[description] if description else None,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Add {label} - {asset.name}", content=content)
