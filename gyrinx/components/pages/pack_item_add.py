"""Pack "add content item" form page component.

Port of ``core/pack/pack_item_add.html`` — the create form shared by every
pack content type (rules, gear, weapons, fighters, weapon accessories, ...).
The single template drives several variants via context flags, so this
component reproduces the same conditional branches:

* ``slug == "weapon-accessory"`` renders the synthetic mod picker instead of
  ``{{ form }}``;
* gear/weapon show a "modifiers later" hint;
* weapons render single- or multi-profile stat inputs;
* fighters get a next-step hint + "Next" button (step 1 of a two-step flow).

The weapon-accessory / weapon-profile ``{% include %}``s are bridged through
the DjangoTemplates loader (they are not themselves ported).
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, i, input_, p, script, span
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"

# Verbatim port of the template's {% block extra_script %} — toggles the
# statline-type <select> based on the "override statline" checkbox.
_EXTRA_SCRIPT = """
        (function () {
            const checkbox = document.getElementById("id_override_statline");
            const select = document.getElementById("id_statline_type");
            if (!checkbox || !select) return;

            function toggle() {
                if (checkbox.checked) {
                    select.removeAttribute("disabled");
                } else {
                    select.setAttribute("disabled", "disabled");
                    select.value = "";
                }
            }

            checkbox.addEventListener("change", toggle);
            toggle();
        })();
    """


def _profile_stats_include(context: dict[str, Any], request: Any, **overrides: Any):
    """Bridge ``weapon_profile_stats_form.html`` with the same variables the
    legacy ``{% include %}`` receives (parent ``weapon_traits`` + overrides)."""
    ctx = {"weapon_traits": context.get("weapon_traits"), **overrides}
    return raw(
        render_to_string(
            "core/pack/includes/weapon_profile_stats_form.html", ctx, request=request
        )
    )


@register_page("core/pack/pack_item_add.html")
def pack_item_add(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    pack = context["pack"]
    label = context["label"]
    icon = context["icon"]
    slug = context["slug"]
    back_url = context["back_url"]
    request = context["request"]

    children: list[Node] = [CsrfInput(request)]

    # --- The form fields (weapon-accessory mod picker vs plain form). ---
    if slug == "weapon-accessory":
        children.append(raw(str(form_obj.non_field_errors())))
        children.extend(raw(str(field)) for field in form_obj.hidden_fields())
        children.extend(
            div[raw(str(field.as_field_group()))] for field in form_obj.standard_fields
        )
        children.append(
            raw(
                render_to_string(
                    "core/pack/includes/_accessory_mods_picker.html",
                    {"form": form_obj},
                    request=request,
                )
            )
        )
        children.append(
            raw(
                render_to_string(
                    "core/pack/includes/_mod_picker_shared.html", {}, request=request
                )
            )
        )
    else:
        children.append(raw(str(form_obj)))

    # --- Gear/weapon: "add modifiers later" hint. ---
    if slug in ("gear", "weapon"):
        children.append(
            div(class_="alert alert-secondary alert-icon", role="alert")[
                i(class_="bi-info-circle"),
                div[
                    "You can add fighter stat, rule, and skill modifiers from the "
                    f"Modifiers tab after you create this {label.lower()}."
                ],
            ]
        )

    # --- Weapon profile stat inputs (single or multi). ---
    if context.get("profile_mode") == "multi":
        children.append(input_(type="hidden", name="profile_mode", value="multi"))
        children.append(
            div[
                div(class_="bg-body-tertiary rounded px-2 py-2 mb-2")[
                    h2(class_="h5 mb-0")["Profile 1"]
                ],
                div(class_="px-2 vstack gap-3")[
                    input_(
                        type="text",
                        name="wp1_name",
                        value=context.get("wp1_name") or "",
                        class_="form-control",
                        placeholder="Name (e.g. melee)",
                        required=True,
                    ),
                    _profile_stats_include(
                        context,
                        request,
                        weapon_stats=context.get("weapon_stat_fields_1"),
                        prefix="wp1",
                        selected_trait_ids=context.get("selected_trait_ids_1"),
                    ),
                ],
            ]
        )
        children.append(
            div[
                div(class_="bg-body-tertiary rounded px-2 py-2 mb-2")[
                    h2(class_="h5 mb-0")["Profile 2"]
                ],
                div(class_="px-2 vstack gap-3")[
                    input_(
                        type="text",
                        name="wp2_name",
                        value=context.get("wp2_name") or "",
                        class_="form-control",
                        placeholder="Name (e.g. ranged)",
                        required=True,
                    ),
                    _profile_stats_include(
                        context,
                        request,
                        weapon_stats=context.get("weapon_stat_fields_2"),
                        prefix="wp2",
                        selected_trait_ids=context.get("selected_trait_ids_2"),
                    ),
                ],
            ]
        )
        children.append(
            div(class_="alert alert-info alert-icon mb-0", role="alert")[
                i(class_="bi-info-circle", aria_hidden="true"),
                div[
                    p(class_="mb-0")[
                        "You can add further profiles or special ammo later."
                    ]
                ],
            ]
        )
    elif context.get("weapon_stat_fields"):
        children.append(input_(type="hidden", name="profile_mode", value="single"))
        children.append(
            _profile_stats_include(
                context,
                request,
                weapon_stats=context.get("weapon_stat_fields"),
                selected_trait_ids=context.get("selected_trait_ids"),
            )
        )

    # --- Next-step hint (fighter flow). ---
    if context.get("next_step_hint"):
        children.append(
            div(class_="alert alert-info alert-icon mb-0 mt-3", role="alert")[
                i(class_="bi-info-circle", aria_hidden="true"),
                div[context["next_step_hint"]],
            ]
        )

    # --- Submit buttons. ---
    if context.get("next_step_button"):
        button_row: list[Node] = [
            button(type="submit", class_="btn btn-primary")[context["next_step_button"]]
        ]
    else:
        button_row = [
            button(type="submit", class_="btn btn-success")[
                i(class_="bi-check-lg me-1"), f" Add {label}"
            ],
            span["or"],
            button(
                type="submit", name="save_and_add_another", class_="btn btn-secondary"
            )["Add and create another"],
        ]
    children.append(
        div(class_="mt-2 d-flex gap-2 align-items-center")[
            tuple(button_row),
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ]
    )

    body = form(
        action=reverse("core:pack-add-item", args=(pack.id, slug)),
        method="post",
        class_="vstack gap-3",
    )[tuple(children)]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")[i(class_=icon), f" Add {label}"],
            body,
            kind=FORM_SHELL,
        ),
    ]

    return Page(
        title=f"Add {label} to {pack.name}",
        content=content,
        extra_script=script[raw(_EXTRA_SCRIPT)],
    )
