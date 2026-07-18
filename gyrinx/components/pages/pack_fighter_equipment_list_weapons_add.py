"""Pack fighter "configure equipment list — add weapons" bulk picker page."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
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
    span,
    table,
    tbody,
    td,
    th,
    thead,
    tr,
)
from ._shared import back_link

_STATLINE_PARTIAL = "core/includes/list_fighter_weapon_profile_statline.html"

# The two "cost" number inputs in the legacy template carry a duplicate
# ``class`` attribute (``class="…" class="w-auto"``). Emit the exact same bytes
# so the port matches both the browser rendering and the golden comparison.
_DUP_CLASS = (
    'class="form-control form-control-sm text-center p-0 w-em-5" class="w-auto"'
)


def _statline(profile: Any, request: Any) -> Node:
    return raw(
        render_to_string(_STATLINE_PARTIAL, {"profile": profile}, request=request)
    )


def _dup_cost_input(name: str) -> Node:
    """A number input with the template's duplicate ``class`` attribute intact."""
    return raw(f'<input type="number" name="{name}" value="0" min="0" {_DUP_CLASS}>')


def _weapon_tbody(weapon: dict[str, Any], request: Any) -> Node:
    eq = weapon["equipment"]
    eq_id = str(eq.id)
    rows: list[Node] = []

    for index, profile in enumerate(weapon["standard_profiles"]):
        first = index == 0
        rowspan = "2" if len(profile.traitline_cached) > 0 else "1"

        if first and profile.name != "":
            rows.append(
                tr[
                    td[
                        input_(
                            type="checkbox",
                            class_="form-check-input weapon-check",
                            name="equipment",
                            value=eq_id,
                            id=f"weapon-{eq_id}",
                            data_weapon_parent=eq_id,
                        )
                    ],
                    td(colspan="9")[
                        label(
                            class_="form-check-label fw-medium",
                            for_=f"weapon-{eq_id}",
                        )[eq.name]
                    ],
                    td[
                        input_(
                            type="number",
                            name=f"cost_{eq_id}",
                            value="0",
                            min="0",
                            class_="form-control form-control-sm text-center p-0 w-em-5",
                        )
                    ],
                ]
            )

        if first and profile.name == "":
            lead: Node = (
                td(rowspan=rowspan)[
                    input_(
                        type="checkbox",
                        class_="form-check-input weapon-check",
                        name="equipment",
                        value=eq_id,
                        id=f"weapon-{eq_id}",
                        data_weapon_parent=eq_id,
                    )
                ],
                td(rowspan=rowspan)[
                    label(class_="form-check-label", for_=f"weapon-{eq_id}")[eq.name]
                ],
            )
        elif profile.name:
            lead = (
                td(rowspan=rowspan),
                td(rowspan=rowspan)[i(class_="bi-dash"), " ", profile.name],
            )
        else:
            lead = None

        cost_cell: Node = None
        if first and profile.name == "":
            cost_cell = td(rowspan=rowspan)[_dup_cost_input(f"cost_{eq_id}")]

        rows.append(
            tr(class_="align-top")[lead, _statline(profile, request), cost_cell]
        )

        if len(profile.traitline_cached) > 0:
            rows.append(tr[td(colspan="8")[", ".join(profile.traitline_cached)]])

    for profile in weapon["non_standard_profiles"]:
        rowspan = "2" if len(profile.traitline_cached) > 0 else "1"
        rows.append(
            tr(class_="align-top")[
                td(rowspan=rowspan),
                td(rowspan=rowspan)[
                    div(class_="form-check")[
                        input_(
                            type="checkbox",
                            class_="form-check-input profile-check",
                            name="profiles",
                            value=str(profile.id),
                            id=f"profile-{profile.id}",
                            disabled=True,
                            data_weapon_child=eq_id,
                        ),
                        label(class_="form-check-label", for_=f"profile-{profile.id}")[
                            profile.name
                        ],
                    ]
                ],
                _statline(profile, request),
                td(rowspan=rowspan)[_dup_cost_input(f"profile_cost_{profile.id}")],
            ]
        )
        if len(profile.traitline_cached) > 0:
            rows.append(tr[td(colspan="8")[", ".join(profile.traitline_cached)]])

    return tbody(class_="table-group-divider", data_weapon_name=eq.name.lower())[
        tuple(rows)
    ]


def _category_card(
    category_name: str, weapons: list[dict[str, Any]], request: Any
) -> Node:
    return div(class_="card mb-3", data_category=True)[
        div(class_="card-header p-2")[h3(class_="h5 mb-0")[category_name]],
        div(class_="card-body p-2")[
            table(class_="table table-sm table-borderless mb-0 fs-7")[
                thead(class_="table-group-divider")[
                    tr[
                        th(scope="col", class_="pe-0"),
                        th(scope="col")["Weapon"],
                        th(class_="text-center", scope="col")["S"],
                        th(class_="text-center", scope="col")["L"],
                        th(class_="text-center border-start", scope="col")["S"],
                        th(class_="text-center", scope="col")["L"],
                        th(class_="text-center border-start", scope="col")["Str"],
                        th(class_="text-center", scope="col")["Ap"],
                        th(class_="text-center", scope="col")["D"],
                        th(class_="text-center", scope="col")["Am"],
                        th(class_="text-center w-em-5", scope="col")["Cost"],
                    ]
                ],
                tuple(_weapon_tbody(weapon, request) for weapon in weapons),
            ]
        ],
    ]


