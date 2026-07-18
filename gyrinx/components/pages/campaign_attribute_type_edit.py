"""Campaign attribute-type edit form page component."""

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


@register_page("core/campaign/campaign_attribute_type_edit.html")
def campaign_attribute_type_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    attribute_type = context["attribute_type"]
    request = context["request"]

    # Port of core/campaign/includes/attribute_type_form_fields.html
    single_select = form_obj["is_single_select"]
    form_fields: Node = fragment[
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
        div(class_="form-check")[
            single_select,
            single_select.label_tag(),
            small(class_="form-text text-secondary d-block")[single_select.help_text]
            if single_select.help_text
            else None,
            div(class_="invalid-feedback d-block")[single_select.errors]
            if single_select.errors
            else None,
        ],
    ]

    body = form(
        action=reverse(
            "core:campaign-attribute-type-edit",
            args=[campaign.id, attribute_type.id],
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        form_fields,
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
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
            h1(class_="h3")[f"Edit {attribute_type.name}"],
            h2(class_="h5 text-secondary")[campaign.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Edit {attribute_type.name} - {campaign.name}",
        content=content,
    )
