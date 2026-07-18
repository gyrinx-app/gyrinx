"""Campaign attribute-value create form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_attribute_value_new.html")
def campaign_attribute_value_new(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    attribute_type = context["attribute_type"]
    request = context["request"]

    body = form(
        action=reverse(
            "core:campaign-attribute-value-new",
            args=[campaign.id, attribute_type.id],
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
        FormField(form_obj["colour"]),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Create value"],
            a(
                href=reverse("core:campaign-attributes", args=[campaign.id]),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(
            context,
            url=reverse("core:campaign-attributes", args=[campaign.id]),
            text="Back to Attributes",
        ),
        PageShell(
            h1(class_="h3")[f"Add value for {attribute_type.name}"],
            h2(class_="h5 text-secondary")[campaign.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Add value for {attribute_type.name} - {campaign.name}",
        content=content,
    )
