"""Pack add-weapon mode-select page component (single vs multi profile)."""

from __future__ import annotations

from typing import Any

from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import a, div, h1, i, p, strong, table, tbody, td, th, thead, tr
from ._shared import back_link

# Stat header columns (port of core/includes/weapon_stat_headers.html with a
# falsy ``show_al`` — the AL column is omitted here).
_STAT_HEADERS = [
    ("text-center", "S"),
    ("text-center", "L"),
    ("text-center border-start", "S"),
    ("text-center", "L"),
    ("text-center border-start", "Str"),
    ("text-center", "Ap"),
    ("text-center", "D"),
    ("text-center", "Am"),
]

# CSS classes for the eight placeholder stat cells in each example row.
_STAT_CELL_CLASSES = [
    "text-center",
    "text-center",
    "text-center border-start",
    "text-center",
    "text-center border-start",
    "text-center",
    "text-center",
    "text-center",
]


def _weapon_stat_headers(first_col: str = "") -> Node:
    return thead(class_="table-group-divider")[
        tr[
            th(scope="col")[first_col],
            tuple(th(class_=cls, scope="col")[label] for cls, label in _STAT_HEADERS),
        ]
    ]


def _stat_cells() -> Node:
    return tuple(td(class_=cls)["-"] for cls in _STAT_CELL_CLASSES)


@register_page("core/pack/pack_weapon_mode_select.html")
def pack_weapon_mode_select(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    back_url = context["back_url"]
    add_weapon_url = context["add_weapon_url"]

    single_card = div(class_="col-12 col-md-6 col-lg-4")[
        div(class_="border rounded p-3 vstack gap-2 h-100")[
            strong["Single profile"],
            p(class_="text-secondary mb-0 fs-7")[
                "One standard statline with no profile name."
            ],
            div(class_="table-responsive")[
                table(class_="table table-sm table-borderless fs-7 mb-0")[
                    _weapon_stat_headers(),
                    tbody(class_="table-group-divider")[
                        tr[
                            td(class_="text-start")[strong["Example Weapon"]],
                            _stat_cells(),
                        ]
                    ],
                ]
            ],
            a(
                href=f"{add_weapon_url}?profile_mode=single",
                class_="btn btn-primary mt-auto",
            )["Single profile ", i(class_="bi-arrow-right")],
        ]
    ]

    multi_card = div(class_="col-12 col-md-6 col-lg-4")[
        div(class_="border rounded p-3 vstack gap-2 h-100")[
            strong["Multiple profiles"],
            p(class_="text-secondary mb-0 fs-7")[
                "Two or more named profiles (e.g. ranged and melee)."
            ],
            div(class_="table-responsive")[
                table(class_="table table-sm table-borderless fs-7 mb-0")[
                    _weapon_stat_headers("Example Weapon"),
                    tbody(class_="table-group-divider")[
                        tr[
                            td(class_="text-secondary fst-italic")["Profile 1"],
                            _stat_cells(),
                        ],
                        tr[
                            td(class_="text-secondary fst-italic")["Profile 2"],
                            _stat_cells(),
                        ],
                    ],
                ]
            ],
            a(
                href=f"{add_weapon_url}?profile_mode=multi",
                class_="btn btn-primary mt-auto",
            )["Multiple profiles ", i(class_="bi-arrow-right")],
        ]
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        div(class_="col-12 px-0 vstack gap-3")[
            h1(class_="h3")[i(class_="bi-crosshair"), " Add weapon"],
            p(class_="mb-0")[
                "Does this weapon come with multiple profiles or ammo by default?"
            ],
            p(class_="text-secondary")[
                "You can add further free or costed profiles or special ammo later."
            ],
            div(class_="row g-3")[single_card, multi_card],
        ],
    ]

    return Page(title=f"Add weapon to {pack.name}", content=content)
