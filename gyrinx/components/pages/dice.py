"""Dice roller page component (port of ``core/dice.html``).

The page is fully described by its query string: the dice mode, how many dice in
how many groups, and (optionally) a roll ``seed``. Every control is an ``<a>``
that reloads the page with new query state, built by the same query-string
template tags the legacy template uses — imported and called directly here so
the generated hrefs are byte-identical.
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.templatetags.static import static

from gyrinx.core.templatetags.custom_tags import qt, qt_append, qt_nth, qt_rm_nth

from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i, script, span


def _die_face(value: Any) -> Node:
    """One die in the tray: a rolled face, or an unrolled placeholder."""
    if value:
        return i(class_=f"bi-dice-{value}", aria_label=f"Dice showing {value}")
    return span(class_="dice-placeholder", role="img", aria_label="Not yet rolled")


def _group_card(request: Any, nth: int, group: dict[str, Any]) -> Node:
    """One dice group: the +/-/1 controls, remove button, and the dice tray."""
    dice_n = group["dice_n"]
    at_min = dice_n <= 1
    return div(class_="col-12 col-md-6 col-xl-3 dice-group")[
        div(class_="border rounded p-3 vstack gap-3 h-100")[
            div(class_="hstack gap-2")[
                div(class_="btn-group flex-grow-1")[
                    a(
                        rel="nofollow",
                        class_=[
                            "js-sub-die btn btn-outline-secondary",
                            {"disabled": at_min},
                        ],
                        href="?"
                        + qt_nth(request, nth=nth, drop="seed", d=max(dice_n - 1, 1)),
                        aria_label="Remove one die",
                        aria_disabled="true" if at_min else None,
                    )[i(class_="bi-dash-lg")],
                    a(
                        rel="nofollow",
                        class_=[
                            "js-set-one btn btn-outline-secondary",
                            {"disabled": at_min},
                        ],
                        href="?" + qt_nth(request, nth=nth, drop="seed", d="1"),
                        aria_disabled="true" if at_min else None,
                    )["1"],
                    a(
                        rel="nofollow",
                        class_="js-add-die btn btn-outline-primary",
                        href="?" + qt_nth(request, nth=nth, drop="seed", d=dice_n + 1),
                        aria_label="Add one die",
                    )[i(class_="bi-plus-lg")],
                ],
                a(
                    rel="nofollow",
                    class_="js-remove-group link-danger text-decoration-none lh-1",
                    href="?" + qt_rm_nth(request, nth=nth, drop="seed", d=1, fp=1, i=1),
                    aria_label="Remove dice group",
                )[i(class_="bi-x-lg")],
            ],
            div(class_="dice-tray hstack gap-2 flex-wrap")[
                tuple(_die_face(value) for value in group["dice"])
            ],
        ]
    ]


@register_page("core/dice.html")
def dice(context: dict[str, Any]) -> Page:
    request = context["request"]
    mode = context["mode"]
    next_seed = context["next_seed"]
    groups = context["groups"]

    # Un-ported breadcrumb include; bridge it through the Django loader.
    home = raw(render_to_string("core/includes/home.html", {}, request=request))

    controls = div(class_="d-grid gap-2 d-sm-flex align-items-center")[
        a(
            rel="nofollow",
            class_=[
                "js-roll-d6 btn btn-lg",
                "btn-primary" if mode == "d6" else "btn-outline-primary",
            ],
            href="?" + qt(request, m="d6", seed=next_seed),
        )[i(class_="bi-dice-6"), " Roll D6"],
        a(
            rel="nofollow",
            class_=[
                "js-roll-d3 btn btn-lg",
                "btn-primary" if mode == "d3" else "btn-outline-primary",
            ],
            href="?" + qt(request, m="d3", seed=next_seed),
        )[i(class_="bi-dice-3"), " Roll D3"],
        a(
            rel="nofollow",
            class_="js-reset btn btn-lg btn-outline-secondary ms-sm-auto",
            href="?m=d6&d=1",
        )["Reset"],
    ]

    groups_row = div(class_="row g-3 js-dice-groups")[
        tuple(_group_card(request, nth, group) for nth, group in enumerate(groups))
    ]

    add_group = div(class_="hstack justify-content-center")[
        a(
            class_="js-add-group btn btn-outline-primary",
            href="?" + qt_append(request, drop="seed", d=1, fp=0, i=0),
        )[i(class_="bi-plus-lg"), " New dice group"]
    ]

    content: Node = fragment[
        home,
        div(class_="col-lg-12 px-0 vstack gap-4 js-dice", data_mode=mode)[
            h1(class_="visually-hidden")["Roll some dice"],
            controls,
            groups_row,
            add_group,
        ],
    ]

    return Page(
        title="Dice",
        content=content,
        extra_script=script(type="module", src=static("core/js/dice.js")),
    )
