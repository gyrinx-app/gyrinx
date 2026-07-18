"""Campaign attribute-value edit form page component."""

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


@register_page("core/campaign/campaign_attribute_value_edit.html")
def campaign_attribute_value_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    attribute_value = context["attribute_value"]
    request = context["request"]

    back_url = reverse("core:campaign-attributes", args=[campaign.id])

    body = form(
        action=reverse(
            "core:campaign-attribute-value-edit",
            args=[campaign.id, attribute_value.id],
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
        FormField(form_obj["colour"]),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context, url=back_url, text="Back to Attributes"),
        PageShell(
            h1(class_="h3")[f"Edit {attribute_value.name}"],
            h2(class_="h5 text-secondary")[
                attribute_value.attribute_type.name, " · ", campaign.name
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit {attribute_value.name} - {campaign.name}", content=content)
