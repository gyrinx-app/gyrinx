"""Pack fighter default psyker powers list + add form page component."""

from __future__ import annotations

from itertools import groupby
from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    button,
    div,
    form,
    h1,
    h2,
    i,
    li,
    optgroup,
    option,
    p,
    section,
    select,
    span,
    ul,
)
from ._shared import back_link

SHELL = "col-12 col-xl-8 px-0 vstack gap-3"


@register_page("core/pack/pack_fighter_default_psyker_powers.html")
def pack_fighter_default_psyker_powers(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    current = list(context["current"])
    available = list(context["available"])
    request = context["request"]

    # --- Current defaults section ---
    if current:
        current_body: Node = ul(class_="list-unstyled mb-0")[
            [
                li(class_="py-1")[
                    div(class_="d-flex justify-content-between align-items-center")[
                        div[
                            span[assign.psyker_power.name],
                            span(class_="text-secondary fs-7")[
                                f"({assign.psyker_power.discipline.name})"
                            ],
                        ],
                        form(
                            action=reverse(
                                "core:pack-fighter-default-psyker-power-remove",
                                args=(pack.id, pack_item.id, assign.id),
                            ),
                            method="post",
                            class_="m-0",
                        )[
                            CsrfInput(request),
                            button(
                                type="submit",
                                class_="btn btn-link btn-sm link-danger link-underline-opacity-50 link-underline-opacity-100-hover p-0",
                            )["Remove"],
                        ],
                    ]
                ]
                for assign in current
            ]
        ]
    else:
        current_body = p(class_="text-secondary mb-0")["No default powers yet."]

    # --- Add power section ---
    if available:
        discipline_groups = [
            (disc, list(powers))
            for disc, powers in groupby(available, key=lambda power: power.discipline)
        ]
        add_body: Node = form(
            action=reverse(
                "core:pack-fighter-default-psyker-power-add",
                args=(pack.id, pack_item.id),
            ),
            method="post",
            class_="vstack gap-2",
        )[
            CsrfInput(request),
            select(name="psyker_power", class_="form-select", required=True)[
                option(value="")["Select a power…"],
                [
                    optgroup(label=disc.name)[
                        [option(value=power.id)[power.name] for power in powers]
                    ]
                    for disc, powers in discipline_groups
                ],
            ],
            div[
                button(type="submit", class_="btn btn-primary btn-sm")[
                    i(class_="bi-plus"), " Add default power"
                ]
            ],
        ]
    else:
        add_body = p(class_="text-secondary mb-0")[
            "No accessible powers. Assign a non-generic discipline to this "
            "fighter first, or create a generic discipline with at least "
            "one power."
        ]

    content: Node = fragment[
        back_link(
            context,
            url=reverse("core:pack-edit-item", args=(pack.id, pack_item.id)),
            text=content_fighter.type,
        ),
        PageShell(
            h1(class_="h3")[f"Default psyker powers: {content_fighter.type}"],
            p(class_="text-secondary")[
                "Powers added here will be assigned by default to any fighter of this "
                "type when the fighter is hired into a subscribed list."
            ],
            raw("<!-- Current default powers -->"),
            section[
                h2(class_="h5")["Current defaults"],
                current_body,
            ],
            raw("<!-- Add power -->"),
            section[
                h2(class_="h5")["Add a default power"],
                add_body,
            ],
            kind=SHELL,
        ),
    ]

    return Page(
        title=f"Default psyker powers - {content_fighter.type} - {pack.name}",
        content=content,
    )
