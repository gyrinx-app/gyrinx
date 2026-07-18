"""Campaign asset create form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_asset_new.html")
def campaign_asset_new(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    asset_type = context["asset_type"]
    request = context["request"]

    fields: list[Node] = [
        CsrfInput(request),
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
    ]
    if "holder" in form_obj.fields:
        fields.append(FormField(form_obj["holder"]))
    fields.append(
        raw(
            render_to_string(
                "core/campaign/includes/asset_properties_fields.html",
                {**context},
                request=request,
            )
        )
    )
    fields.append(
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success", name="save")[
                f"Create {asset_type.name_singular}"
            ],
            "or",
            button(
                type="submit",
                class_="btn btn-secondary",
                name="save_and_add_another",
            )["Create and add another"],
            a(
                href=reverse("core:campaign-assets", args=[campaign.id]),
                class_="btn btn-link",
            )["Cancel"],
        ]
    )

    body = form(
        action=reverse("core:campaign-asset-new", args=[campaign.id, asset_type.id]),
        method="post",
        class_="vstack gap-3",
    )[fields]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(
            context,
            url=reverse("core:campaign-assets", args=[campaign.id]),
            text="Back to Assets",
        ),
        PageShell(
            h1(class_="h3")[f"Add {asset_type.name_singular}"],
            h2(class_="h5 text-secondary")[campaign.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Add {asset_type.name_singular} - {campaign.name}", content=content
    )
