"""List archive / unarchive confirmation page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, input_, li, p, strong, ul
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _explainer(heading: str, items: list[str]) -> Node:
    return div(class_="border rounded p-3 bg-body-secondary")[
        p(class_="mb-2")[strong[heading]],
        ul(class_="mb-0")[tuple(li[item] for item in items)],
    ]


def _plural(active_campaigns: Any) -> str:
    return "" if len(active_campaigns) == 1 else "s"


def _archive_campaign_warning(active_campaigns: Any) -> Node:
    plural = _plural(active_campaigns)
    return div(class_="border border-warning rounded p-3 bg-warning bg-opacity-10")[
        p(class_="mb-2")[strong(class_="text-warning")["⚠️ Warning: Active Campaign"]],
        p(class_="mb-2")[
            f"This gang is currently participating in the following active campaign{plural}:"
        ],
        ul(class_="mb-2")[tuple(li[campaign.name] for campaign in active_campaigns)],
        p(class_="mb-0")[
            f"The gang will remain visible in the campaign{plural}, but an action log "
            "entry will be added noting that it has been archived."
        ],
    ]


def _unarchive_campaign_note(active_campaigns: Any) -> Node:
    plural = _plural(active_campaigns)
    return div(class_="border border-info rounded p-3 bg-info bg-opacity-10")[
        p(class_="mb-0")[
            strong["Note:"],
            f" An action log entry will be added to the campaign{plural} noting that "
            "the gang has been unarchived.",
        ]
    ]


@register_page("core/list_archive.html")
def list_archive(context: dict[str, Any]) -> Page:
    lst = context["list"]
    is_in_active_campaign = context["is_in_active_campaign"]
    active_campaigns = context["active_campaigns"]
    archived = lst.archived
    verb = "Unarchive" if archived else "Archive"

    if not archived:
        question = "Are you sure you want to archive this gang/list?"
        explainer = _explainer(
            "What happens when you archive:",
            [
                "The list will be hidden from your main lists page",
                "You won't be able to edit the list or its fighters",
                "You can unarchive it",
            ],
        )
        campaign_note = (
            _archive_campaign_warning(active_campaigns)
            if is_in_active_campaign
            else None
        )
        hidden: Node = input_(type="hidden", name="archive", value="1")
        submit = button(type="submit", class_="btn btn-danger")["Archive"]
    else:
        question = "Are you sure you want to unarchive this gang/list?"
        explainer = _explainer(
            "What happens when you unarchive:",
            [
                "The list will be visible on your main lists page again",
                "You'll be able to edit the list and its fighters",
                "All functionality will be restored",
            ],
        )
        campaign_note = (
            _unarchive_campaign_note(active_campaigns)
            if is_in_active_campaign
            else None
        )
        hidden = None
        submit = button(type="submit", class_="btn btn-primary")["Unarchive"]

    body = form(action=reverse("core:list-archive", args=[lst.id]), method="post")[
        CsrfInput(context["request"]),
        div(class_="mt-3")[
            hidden,
            submit,
            cancel_link(context),
        ],
    ]

    content = fragment[
        back_link(context),
        PageShell(
            h1(class_="h3")[f"{verb} {lst.name}"],
            p[question],
            explainer,
            campaign_note,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"{verb} {lst.name}", content=content)
