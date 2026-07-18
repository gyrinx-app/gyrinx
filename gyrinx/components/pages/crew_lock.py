"""Crew lock/roll confirmation page component (port of crew_lock.html)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, i, p, strong
from ._shared import back_link, cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/crew/crew_lock.html")
def crew_lock(context: dict[str, Any]) -> Page:
    crew = context["crew"]
    battle = context["battle"]
    chosen_fighters = context["chosen_fighters"]
    whole_gang = context["whole_gang"]
    request = context["request"]

    crew_url = reverse("core:crew", args=[battle.id, crew.id])

    heading = f"Roll {crew} for selection" if crew.pending_roll else f"Confirm {crew}"

    # First sentence: "Rolling"/"Confirming" freezes the crew's attendees.
    verb = "Rolling" if crew.pending_roll else "Confirming"
    p_children: list[Node] = [
        f"{verb} freezes the crew's attendees for {battle.name}. "
    ]
    if whole_gang:
        p_children.append("The whole eligible gang will attend.")
    else:
        count = len(chosen_fighters)
        suffix = "" if count == 1 else "s"
        included = f"{count} chosen fighter{suffix} will be included"
        if crew.random_spec:
            p_children += [
                f"{included}, and ",
                strong[crew.random_spec],
                " more will be drawn at random from the rest of the gang.",
            ]
        else:
            p_children.append(f"{included}.")

    box_text = "After this, the crew's recipe can no longer be changed"
    if crew.random_spec:
        box_text += ", and the random draw runs once — it can't be re-rolled"
    box_text += "."

    button_label = "Roll for selection" if crew.pending_roll else "Confirm crew"

    body = form(
        action=reverse("core:crew-lock", args=[battle.id, crew.id]),
        method="post",
    )[
        CsrfInput(request),
        p(class_="mb-0")[tuple(p_children)],
        div(class_="border rounded p-2 mt-3")[
            i(class_="bi-exclamation-triangle"),
            f" {box_text}",
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-primary")[button_label],
            cancel_link(context, url=crew_url),
        ],
    ]

    content: Node = fragment[
        back_link(context, url=crew_url, text="Back to Crew"),
        PageShell(
            h1(class_="h3")[heading],
            body,
            kind=FORM_SHELL,
        ),
    ]

    title_prefix = "Roll for selection" if crew.pending_roll else "Confirm crew"
    return Page(
        title=f"{title_prefix} - {battle.name}",
        content=content,
    )
