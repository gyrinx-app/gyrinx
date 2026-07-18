"""List "performance" debug page component (port of ``core/list_performance.html``).

The legacy template extends ``core/layouts/foundation.html`` directly and
overrides ``{% block base %}`` — i.e. a bare, nav/footer-free document whose body
*is* the page content. So the component returns ``Page(layout="foundation")`` and
puts the whole ``{% block base %}`` node in ``content``.

The base block is a staff-facing dump of cached list/fighter state. It reads a
lot of model accessors, and Django auto-calls callables during ``{{ }}``
resolution (``{{ list.facts.rating }}`` invokes ``list.facts()`` first). To
reproduce that byte-for-byte without hand-classifying every accessor as
field/property/method, this module resolves values through a small helper that
mirrors Django's ``Variable._resolve_lookup`` (dict → attr → index, then auto-call
non-``alters_data`` callables) and its rendering rules (a resolved ``None``
renders as the literal ``"None"``; a failed lookup renders as ``""``, the default
``string_if_invalid``).
"""

from __future__ import annotations

from typing import Any

from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import div, em, h2, li, p, small, span, table, tbody, td, th, tr, ul

# --------------------------------------------------------------------------
# Django-faithful variable resolution / filters
# --------------------------------------------------------------------------

_MISSING = object()  # stands in for a failed lookup (Django: string_if_invalid).


def _lookup(current: Any, bit: str) -> Any:
    """One resolution step, in Django's order: ``current[bit]`` → ``getattr`` →
    ``current[int(bit)]``; returns ``_MISSING`` if all fail."""
    try:
        return current[bit]
    except (TypeError, AttributeError, KeyError, ValueError, IndexError):
        pass
    try:
        return getattr(current, bit)
    except (TypeError, AttributeError):
        pass
    try:
        return current[int(bit)]
    except (IndexError, ValueError, KeyError, TypeError):
        return _MISSING


def _resolve_bit(current: Any, bit: str) -> Any:
    value = _lookup(current, bit)
    if value is _MISSING:
        return _MISSING
    if callable(value):
        if getattr(value, "do_not_call_in_templates", False):
            return value
        if getattr(value, "alters_data", False):
            return _MISSING
        try:
            return value()
        except TypeError:
            return _MISSING
    return value


def resolve(root: Any, path: str) -> Any:
    """Resolve ``{{ root.path }}`` the way Django would (auto-calling callables)."""
    current: Any = root
    for bit in path.split("."):
        current = _resolve_bit(current, bit)
        if current is _MISSING:
            return _MISSING
    return current


def render_value(value: Any) -> str:
    """Render a resolved value as Django's ``{{ }}`` does before autoescape."""
    if value is _MISSING:
        return ""
    if value is None:
        return "None"
    return str(value)


def dj(root: Any, path: str) -> str:
    """Shorthand for ``render_value(resolve(root, path))``."""
    return render_value(resolve(root, path))


def truthy(root: Any, path: str) -> bool:
    """Truthiness of ``{{ root.path }}`` (a failed lookup is falsy)."""
    value = resolve(root, path)
    return value is not _MISSING and bool(value)


def yesno(value: Any, yes: str, no: str) -> str:
    """Port of the ``yesno`` filter with two labels (``None`` maps to ``no``)."""
    if value is _MISSING:
        value = ""
    if value is None:
        return no
    return yes if value else no


def yesno_len(value: Any, yes: str, no: str) -> str:
    """``{{ value|length|yesno:"yes,no" }}`` — non-empty → ``yes``."""
    if value is _MISSING or value is None:
        length = 0
    else:
        length = len(value)
    return yesno(length, yes, no)


def _iter(root: Any, path: str) -> list:
    value = resolve(root, path)
    if value is _MISSING or value is None:
        return []
    return list(value)


# --------------------------------------------------------------------------
# Page
# --------------------------------------------------------------------------


def _fighter_rows(fighter: Any) -> Node:
    """The two ``<tr>`` rows the template renders per active fighter."""
    if truthy(fighter, "is_child_fighter"):
        linked: Node = fragment[
            dj(fighter, "term_proximal_demonstrative"),
            " is linked to ",
            dj(fighter, "parent_list_fighter.name"),
        ]
    else:
        linked = span(class_="text-secondary fst-italic")["No linked fighter"]

    if truthy(fighter, "legacy_content_fighter_cached"):
        legacy: Node = dj(fighter, "legacy_content_fighter_cached.house.name")
    else:
        legacy = span(class_="text-secondary fst-italic")["No legacy"]

    stats = _iter(fighter, "statline")
    statline_text = " | ".join(
        f"{render_value(resolve(s, 'name'))}: {render_value(resolve(s, 'value'))}"
        for s in stats
    )

    rule_items = _iter(fighter, "ruleline")
    if rule_items:
        rules_text = "Rules: " + " , ".join(
            render_value(resolve(r, "value")) for r in rule_items
        )
    else:
        rules_text = "Rules: None"

    skill_items = _iter(fighter, "skilline_cached")
    if skill_items:
        skills_text = "Skills: " + " , ".join(render_value(s) for s in skill_items)
    else:
        skills_text = "Skills: None"

    return fragment[
        tr[
            td(rowspan="2")[dj(fighter, "name")],
            td[
                dj(fighter, "get_category_label"),
                " / ",
                dj(fighter, "content_fighter_cached.cat"),
                " / ",
                dj(fighter, "category_override"),
            ],
            td[dj(fighter, "base_cost_display")],
            td[dj(fighter, "advancement_cost_display")],
            td[dj(fighter, "get_injury_state_display")],
            td[
                yesno(resolve(fighter, "is_captured"), "Captured", "Not Captured"),
                " / ",
                yesno(
                    resolve(fighter, "is_sold_to_guilders"),
                    "Sold to Guilders",
                    "Not Sold",
                ),
            ],
            td[linked],
            td[
                yesno(
                    resolve(fighter, "has_overridden_cost"),
                    "Cost overridden",
                    "No override",
                )
            ],
        ],
        tr[
            td[
                legacy,
                " / ",
                yesno(resolve(fighter, "can_take_legacy"), "Yes", "No"),
            ],
            td(colspan="2")[small[statline_text]],
            td[small[rules_text]],
            td[small[skills_text]],
        ],
    ]