_SCRIPT = """<script>
        (function () {
            var form = document.getElementById("bulk-form");
            var filterInput = document.getElementById("filter-input");
            var submitBtn = document.getElementById("submit-btn");
            var submitBtnText = document.getElementById("submit-btn-text");
            var zeroCostWarning = document.getElementById("zero-cost-warning");
            var zeroCostWarningText = document.getElementById("zero-cost-warning-text");

            function updateWarning() {
                var zeroCount = 0;
                // Check base weapons.
                var weapons = form.querySelectorAll(".weapon-check:checked");
                for (var i = 0; i < weapons.length; i++) {
                    var costInput = form.querySelector('input[name="cost_' + weapons[i].value + '"]');
                    if (costInput && (costInput.value === "" || costInput.value === "0")) zeroCount++;
                }
                // Check selected profiles.
                var profiles = form.querySelectorAll(".profile-check:checked");
                for (var j = 0; j < profiles.length; j++) {
                    var pCostInput = form.querySelector('input[name="profile_cost_' + profiles[j].value + '"]');
                    if (pCostInput && (pCostInput.value === "" || pCostInput.value === "0")) zeroCount++;
                }
                if (zeroCount > 0) {
                    zeroCostWarningText.textContent = zeroCount + " item" + (zeroCount > 1 ? "s" : "") + " at 0¢ — are you sure?";
                    zeroCostWarning.classList.remove("d-none");
                } else {
                    zeroCostWarning.classList.add("d-none");
                }
            }

            // Parent checkbox enables/disables child profile checkboxes.
            form.addEventListener("change", function (e) {
                if (e.target.classList.contains("weapon-check")) {
                    var id = e.target.dataset.weaponParent;
                    var children = form.querySelectorAll('[data-weapon-child="' + id + '"]');
                    for (var i = 0; i < children.length; i++) {
                        children[i].disabled = !e.target.checked;
                        if (!e.target.checked) children[i].checked = false;
                    }
                }
                // Update submit button count (weapons + profiles).
                var weaponCount = form.querySelectorAll(".weapon-check:checked").length;
                var profileCount = form.querySelectorAll(".profile-check:checked").length;
                var count = weaponCount + profileCount;
                submitBtn.disabled = weaponCount === 0;
                submitBtnText.textContent = count ? "Add selected (" + count + ")" : "Add selected";
                updateWarning();
            });
            form.addEventListener("input", function (e) {
                if (e.target.type === "number") updateWarning();
            });

            // Client-side filtering by weapon name.
            filterInput.addEventListener("input", function () {
                var q = this.value.toLowerCase();
                var bodies = form.querySelectorAll("[data-weapon-name]");
                for (var i = 0; i < bodies.length; i++) {
                    bodies[i].style.display = bodies[i].dataset.weaponName.indexOf(q) !== -1 ? "" : "none";
                }
                // Hide empty categories.
                var cats = form.querySelectorAll("[data-category]");
                for (var j = 0; j < cats.length; j++) {
                    var visible = cats[j].querySelectorAll("tbody[data-weapon-name]:not([style*='display: none'])");
                    cats[j].style.display = visible.length ? "" : "none";
                }
            });
        })();
    </script>"""


@register_page("core/pack/pack_fighter_equipment_list_weapons_add.html")
def pack_fighter_equipment_list_weapons_add(context: dict[str, Any]) -> Page:
    request = context["request"]
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_fighter = context["content_fighter"]
    categories = context["categories"]
    error_message = context["error_message"]

    action_url = reverse(
        "core:pack-fighter-equipment-list-weapon-add", args=(pack.id, pack_item.id)
    )

    if categories:
        cards: Node = tuple(
            _category_card(category_name, weapons, request)
            for category_name, weapons in categories.items()
        )
    else:
        cards = p["No weapons found."]

    body = form(action=action_url, method="post", id="bulk-form")[
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
        cards,
    ]

    content: Node = fragment[
        back_link(
            context,
            url=reverse("core:pack-item-equipment-list", args=(pack.id, pack_item.id)),
            text=content_fighter.type,
        ),
        div(class_="col-12 px-0 vstack gap-3")[
            h1(class_="h3")[f"Configure equipment list: {content_fighter.type}"],
            div(class_="alert alert-danger alert-icon mb-0", role="alert")[
                i(class_="bi-exclamation-triangle"),
                div[error_message],
            ]
            if error_message
            else None,
            body,
        ],
        raw(_SCRIPT),
    ]

    return Page(
        title=(f"Configure equipment list - {content_fighter.type} - {pack.name}"),
        content=content,
    )
