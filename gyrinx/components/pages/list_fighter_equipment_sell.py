"""Sell-equipment three-step flow page component.

Port of ``core/list_fighter_equipment_sell.html`` — a stash-fighter equipment
sale with dice-roll pricing. The single template drives three steps
(``selection`` / ``confirm`` / ``summary``) chosen by the ``step`` context key;
this component reproduces each branch, plus the selection-only ``extra_script``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from django.template.defaulttags import querystring as _querystring
from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h3,
    i,
    input_,
    label,
    script,
    span,
    strong,
    table,
    tbody,
    td,
    tfoot,
    th,
    thead,
    tr,
)
from ._shared import back_link


def _header(context: dict[str, Any], lst: Any, request: Any) -> Node:
    """Bridge the un-ported ``list_common_header.html`` include (with-overrides)."""
    return raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {**context, "list": lst, "link_list": "true"},
            request=request,
        )
    )


def _step_progress(request: Any, step: int, total_steps: int, title: str) -> Node:
    """Bridge the un-ported ``step_progress.html`` include."""
    return raw(
        render_to_string(
            "core/includes/step_progress.html",
            {"step": step, "total_steps": total_steps, "title": title},
            request=request,
        )
    )


def _back_to_list(context: dict[str, Any], lst: Any, request: Any) -> Node:
    """Bridge the un-ported ``back_to_list.html`` include (renders back.html with
    ``text=list.name`` / ``url=core:list``)."""
    return raw(
        render_to_string(
            "core/includes/back_to_list.html",
            {**context, "url_name": "core:list", "back_text": "Back to list"},
            request=request,
        )
    )


def _upgrades_note_from_objects(upgrades: Any) -> Node:
    """Selection-step upgrades: model objects (``upgrade.name`` attribute)."""
    if not upgrades:
        return None
    return div(class_="text-secondary fs-7")[
        tuple(fragment["+ ", upgrade.name] for upgrade in upgrades)
    ]


def _upgrades_note_from_dicts(upgrades: Any) -> Node:
    """Confirm-step upgrades: dicts (``upgrade["name"]``)."""
    if not upgrades:
        return None
    return div(class_="text-secondary fs-7")[
        tuple(fragment["+ ", upgrade["name"]] for upgrade in upgrades)
    ]


def _radio_extra(field: Any) -> Node:
    """The pb-2 block shown under a roll_manual / price_manual radio option."""
    return div(class_="pb-2")[
        raw(str(field)),
        div(class_="form-text")[field.help_text] if field.help_text else None,
        div(class_="invalid-feedback d-block")[field.errors[0]]
        if field.errors
        else None,
    ]


def _price_method_options(form_obj: Any) -> Node:
    blocks: list[Node] = []
    for radio in form_obj["price_method"]:
        value = radio.data["value"]
        if value == "roll_manual":
            extra: Node = _radio_extra(form_obj["roll_manual_d6"])
        elif value == "price_manual":
            extra = _radio_extra(form_obj["price_manual_value"])
        else:
            extra = None
        blocks.append(
            fragment[
                div(class_="form-check")[
                    raw(str(radio.tag())),
                    label(class_="form-check-label", for_=radio.id_for_label)[
                        radio.choice_label
                    ],
                ],
                extra,
            ]
        )
    return div(class_="vstack gap-2")[tuple(blocks)]


def _selection(
    context: dict[str, Any],
    lst: Any,
    fighter: Any,
    request: Any,
    gear_edit_url: str,
    weapons_edit_url: str,
) -> Node:
    assign = context.get("assign")
    forms = context["forms"]

    if assign is not None and assign.is_weapon:
        back = back_link(context, url=weapons_edit_url, text="Back to Weapons")
    else:
        back = back_link(context, url=gear_edit_url, text="Back to Gear")

    rows = [
        tr[
            td[
                item["name"],
                _upgrades_note_from_objects(item.get("upgrades")),
            ],
            td[item["total_cost"], "¢"],
            td[_price_method_options(form_obj)],
        ]
        for item, form_obj in forms
    ]

    return fragment[
        div(class_="vstack gap-3")[
            div(class_="vstack gap-1")[
                back,
                _step_progress(request, 1, 3, "Sell Equipment"),
                h3(class_="h5 mb-0")["Select Sale Price Method"],
            ]
        ],
        form(method="post", class_="vstack gap-3")[
            CsrfInput(request),
            input_(type="hidden", name="step", value="selection"),
            div(class_="table-responsive")[
                table(class_="table")[
                    thead[
                        tr[
                            th["Item"],
                            th["Cost"],
                            th["Sale Price Method"],
                        ]
                    ],
                    tbody[tuple(rows)],
                ]
            ],
            div(class_="hstack gap-3")[
                a(
                    href=reverse(
                        "core:list-fighter-gear-edit", args=[lst.id, fighter.id]
                    ),
                    class_="icon-link",
                )[i(class_="bi-chevron-left"), " Back"],
                button(type="submit", class_="btn btn-primary")[
                    "Continue ", i(class_="bi-arrow-right")
                ],
            ],
        ],
    ]


def _confirm_method_cell(item: dict[str, Any]) -> Node:
    method = item["price_method"]
    if method == "roll_auto":
        return fragment["Cost minus D6×10 (auto)"]
    if method == "roll_manual":
        return fragment[
            "Cost minus D6×10 (tabletop result: ", item["roll_manual_d6"], ")"
        ]
    return fragment["Manual: ", item["price_manual_value"], "¢"]


def _confirm_price_cell(item: dict[str, Any]) -> Node:
    method = item["price_method"]
    if method == "roll_auto":
        return span(class_="text-secondary")["To be rolled..."]
    if method == "roll_manual":
        return fragment[item["total_cost"], "¢ − ", item["roll_manual_d6"], "×10¢"]
    return fragment[item["price_manual_value"], "¢"]


def _confirm(context: dict[str, Any], lst: Any, fighter: Any, request: Any) -> Node:
    assign = context["assign"]
    sell_data = context["sell_data"]

    rows = [
        tr[
            td[
                item["name"],
                _upgrades_note_from_dicts(item.get("upgrades")),
            ],
            td[item["base_cost"], "¢"],
            td[_confirm_method_cell(item)],
            td[_confirm_price_cell(item)],
        ]
        for item in sell_data
    ]

    back_href = reverse(
        "core:list-fighter-equipment-sell", args=[lst.id, fighter.id, assign.id]
    ) + _querystring(SimpleNamespace(request=request), sell_assign=assign.id, step=None)

    return fragment[
        div(class_="vstack gap-3")[
            div(class_="vstack gap-1")[
                _back_to_list(context, lst, request),
                _step_progress(request, 2, 3, "Confirm Equipment Sale"),
                h3(class_="h5 mb-0")["Sale Summary"],
            ]
        ],
        div(class_="table-responsive")[
            table(class_="table")[
                thead[
                    tr[
                        th["Item"],
                        th["Cost"],
                        th["Sale Method"],
                        th["Sale Price"],
                    ]
                ],
                tbody[tuple(rows)],
            ]
        ],
        div(class_="alert alert-info alert-icon mb-0", role="alert")[
            i(class_="bi-info-circle"),
            div[
                'Items using "Roll for me" will have dice rolled automatically when '
                "you confirm. Items using tabletop results will use the entered D6 "
                "value. Sale price is the item's base cost minus the dice roll × 10 "
                "credits (minimum 5¢)."
            ],
        ],
        form(method="post", class_="vstack gap-3")[
            CsrfInput(request),
            input_(type="hidden", name="step", value="confirm"),
            div(class_="hstack gap-3")[
                a(href=back_href, class_="icon-link")[
                    i(class_="bi-chevron-left"), " Back"
                ],
                button(type="submit", class_="btn btn-danger")[
                    i(class_="bi-check-lg"), " Confirm Sale"
                ],
            ],
        ],
    ]


def _summary(context: dict[str, Any], lst: Any, fighter: Any, request: Any) -> Node:
    sale_results = context["sale_results"]
    dice_rolls = sale_results.get("dice_rolls")
    sale_details = sale_results.get("sale_details") or []
    total_credits = sale_results.get("total_credits")

    dice_block: Node = None
    if dice_rolls:
        dice_block = div(class_="border rounded p-2 hstack gap-3")[
            strong["Dice Rolls:"],
            tuple(i(class_=f"bi-dice-{roll} fs-4") for roll in dice_rolls),
        ]

    detail_rows = [
        tr[
            td[detail["name"]],
            td[detail["total_cost"], "¢"],
            td[
                fragment[
                    i(class_=f"bi-dice-{detail['dice_roll']}"), " ", detail["dice_roll"]
                ]
                if detail["dice_roll"]
                else "Manual"
            ],
            td[detail["sale_price"], "¢"],
        ]
        for detail in sale_details
    ]

    return fragment[
        div(class_="vstack gap-3")[
            div(class_="vstack gap-1")[
                _back_to_list(context, lst, request),
                _step_progress(request, 3, 3, "Sale Complete"),
                h3(class_="h5 mb-0")["Sale Results"],
            ]
        ],
        dice_block,
        div(class_="table-responsive")[
            table(class_="table")[
                thead[
                    tr[
                        th["Item"],
                        th["Cost"],
                        th["Dice Roll"],
                        th["Sale Price"],
                    ]
                ],
                tbody[tuple(detail_rows)],
                tfoot[
                    tr[
                        th(colspan="3")[strong["Total"]],
                        th[total_credits, "¢"],
                    ]
                ],
            ]
        ],
        div(class_="alert alert-success alert-icon", role="alert")[
            i(class_="bi-check-lg"),
            div[total_credits, "¢ has been added to your gang's credits."],
        ],
        div(class_="hstack gap-3")[_back_to_list(context, lst, request)],
    ]


_SYNC_BLOCK = """(function () {{
    const priceMethodRadios = document.getElementsByName('{html_name}');
    const d6Select = document.getElementById('{d6_id}');
    const manualInput = document.getElementById('{manual_id}');

    // Sync the enabled/disabled state of the respective inputs
    function syncEnabledState() {{
        const checked = Array.from(priceMethodRadios).find((r) => r.checked);
        const value = checked ? checked.value : null;

        if (d6Select) {{
            d6Select.disabled = value !== 'roll_manual';
        }}

        if (manualInput) {{
            manualInput.disabled = value !== 'price_manual';
        }}
    }}

    // Add event listeners to all price method radios
    priceMethodRadios.forEach(function (r) {{ r.addEventListener('change', syncEnabledState); }});

    // Initial sync on page load
    syncEnabledState();
}}());
"""


def _extra_script(context: dict[str, Any]) -> Node:
    blocks = []
    for _item, form_obj in context["forms"]:
        blocks.append(
            _SYNC_BLOCK.format(
                html_name=form_obj["price_method"].html_name,
                d6_id=form_obj["roll_manual_d6"].id_for_label,
                manual_id=form_obj["price_manual_value"].id_for_label,
            )
        )
    js = (
        "document.addEventListener('DOMContentLoaded', function () {\n"
        + "".join(blocks)
        + "});"
    )
    return script[raw(js)]


@register_page("core/list_fighter_equipment_sell.html")
def sell_equipment(context: dict[str, Any]) -> Page:
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]
    step = context["step"]

    gear_edit_url = reverse("core:list-fighter-gear-edit", args=[lst.id, fighter.id])
    weapons_edit_url = reverse(
        "core:list-fighter-weapons-edit", args=[lst.id, fighter.id]
    )

    if step == "selection":
        inner: Node = _selection(
            context, lst, fighter, request, gear_edit_url, weapons_edit_url
        )
    elif step == "confirm":
        inner = _confirm(context, lst, fighter, request)
    elif step == "summary":
        inner = _summary(context, lst, fighter, request)
    else:
        inner = None

    content: Node = fragment[
        _header(context, lst, request),
        div(class_="col-12 col-md-8 col-lg-6 vstack gap-4")[inner],
    ]

    extra_script = _extra_script(context) if step == "selection" else None

    return Page(
        title=f"Sell Equipment - {fighter.fully_qualified_name} - {lst.name}",
        content=content,
        extra_script=extra_script,
    )
