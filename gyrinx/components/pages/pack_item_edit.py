"""Pack item edit form page component (port of core/pack/pack_item_edit.html)."""

from __future__ import annotations

from typing import Any

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
    h1,
    i,
    input_,
    label,
    p,
    span,
    table,
    tbody,
    td,
    tr,
)
from ._shared import back_link


def _stats_block(stat_values: Any) -> Node:
    """The fighter Stats input grid (``{% if stat_values %}``)."""
    return div[
        label(class_="form-label")["Stats"],
        div(class_="d-flex flex-wrap gap-2")[
            tuple(
                div(class_="text-center stat-input-cell")[
                    label(class_="form-label fs-7 mb-1")[stat["short_name"]],
                    input_(
                        type="text",
                        name=f"stat_{stat['field_name']}",
                        value=stat["value"],
                        class_="form-control form-control-sm text-center",
                        placeholder=stat["placeholder"],
                        maxlength="10",
                    ),
                ]
                for stat in stat_values
            )
        ],
        div(class_="form-text")['Set each stat value, or leave as "-" for unset.'],
    ]


def _weapon_stat_include(context: dict[str, Any], request: Any) -> Node:
    """``{% include weapon_profile_stats_form.html with weapon_stats=... %}``."""
    if not context.get("weapon_stat_values"):
        return None
    return raw(
        render_to_string(
            "core/pack/includes/weapon_profile_stats_form.html",
            {**context, "weapon_stats": context["weapon_stat_values"]},
            request=request,
        )
    )


def _named_profiles_table(
    context: dict[str, Any], pack: Any, pack_item: Any, request: Any
) -> Node:
    named_profiles = context.get("named_profiles") or []
    can_archive = context.get("can_archive_profiles")
    rows: list[Node] = []
    for profile in named_profiles:
        traitline = profile.traitline()
        cost_display = profile.cost_display()
        rows.append(
            tr(class_="align-top")[
                td(rowspan="2" if len(traitline) > 0 else "1")[
                    i(class_="bi-dash"),
                    " ",
                    profile.name,
                    " ",
                    f"({cost_display})" if cost_display else None,
                    " ",
                    span(class_="text-secondary fs-7")[
                        "· ",
                        a(
                            href=reverse(
                                "core:pack-edit-weapon-profile",
                                args=(pack.id, pack_item.id, profile.id),
                            ),
                            class_="linked-secondary",
                        )["Edit"],
                        fragment[
                            " · ",
                            a(
                                href=reverse(
                                    "core:pack-delete-weapon-profile",
                                    args=(pack.id, pack_item.id, profile.id),
                                ),
                                class_="linked-danger",
                            )["Archive"],
                        ]
                        if can_archive
                        else None,
                    ],
                ],
                tuple(
                    td(class_=["text-center", stat.classes])[stat.value]
                    for stat in profile.statline()
                ),
            ]
        )
        if len(traitline) > 0:
            rows.append(tr[td(colspan="8")[", ".join(traitline)]])

    return table(class_="table table-sm table-borderless mb-0 fs-7")[
        raw(
            render_to_string(
                "core/includes/weapon_stat_headers.html",
                {**context, "first_col": "Profile"},
                request=request,
            )
        ),
        tbody(class_="table-group-divider")[tuple(rows)],
    ]


def _profiles_block(
    context: dict[str, Any], pack: Any, pack_item: Any, request: Any
) -> Node:
    """The "Profiles" block (``{% if weapon_stat_values or has_named_profiles %}``)."""
    if not (context.get("weapon_stat_values") or context.get("has_named_profiles")):
        return None

    named_profiles = context.get("named_profiles")
    archived_profile_count = context.get("archived_profile_count") or 0

    return div[
        label(class_="form-label")["Profiles"],
        _named_profiles_table(context, pack, pack_item, request)
        if named_profiles
        else p(class_="text-secondary mb-2")["No named profiles yet."],
        div(class_="d-flex gap-1 align-items-center fs-7")[
            a(
                href=reverse(
                    "core:pack-add-weapon-profile", args=(pack.id, pack_item.id)
                ),
                class_="linked-secondary",
            )["Add profile"],
            fragment[
                "· ",
                a(href=context.get("archived_profiles_url"), class_="linked-secondary")[
                    f"Archived ({archived_profile_count})"
                ],
            ]
            if archived_profile_count > 0
            else None,
        ],
    ]


