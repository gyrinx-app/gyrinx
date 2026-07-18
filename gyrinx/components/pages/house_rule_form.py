"""Add / edit house-rule form page component (pack house rules)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    em,
    form,
    h1,
    i,
    p,
    span,
    strong,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _view_entries(view: Any) -> Any:
    """Read ``view.entries`` the way the template does (dict key or attribute)."""
    if not view:
        return None
    if isinstance(view, dict):
        return view.get("entries")
    return getattr(view, "entries", None)


def _pack_mod_view_line(view: Any) -> Node:
    """Port of ``core/pack/includes/pack_mod_view_line.html``."""
    if not _view_entries(view):
        return None
    html = view["html"] if isinstance(view, dict) else getattr(view, "html", "")
    return span(class_="text-secondary")[html]


def _weapon_profile_table(target: Any, trait_view: Any, request: Any) -> Node:
    """The weapon-profile target preview table (``target_type == "weapon-profile"``)."""
    statline = list(target.statline())
    has_trait = bool(_view_entries(trait_view))

    header_context = {"first_col": target.equipment.name} if target.name else {}
    header = render_to_string(
        "core/includes/weapon_stat_headers.html", header_context, request=request
    )

    return table(class_="table table-sm table-borderless mb-0 border-bottom")[
        raw(header),
        tbody(class_="table-group-divider")[
            tr(class_="align-top")[
                td(rowspan="2" if has_trait else "1")[
                    strong[target.name if target.name else target.equipment.name],
                ],
                tuple(
                    td(class_=["text-center", stat.classes])[stat.value]
                    for stat in statline
                ),
            ],
            tr[td(colspan="8")[_pack_mod_view_line(trait_view)]] if has_trait else None,
        ],
    ]


def _fighter_table(target: Any, rule_view: Any) -> Node:
    """The fighter/vehicle target preview table (non ``weapon-profile``)."""
    statline = list(target.statline())
    has_rule = bool(_view_entries(rule_view))

    return table(class_="table table-sm table-borderless mb-0 border-bottom")[
        thead(class_="table-group-divider")[
            tr[
                th(scope="col"),
                tuple(
                    th(
                        class_=[
                            "text-center",
                            "border-start" if stat["first_of_group"] else None,
                        ],
                        scope="col",
                    )[stat["name"]]
                    for stat in statline
                ),
            ]
        ],
        tbody(class_="table-group-divider")[
            tr(class_="align-top")[
                td(rowspan="2" if has_rule else "1")[
                    strong[target.type],
                    span(class_="text-secondary")["· ", target.house.name]
                    if target.house
                    else None,
                ],
                tuple(
                    td(
                        class_=[
                            "text-center",
                            "border-start" if stat["first_of_group"] else None,
                        ]
                    )[stat["value"]]
                    for stat in statline
                ),
            ],
            tr[td(colspan=len(statline))[_pack_mod_view_line(rule_view)]]
            if has_rule
            else None,
        ],
    ]


@register_page("core/pack/house_rule_form.html")
def house_rule_form(context: dict[str, Any]) -> Page:
    request = context["request"]
    pack = context["pack"]
    form_obj = context["form"]
    target = context["target"]
    target_type = context["target_type"]
    trait_view = context.get("trait_view")
    rule_view = context.get("rule_view")
    kind_picker = context["kind_picker"]
    is_new = context["is_new"]
    back_url = context["back_url"]

    if target_type == "weapon-profile":
        preview = _weapon_profile_table(target, trait_view, request)
    else:
        preview = _fighter_table(target, rule_view)

    picker_links = []
    for entry in kind_picker:
        picker_links.append(
            a(
                href=entry["url"],
                class_=[
                    "btn btn-sm",
                    "btn-primary" if entry["is_current"] else "btn-outline-secondary",
                ],
            )({"aria-current": "page"} if entry["is_current"] else {})[entry["label"]]
        )

    kind_group = div[
        div(class_="form-label mb-1")["What to modify"],
        div(class_="btn-group", role="group", aria_label="Modification kind")[
            tuple(picker_links)
        ],
    ]

    body = form(method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj)),
        div(class_="mt-2 d-flex gap-2 align-items-center")[
            button(type="submit", class_="btn btn-success")[
                i(class_="bi-check-lg me-1"),
                " Add house rule " if is_new else " Save ",
            ],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")[
                i(class_="bi-megaphone"),
                " Add " if is_new else " Edit ",
                "house rule",
            ],
            p(class_="text-secondary mb-0")[
                "Modify the target below for any List subscribed to ",
                em[pack.name],
                ".",
            ],
            preview,
            kind_group,
            body,
            kind=FORM_SHELL,
        ),
    ]

    title = f"{'Add' if is_new else 'Edit'} house rule - {pack.name}"
    return Page(title=title, content=content)
