"""Pack fighter equipment-list accessory-add page component."""

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
    i,
    input_,
    label,
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

            form.addEventListener("change", function () {
                var count = form.querySelectorAll(".accessory-check:checked").length;
                submitBtn.disabled = count === 0;
                submitBtnText.textContent = count ? "Add selected (" + count + ")" : "Add selected";
            });

            filterInput.addEventListener("input", function () {
                var q = this.value.toLowerCase();
                var rows = form.querySelectorAll("[data-accessory-name]");
                for (var i = 0; i < rows.length; i++) {
                    rows[i].style.display = rows[i].dataset.accessoryName.indexOf(q) !== -1 ? "" : "none";
                }
            });
        })();
    """


def _accessory_row(accessory: Any) -> Node:
    return tr(data_accessory_name=accessory.name.lower())[
        td[
            input_(
                type="checkbox",
                class_="form-check-input accessory-check",
                name="accessory",
                value=accessory.id,
                id=f"accessory-{accessory.id}",
            )
        ],
        td[
            label(class_="form-check-label", for_=f"accessory-{accessory.id}")[
                accessory.name,
                span(class_="text-secondary")[f"({accessory.cost}¢)"],
            ]
        ],
        td[
            input_(
                type="number",
                name=f"cost_{accessory.id}",
                value=accessory.cost,
                min="0",
                class_="form-control form-control-sm text-center p-0 w-em-5",
            )
        ],
    ]


@register_page("core/pack/pack_fighter_equipment_list_accessory_add.html")
def pack_fighter_equipment_list_accessory_add(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    accessories = context["accessories"]
    error_message = context.get("error_message")
    request = context["request"]

    if accessories:
        rows: Node = tuple(_accessory_row(accessory) for accessory in accessories)
    else:
        rows = tr[td(colspan="3", class_="text-secondary")["No accessories available."]]

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
            "core:pack-fighter-equipment-list-accessory-add",
            args=[pack.id, pack_item.id],
        ),
        method="post",
        id="bulk-form",
    )[
        CsrfInput(request),
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
                    placeholder="Filter accessories...",
                ),
            ],
        ],
        div(class_="card")[
            div(class_="card-body p-2")[
                table(class_="table table-sm table-borderless mb-0 fs-7")[
                    thead(class_="table-group-divider")[
                        tr[
                            th(scope="col", class_="pe-0"),
                            th(scope="col")["Accessory"],
                            th(class_="text-center w-em-5", scope="col")["Cost"],
                        ]
                    ],
                    tbody(class_="table-group-divider")[rows],
                ]
            ]
        ],
    ]

    content: Node = fragment[
        back_link(
            context,
            url=reverse("core:pack-item-equipment-list", args=[pack.id, pack_item.id]),
            text=content_fighter.type,
        ),
        div(class_=SHELL)[
            h1(class_="h3")[f"Add accessories: {content_fighter.type}"],
            error_alert,
            form_node,
        ],
        script[raw(_SCRIPT)],
    ]

    return Page(
        title=(f"Configure equipment list - {content_fighter.type} - {pack.name}"),
        content=content,
    )
