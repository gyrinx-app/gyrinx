"""Campaign resource-modify form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, h6, input_, p, script, span
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"

_PREVIEW_JS = """
        document.addEventListener('DOMContentLoaded', function() {
            const modificationInput = document.getElementById('id_modification');
            const previewCard = document.getElementById('preview-card');
            const newAmountSpan = document.getElementById('new-amount');
            const currentAmount = %s;

            function updatePreview() {
                const modification = parseInt(modificationInput.value) || 0;
                const newAmount = currentAmount + modification;

                if (modification !== 0) {
                    previewCard.classList.remove('d-none');
                    newAmountSpan.textContent = newAmount;

                    if (newAmount < 0) {
                        newAmountSpan.className = 'badge text-bg-danger fs-5';
                    } else {
                        newAmountSpan.className = 'badge text-bg-success fs-5';
                    }
                } else {
                    previewCard.classList.add('d-none');
                }
            }

            modificationInput.addEventListener('input', updatePreview);
            modificationInput.addEventListener('change', updatePreview);
        });
"""


@register_page("core/campaign/campaign_resource_modify.html")
def campaign_resource_modify(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    resource = context["resource"]
    request = context["request"]

    return_url = context.get("return_url", "")
    return_url_field: Node = (
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None
    )

    current_amount_card = div(class_="card")[
        div(class_="card-body")[
            h6(class_="card-subtitle mb-2 text-secondary")["Current Amount"],
            p(class_="mb-0")[
                span(class_="badge text-bg-primary fs-5")[resource.amount],
            ],
        ]
    ]

    preview_card = div(class_="card bg-body-secondary d-none", id="preview-card")[
        div(class_="card-body")[
            h6(class_="card-subtitle mb-2 text-secondary")["New Amount"],
            p(class_="mb-0")[
                span(class_="badge text-bg-success fs-5", id="new-amount")[
                    resource.amount
                ],
            ],
        ]
    ]

    body = form(
        action=reverse(
            "core:campaign-resource-modify", args=[campaign.id, resource.id]
        ),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        return_url_field,
        FormField(form_obj["modification"]),
        preview_card,
        Alert(
            "This action will be recorded in the campaign action log.",
            variant="info",
            class_="mb-0",
        ),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Update Resource"],
            cancel_link(context),
        ],
    ]

    content: Node = fragment[
        back_link(context, text="Back"),
        PageShell(
            h1(class_="h3")[f"Modify {resource.resource_type.name}"],
            h2(class_="h5 text-secondary")[resource.list.name],
            current_amount_card,
            body,
            kind=FORM_SHELL,
        ),
        script[raw(_PREVIEW_JS % resource.amount)],
    ]
    return Page(title=f"Modify {resource.resource_type.name}", content=content)
