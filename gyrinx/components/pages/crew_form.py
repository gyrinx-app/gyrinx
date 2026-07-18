"""Crew create/edit recipe form page component (battle crews, #1346)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, em, form, h1, i, input_, label, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/crew/crew_form.html")
def crew_form(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    battle = context["battle"]
    gang = context["gang"]
    crew = context.get("crew")
    is_create = bool(context.get("is_create"))
    request = context["request"]

    if crew is not None:
        cancel_url = reverse("core:crew", args=[battle.id, crew.id])
    else:
        cancel_url = reverse("core:battle", args=[battle.id])

    name_field = form_obj["name"]
    dice_field = form_obj["random_dice"]
    number_field = form_obj["random_number"]
    chosen_field = form_obj["chosen_fighters"]

    if form_obj.has_eligible_fighters:
        chosen_body: Node = fragment[
            raw(str(chosen_field)),
            div(class_="form-text")[chosen_field.help_text],
        ]
    else:
        chosen_body = p(class_="text-secondary fs-7 mb-0")[
            i(class_="bi-info-circle"),
            " This gang has no active fighters available for a crew yet. Add fighters to "
            "the gang first, or set up a random draw and lock a whole-gang crew later.",
        ]

    body = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        input_(type="hidden", name="list", value=str(gang.id)) if is_create else None,
        raw(str(form_obj.non_field_errors())),
        div[
            label(class_="form-label", for_=name_field.id_for_label)[name_field.label],
            raw(str(name_field)),
            div(class_="form-text")[name_field.help_text]
            if name_field.help_text
            else None,
            raw(str(name_field.errors)),
        ],
        div[
            label(class_="form-label")["Random draw"],
            div(class_="d-flex flex-wrap gap-2 align-items-end")[
                div[
                    label(
                        class_="form-text mb-1 d-block", for_=dice_field.id_for_label
                    )[dice_field.label],
                    raw(str(dice_field)),
                ],
                div(class_="pb-2")["+"],
                div[
                    label(
                        class_="form-text mb-1 d-block", for_=number_field.id_for_label
                    )[number_field.label],
                    raw(str(number_field)),
                ],
            ],
            div(class_="form-text")[
                "Extra fighters drawn at random when the crew is locked — you don't choose "
                "which ones. Pick a die (D3/D6), add a number, or use either alone (e.g. D3, "
                "D3+4, or 6); leave both blank for no random draw. If a scenario instead rolls "
                "for how many you may ",
                em["hand-pick"],
                " (e.g. Custom Selection (D3+7)), roll it yourself and tick that many below.",
            ],
            raw(str(dice_field.errors)),
            raw(str(number_field.errors)),
        ],
        div[
            label(class_="form-label")[chosen_field.label],
            chosen_body,
            raw(str(chosen_field.errors)),
        ],
        div(class_="hstack gap-3 align-items-center")[
            button(type="submit", class_="btn btn-success")["Save crew"],
            a(href=cancel_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    heading = (
        h1(class_="h3")["Add a crew for ", gang.name]
        if is_create
        else h1(class_="h3")["Edit crew"]
    )
    intro = p(class_="text-secondary")[
        "Choose this crew's fighters for ",
        battle.name,
        ". Tick the ones you're hand-picking; the dice draw ",
        em["extra"],
        " fighters at random when the crew is locked at battle start.",
    ]

    content: Node = fragment[
        back_link(context, url=cancel_url, text="Back"),
        PageShell(heading, intro, body, kind=FORM_SHELL),
    ]
    title = f"{'Add crew' if is_create else 'Edit crew'} - {battle.name}"
    return Page(title=title, content=content)
