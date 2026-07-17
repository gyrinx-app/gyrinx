"""Campaign resource-type edit form page component."""

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


@register_page("core/campaign/campaign_resource_type_edit.html")
def campaign_resource_type_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    resource_type = context["resource_type"]
    request = context["request"]

    body = form(
        action=reverse(
            "core:campaign-resource-type-edit", args=[campaign.id, resource_type.id]
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
        FormField(form_obj["default_amount"]),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Update Resource Type"],
            a(
                href=reverse("core:campaign-resources", args=[campaign.id]),
                class_="btn btn-link",
            )["Cancel"],
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(
            context,
            url=reverse("core:campaign-resources", args=[campaign.id]),
            text="Back to Resources",
        ),
        PageShell(
            h1(class_="h3")["Edit Resource Type"],
            h2(class_="h5 text-secondary")[resource_type.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit Resource Type - {resource_type.name}", content=content)