def _form_fields(context: dict[str, Any], form_obj: Any, request: Any) -> Node:
    """The form-field region: the weapon-accessory mod picker or plain ``{{ form }}``."""
    if context.get("slug") == "weapon-accessory":
        return fragment[
            raw(str(form_obj.non_field_errors())),
            tuple(raw(str(field)) for field in form_obj.hidden_fields()),
            tuple(
                div[raw(str(field.as_field_group()))]
                for field in form_obj.standard_fields
            ),
            raw(
                render_to_string(
                    "core/pack/includes/_accessory_mods_picker.html",
                    {**context, "form": form_obj},
                    request=request,
                )
            ),
            raw(
                render_to_string(
                    "core/pack/includes/_mod_picker_shared.html",
                    {**context},
                    request=request,
                )
            ),
        ]
    return raw(str(form_obj))


def _save_row(back_url: str) -> Node:
    return div(class_="mt-3")[
        button(type="submit", class_="btn btn-success")["Save"],
        a(href=back_url, class_="btn btn-link")["Cancel"],
    ]


@register_page("core/pack/pack_item_edit.html")
def pack_item_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_obj = context["content_obj"]
    item_label = context["label"]
    icon = context["icon"]
    slug = context["slug"]
    back_url = context["back_url"]
    is_fighter = context["is_fighter"]
    request = context["request"]

    action = reverse("core:pack-edit-item", args=(pack.id, pack_item.id))

    if is_fighter:
        psyker_url = reverse(
            "core:pack-fighter-default-psyker-powers", args=(pack.id, pack_item.id)
        )
        equipment_url = reverse(
            "core:pack-item-equipment", args=(pack.id, pack_item.id)
        )
        branch: Node = fragment[
            div(class_="vstack gap-3")[
                h1(class_="h3")[i(class_="bi-person"), " Edit ", content_obj.type],
                raw(
                    render_to_string(
                        "core/pack/includes/pack_item_edit_tabs.html",
                        {**context, "active_tab": "details"},
                        request=request,
                    )
                ),
            ],
            div(class_="row")[
                div(class_="col-12 col-xl-5 order-xl-last mb-3 mb-xl-0 ps-xl-4")[
                    raw(
                        render_to_string(
                            "core/pack/includes/fighter_preview_card.html",
                            {
                                **context,
                                "content_fighter": content_obj,
                                "fighter_psyker_url": psyker_url,
                                "fighter_equipment_url": equipment_url,
                            },
                            request=request,
                        )
                    ),
                ],
                div(class_="col-12 col-xl-7")[
                    div(class_="vstack gap-3")[
                        form(action=action, method="post", class_="vstack gap-3")[
                            CsrfInput(request),
                            raw(str(form_obj)),
                            _stats_block(context["stat_values"])
                            if context.get("stat_values")
                            else None,
                            _weapon_stat_include(context, request),
                            _profiles_block(context, pack, pack_item, request),
                            _save_row(back_url),
                        ],
                    ],
                ],
            ],
        ]
    else:
        branch = div(class_="col-12 col-md-8 col-lg-6 vstack gap-3")[
            h1(class_="h3")[i(class_=icon), " Edit ", item_label],
            raw(
                render_to_string(
                    "core/pack/includes/pack_item_edit_tabs_equipment.html",
                    {**context, "active_tab": "details"},
                    request=request,
                )
            )
            if slug in ("gear", "weapon")
            else None,
            form(action=action, method="post", class_="vstack gap-3")[
                CsrfInput(request),
                _form_fields(context, form_obj, request),
                _weapon_stat_include(context, request),
                _profiles_block(context, pack, pack_item, request),
                _save_row(back_url),
            ],
        ]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(context, url=back_url, text=pack.name),
        branch,
    ]
    return Page(title=f"Edit {item_label} - {pack.name}", content=content)
