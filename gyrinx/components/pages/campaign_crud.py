"""Campaign create/edit form page components."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from .. import bridge
from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/campaign/campaign_new.html")
def campaign_new(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    request = context["request"]
    body = form(
        action=reverse("core:campaigns-new"), method="post", class_="vstack gap-3"
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Create"],
            a(href=bridge.safe_referer(request, "/campaigns/"), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]
    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context),
        PageShell(h1(class_="h3")["Create a new Campaign"], body, kind=FORM_SHELL),
    ]
    return Page(title="New Campaign", content=content)


@register_page("core/campaign/campaign_edit.html")
def campaign_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = form_obj.instance
    request = context["request"]
    body = form(
        action=reverse("core:campaign-edit", args=[campaign.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=reverse("core:campaign", args=[campaign.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]
    content = fragment[
        raw(str(form_obj.media)),
        back_link(context, text=campaign.name),
        PageShell(h1(class_="h3")["Edit Campaign"], body, kind=FORM_SHELL),
    ]
    return Page(title=str(campaign.name), content=content)
