"""Campaign log-action form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, input_
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_log_action.html")
def campaign_log_action(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    request = context["request"]
    return_url = context.get("return_url", "")

    body = form(
        action=reverse("core:campaign-action-new", args=[campaign.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None,
        FormField(form_obj["list"]),
        FormField(form_obj["battle"]),
        FormField(form_obj["description"]),
        FormField(form_obj["dice_count"]),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Log Action"],
            cancel_link(context),
        ],
    ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context, text="Back"),
        PageShell(
            h1(class_="h3")["Log Action"],
            h2(class_="h5 text-secondary")[campaign.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Log Action - {campaign.name}", content=content)
