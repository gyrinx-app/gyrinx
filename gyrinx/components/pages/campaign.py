"""Campaign lifecycle page components (start / end / reopen / archive)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import Alert, CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, em, h1, h3, h4, i, li, p, strong, ul
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _campaign_url(campaign: Any) -> str:
    return reverse("core:campaign", args=[campaign.id])


@register_page("core/campaign/campaign_end.html")
def campaign_end(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    content = fragment[
        back_link(context, url=_campaign_url(campaign), text=campaign.name),
        PageShell(
            h1(class_="h3")[f"End Campaign: {campaign.name}"],
            _end_form(context, campaign),
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"End Campaign - {campaign.name}", content=content)


def _end_form(context: dict[str, Any], campaign: Any) -> Node:
    from ..tags import form

    return form(action=reverse("core:campaign-end", args=[campaign.id]), method="post")[
        CsrfInput(context["request"]),
        p["Are you sure you want to end this campaign?"],
        Alert(
            fragment[
                "Once ended, the campaign will move from ",
                strong["In Progress"],
                " to ",
                strong["Post-Campaign"],
                " status. However, you will be able to reopen it later if needed.",
            ],
            variant="warning",
            class_="mb-0",
        ),
        p["After ending the campaign, you will still be able to:"],
        ul[
            li["View all campaign information and history"],
            li["View the action log"],
            li["Access all gangs that participated"],
        ],
        p["However, you will ", strong["not"], " be able to:"],
        ul[
            li["Add new gangs to the campaign"],
            li["Log new actions"],
        ],
        p(class_="text-secondary")[
            i(class_="bi-info-circle"),
            " ",
            strong["Note:"],
            " If you need to continue the campaign later, you can reopen it from the campaign page.",
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-danger")["End Campaign"],
            a(href=_campaign_url(campaign), class_="btn btn-link")["Cancel"],
        ],
    ]


@register_page("core/campaign/campaign_reopen.html")
def campaign_reopen(context: dict[str, Any]) -> Page:
    from ..tags import form

    campaign = context["campaign"]
    body = form(
        action=reverse("core:campaign-reopen", args=[campaign.id]), method="post"
    )[
        CsrfInput(context["request"]),
        p["Are you sure you want to reopen this campaign?"],
        Alert(
            fragment[
                "The campaign will return from ",
                strong["Post-Campaign"],
                " to ",
                strong["In Progress"],
                " status.",
            ],
            variant="info",
            class_="mb-0",
        ),
        p["After reopening the campaign, you will be able to:"],
        ul[
            li["Log new actions"],
            li["Modify campaign assets and resources"],
            li["Continue where you left off"],
        ],
        p(class_="text-secondary")[
            i(class_="bi-exclamation-circle"),
            " ",
            strong["Note:"],
            " The existing gangs will remain in the campaign. No new clones will be created.",
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")["Reopen Campaign"],
            a(href=_campaign_url(campaign), class_="btn btn-link")["Cancel"],
        ],
    ]
    content = fragment[
        back_link(context, url=_campaign_url(campaign), text=campaign.name),
        PageShell(
            h1(class_="h3")[f"Reopen Campaign: {campaign.name}"], body, kind=FORM_SHELL
        ),
    ]
    return Page(title=f"Reopen Campaign - {campaign.name}", content=content)


@register_page("core/campaign/campaign_start.html")
def campaign_start(context: dict[str, Any]) -> Page:
    from ..tags import form

    campaign = context["campaign"]
    lists = list(context.get("lists", []))

    def _row(lst: Any) -> Node:
        credit_badge = None
        if campaign.budget > 0:
            credits_to_add = max(campaign.budget - lst.wealth_current, 0)
            credit_badge = div(class_="badge text-bg-secondary")[f"{credits_to_add}¢"]
        return div(class_="d-flex justify-content-between align-items-center")[
            h4(class_="fs-6 mb-0")[lst.name],
            div[i(class_="bi-person"), " ", lst.owner.username],
            credit_badge,
        ]

    allocation = (
        [_row(lst) for lst in lists] if lists else [div[em["No gangs added yet"]]]
    )
    body = form(
        action=reverse("core:campaign-start", args=[campaign.id]), method="post"
    )[
        CsrfInput(context["request"]),
        p["Are you sure you want to start this campaign?"],
        Alert(
            fragment[
                "This action cannot be undone. Once started, the campaign will move from ",
                strong["Pre-Campaign"],
                " to ",
                strong["In Progress"],
                " status.",
            ],
            variant="warning",
            class_="mb-0",
        ),
        h3(class_="h5")["Gang credit allocation"],
        div(class_="vstack gap-2")[tuple(allocation)],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Start Campaign"],
            a(href=_campaign_url(campaign), class_="btn btn-link")["Cancel"],
        ],
    ]
    content = fragment[
        back_link(context, url=_campaign_url(campaign), text=campaign.name),
        PageShell(
            h1(class_="h3")[f"Start Campaign: {campaign.name}"], body, kind=FORM_SHELL
        ),
    ]
    return Page(title=f"Start Campaign - {campaign.name}", content=content)


@register_page("core/campaign/campaign_archive.html")
def campaign_archive(context: dict[str, Any]) -> Page:
    from ..tags import form

    campaign = context["campaign"]
    archived = campaign.archived
    verb = "Unarchive" if archived else "Archive"

    if archived:
        explainer = _archive_explainer(
            "What happens when you unarchive:",
            [
                "The campaign will be visible on the main campaigns page again",
                "All functionality will be restored",
            ],
        )
        question = "Are you sure you want to unarchive this campaign?"
        submit = button(type="submit", class_="btn btn-primary")["Unarchive"]
        hidden = None
    else:
        explainer = _archive_explainer(
            "What happens when you archive:",
            [
                "The campaign will be hidden from the main campaigns page",
                "You'll still be able to view the campaign details",
                "Campaign participants can still access it directly",
                "You can unarchive it at any time",
            ],
        )
        question = "Are you sure you want to archive this campaign?"
        submit = button(type="submit", class_="btn btn-danger")["Archive"]
        hidden = _archive_hidden()

    body = form(
        action=reverse("core:campaign-archive", args=[campaign.id]), method="post"
    )[
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
            h1(class_="h3")[f"{verb} {campaign.name}"],
            p[question],
            explainer,
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"{verb} {campaign.name}", content=content)


def _archive_explainer(heading: str, items: list[str]) -> Node:
    return div(class_="border rounded p-3 bg-body-secondary")[
        p(class_="mb-2")[strong[heading]],
        ul(class_="mb-0")[tuple(li[item] for item in items)],
    ]


def _archive_hidden() -> Node:
    from ..tags import input_

    return input_(type="hidden", name="archive", value="1")
