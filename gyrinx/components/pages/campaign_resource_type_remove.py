"""Campaign resource-type remove confirmation page component."""

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


@register_page("core/campaign/campaign_resource_type_remove.html")
def campaign_resource_type_remove(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    resource_type = context["resource_type"]
    resources_count = context["resources_count"]
    request = context["request"]

    campaign_resources_url = reverse("core:campaign-resources", args=[campaign.id])

    alert_body: list[Node] = [
        strong["Are you sure?"],
        p(class_="mb-0")[
            "This will permanently remove the resource type ",
            strong[resource_type.name],
            " from the campaign.",
        ],
    ]
    if resources_count > 0:
        suffix = "" if resources_count == 1 else "s"
        alert_body += [
            hr,
            p(class_="mb-0")[
                "This will also delete all ",
                strong[f"{resources_count} gang resource{suffix}"],
                " of this type.",
            ],
        ]

    body = form(
        action=reverse(
            "core:campaign-resource-type-remove",
            args=[campaign.id, resource_type.id],
        ),
        method="post",
    )[
        CsrfInput(request),
        Alert(*alert_body, variant="warning", class_="mb-0"),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")[
                i(class_="bi-trash"), " Remove Resource Type"
            ],
            a(href=campaign_resources_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(
            context,
            url=campaign_resources_url,
            text="Back to Campaign Resources",
        ),
        PageShell(
            h1(class_="h3")[f"Remove {resource_type.name} from {campaign.name}"],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Remove {resource_type.name} - {campaign.name}",
        content=content,
    )
