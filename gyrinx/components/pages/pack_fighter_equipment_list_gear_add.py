"""Pack fighter equipment-list gear-add page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    button,
    div,
    form,
    h1,
    h3,
    i,
    input_,
    label,
    p,
    script,
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)
from ._shared import back_link

SHELL = "col-12 col-xl-8 px-0 vstack gap-3"

_SCRIPT = """
        (function () {
            var form = document.getElementById("bulk-form");
            var filterInput = document.getElementById("filter-input");
            var submitBtn = document.getElementById("submit-btn");
            var submitBtnText = document.getElementById("submit-btn-text");
            var zeroCostWarning = document.getElementById("zero-cost-warning");
            var zeroCostWarningText = document.getElementById("zero-cost-warning-text");

            function updateWarning() {
                var checked = form.querySelectorAll(".gear-check:checked");
                var zeroCount = 0;
                for (var i = 0; i < checked.length; i++) {
                    var id = checked[i].value;
                    var costInput = form.querySelector('input[name="cost_' + id + '"]');
                    if (costInput && (costInput.value === "" || costInput.value === "0")) zeroCount++;
                }
                if (zeroCount > 0) {
                    zeroCostWarningText.textContent = zeroCount + " item" + (zeroCount > 1 ? "s" : "") + " at 0¢ — are you sure?";
                    zeroCostWarning.classList.remove("d-none");
                } else {
                    zeroCostWarning.classList.add("d-none");
                }
            }

            // Update submit button count.
            form.addEventListener("change", function () {
                var count = form.querySelectorAll(".gear-check:checked").length;
                submitBtn.disabled = count === 0;
                submitBtnText.textContent = count ? "Add selected (" + count + ")" : "Add selected";
                updateWarning();
            });
            form.addEventListener("input", function (e) {
                if (e.target.type === "number") updateWarning();
            });

            // Client-side filtering by gear name.
            filterInput.addEventListener("input", function () {
                var q = this.value.toLowerCase();
                var rows = form.querySelectorAll("[data-gear-name]");
                for (var i = 0; i < rows.length; i++) {
                    rows[i].style.display = rows[i].dataset.gearName.indexOf(q) !== -1 ? "" : "none";
                }
                // Hide empty categories.
                var cats = form.querySelectorAll("[data-category]");
                for (var j = 0; j < cats.length; j++) {
                    var visible = cats[j].querySelectorAll("tr[data-gear-name]:not([style*='display: none'])");
                    cats[j].style.display = visible.length ? "" : "none";
                }
            });
        })();
    """


def _category_card(category_name: Any, items: Any) -> Node:
    return div(class_="card g-col-12 g-col-lg-6", data_category=True)[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")[category_name]],
        div(class_="card-body p-2")[
            table(class_="table table-sm table-borderless mb-0 fs-7")[
                thead(class_="table-group-divider")[
                    tr[
                        th(scope="col", class_="pe-0"),
                        th(scope="col")["Gear"],
                        th(class_="text-center w-em-5", scope="col")["Cost"],
                    ]
                ],
                tbody(class_="table-group-divider")[
                    tuple(
                        tr(data_gear_name=item.name.lower())[
                            td[
                                input_(
                                    type="checkbox",
                                    class_="form-check-input gear-check",
                                    name="equipment",
                                    value=item.id,
                                    id=f"gear-{item.id}",
                                )
                            ],
                            td[
                                label(
                                    class_="form-check-label", for_=f"gear-{item.id}"
                                )[item.name]
                            ],
                            td[
                                input_(
                                    type="number",
                                    name=f"cost_{item.id}",
                                    value="0",
                                    min="0",
                                    class_="form-control form-control-sm text-center p-0 w-em-5",
                                )
                            ],
                        ]
                        for item in items
                    )
                ],
            ]
        ],
    ]


@register_page("core/pack/pack_fighter_equipment_list_gear_add.html")
def pack_fighter_equipment_list_gear_add(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    categories = context["categories"]
    error_message = context.get("error_message")
    request = context["request"]

    cards = [_category_card(name, items) for name, items in categories.items()]
    grid_children = (
        tuple(cards) if cards else div(class_="g-col-12")[p["No gear found."]]
    )

    error_alert = (
        div(class_="alert alert-danger alert-icon mb-0", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[error_message],
        ]
        if error_message
        else None
    )

    form_node = form(
        action=reverse(
            "core:pack-fighter-equipment-list-gear-add",
            args=[pack.id, pack_item.id],
        ),
        method="post",
        id="bulk-form",
    )[
        CsrfInput(request),
        raw("<!-- Filter + submit bar -->"),
        div(class_="d-flex flex-column gap-2 mb-3")[
            div(class_="d-flex gap-3")[
                button(
                    type="submit",
                    class_="btn btn-success flex-shrink-0",
                    id="submit-btn",
                    disabled=True,
                )[
                    i(class_="bi-plus-lg me-1"),
                    span(id="submit-btn-text")["Add selected"],
                ],
                input_(
                    type="search",
                    id="filter-input",
                    class_="form-control form-control-sm",
                    placeholder="Filter weapons...",
                ),
            ],
            div(
                id="zero-cost-warning",
                class_="bg-warning-subtle text-warning-emphasis rounded p-2 fs-7 d-none",
            )[
                i(class_="bi-exclamation-triangle"),
                span(id="zero-cost-warning-text"),
            ],
        ],
        raw("<!-- Gear by category -->"),
        div(class_="grid")[grid_children],
    ]

    content: Node = fragment[
        back_link(
            context,
            url=reverse("core:pack-item-equipment-list", args=[pack.id, pack_item.id]),
            text=content_fighter.type,
        ),
        div(class_=SHELL)[
            h1(class_="h3")[f"Configure equipment list: {content_fighter.type}"],
            error_alert,
            form_node,
        ],
        script[raw(_SCRIPT)],
    ]

    return Page(
        title=(f"Configure equipment list - {content_fighter.type} - {pack.name}"),
        content=content,
    )
