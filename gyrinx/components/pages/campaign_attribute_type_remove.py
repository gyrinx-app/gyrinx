"""Campaign attribute-type remove confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, hr, i, p, strong
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_attribute_type_remove.html")
def campaign_attribute_type_remove(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    attribute_type = context["attribute_type"]
    values_count = context["values_count"]
    request = context["request"]

    back_url = reverse("core:campaign-attributes", args=[campaign.id])

    alert_children: list[Node] = [
        strong["Are you sure?"],
        p(class_="mb-0")[
            "This will permanently remove the attribute type ",
            strong[attribute_type.name],
            " from the Campaign.",
        ],
    ]
    if values_count > 0:
        plural = "" if values_count == 1 else "s"
        alert_children += [
            hr,
            p(class_="mb-0")[
                "This will also delete all ",
                strong[f"{values_count} value{plural}"],
                " and their Gang assignments.",
            ],
        ]

    body = form(
        action=reverse(
            "core:campaign-attribute-type-remove",
            args=[campaign.id, attribute_type.id],
        ),
        method="post",
    )[
        CsrfInput(request),
        Alert(*alert_children, variant="warning", class_="mb-0"),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")[
                i(class_="bi-trash"), " Remove Attribute type"
            ],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text="Back to Attributes"),
        PageShell(
            h1(class_="h3")[f"Remove {attribute_type.name} from {campaign.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove {attribute_type.name} - {campaign.name}", content=content
    )
