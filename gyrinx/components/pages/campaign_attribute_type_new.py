"""Campaign attribute-type create form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, small
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_attribute_type_new.html")
def campaign_attribute_type_new(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    request = context["request"]

    is_single_select = form_obj["is_single_select"]

    body = form(
        action=reverse("core:campaign-attribute-type-new", args=[campaign.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
        div(class_="form-check")[
            is_single_select,
            is_single_select.label_tag(),
            small(class_="form-text text-secondary d-block")[is_single_select.help_text]
            if is_single_select.help_text
            else None,
            div(class_="invalid-feedback d-block")[is_single_select.errors]
            if is_single_select.errors
            else None,
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Create Attribute Type"],
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
            h1(class_="h3")["Add Attribute Type"],
            h2(class_="h5 text-secondary")[campaign.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Add Attribute Type - {campaign.name}", content=content)