@register_page("core/list_performance.html")
def list_performance(context: dict[str, Any]) -> Page:
    lst = context["list"]
    user = context.get("user")

    # List Attributes (active) — one <li> per assignment, or an empty note.
    active_attrs = _iter(lst, "active_attributes_cached")
    if active_attrs:
        attribute_items: Node = [
            li[
                dj(a, "attribute_value.name"),
                ": ",
                dj(a, "attribute_value.attribute"),
            ]
            for a in active_attrs
        ]
    else:
        attribute_items = li["No attributes assigned."]

    # Available Attributes — a table, or a "none" note.
    all_attrs = _iter(lst, "all_attributes")
    if all_attrs:
        available_attributes: Node = table(class_="table table-sm mb-0 fs-7")[
            tbody[
                [
                    tr[
                        td[dj(attr, "name")],
                        td[
                            " , ".join(
                                render_value(x) for x in resolve(attr, "assignments")
                            )
                            if truthy(attr, "assignments")
                            else span(class_="text-secondary")["Not set"]
                        ],
                    ]
                    for attr in all_attrs
                ]
            ]
        ]
    else:
        available_attributes = p(class_="text-secondary fs-7 mb-0")[
            "No attributes available."
        ]

    # List Fighters — two rows per active fighter, or an empty note.
    fighters = _iter(lst, "active_fighters")
    if fighters:
        fighter_body: Node = [_fighter_rows(f) for f in fighters]
    else:
        fighter_body = tr[td["No fighters in this list."]]

    content: Node = fragment[
        div(class_="border rounded m-2 mb-3 p-2 mb-last-0 text-secondary")[
            "Stuff that is not here yet, but could later be optimised:",
            ul[
                li[
                    em["Cost"],
                    " — this is the big one. Currently around 14 queries per fighter, "
                    "which is a lot.",
                ],
                li[
                    em["Refs"],
                    " — using the ref tag. These are already fairly optimised and cached.",
                ],
            ],
        ],
        h2["List Details"],
        ul[
            li[dj(lst, "name")],
            li["Archived? ", yesno(resolve(lst, "archived"), "Yes", "No")],
            li[dj(lst, "owner_cached")],
            li[dj(lst, "owner_cached.username")],
            li[dj(lst, "content_house_name")],
            li[dj(lst, "is_campaign_mode")],
            li["Public" if truthy(lst, "public") else "Unlisted"],
            li["Owner" if resolve(lst, "owner_cached") == user else None],
            li[dj(lst, "original_list")],
            li[dj(lst, "campaign")],
            li[
                "Clones? ",
                yesno_len(resolve(lst, "active_campaign_clones"), "Yes", "No"),
            ],
        ],
        h2["Facts"],
        ul[
            li["R: ", dj(lst, "facts.rating")],
            li["S: ", dj(lst, "facts.stash")],
            li["Cr: ", dj(lst, "facts.credits")],
            li["W: ", dj(lst, "facts.wealth")],
        ],
        h2["List Attributes"],
        ul[attribute_items],
        h2["Available Attributes"],
        available_attributes,
        h2["List Fighters"],
        table(class_="table table-sm mb-0 fs-7")[
            tbody[
                tr[
                    th(rowspan="2")["Name"],
                    th["Category Label / CF Cat / Override"],
                    th["Base Cost"],
                    th["Advancement Cost"],
                    th["Injury State"],
                    th["Captured / Sold to Guilders"],
                    th["Linked Fighter"],
                    th["Cost Override"],
                ],
                tr[
                    th["Legacy House / Takes Legacy"],
                    th(colspan="2")["Statline"],
                    th["Rules"],
                    th["Skills"],
                    th[""],
                    th[""],
                    th[""],
                ],
                fighter_body,
            ]
        ],
    ]

    return Page(
        layout="foundation",
        title=f"{dj(lst, 'name')} | {dj(lst, 'owner_cached')}",
        content=content,
    )
