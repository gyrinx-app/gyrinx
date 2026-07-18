"""Content-pack detail page component (large display + edit surface)."""

from __future__ import annotations

import itertools
from typing import Any

from django.template.defaultfilters import filesizeformat
from django.template.loader import render_to_string
from django.urls import reverse

from .. import bridge
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    h1,
    h2,
    hr,
    i,
    li,
    nav,
    p,
    section,
    span,
    strong,
    table,
    tbody,
    ul,
)


def _plus_add() -> Node:
    return fragment[i(class_="bi-plus-lg"), " Add"]


def _breadcrumb(pack: Any) -> Node:
    # Rendered with `only` in the legacy template — a fresh context with just
    # these four vars (no request / context processors).
    return raw(
        render_to_string(
            "core/includes/breadcrumb.html",
            {
                "type": "Pack",
                "owner": pack.owner,
                "name": pack.name,
                "type_url": reverse("core:packs"),
            },
        )
    )


def _header_nav(
    pack: Any, context: dict[str, Any], can_edit: bool, is_owner: bool
) -> Node:
    user_lists = context.get("user_lists")
    user_campaigns = context.get("user_campaigns")
    subscribed_list_ids = context.get("subscribed_list_ids")
    subscribed_campaign_ids = context.get("subscribed_campaign_ids")

    add_to_menu = None
    if user_lists or user_campaigns:
        menu_items: list[Node] = []
        if user_lists:
            menu_items.append(
                li[
                    a(
                        href=reverse("core:pack-lists", args=[pack.id]),
                        class_="dropdown-item icon-link",
                    )[
                        i(class_="bi-list-ul"),
                        " List",
                        span(class_="badge text-bg-secondary ms-1")[
                            len(subscribed_list_ids)
                        ]
                        if subscribed_list_ids
                        else None,
                    ]
                ]
            )
        if user_campaigns:
            menu_items.append(
                li[
                    a(
                        href=reverse("core:pack-campaigns", args=[pack.id]),
                        class_="dropdown-item icon-link",
                    )[
                        i(class_="bi-award"),
                        " Campaign",
                        span(class_="badge text-bg-secondary ms-1")[
                            len(subscribed_campaign_ids)
                        ]
                        if subscribed_campaign_ids
                        else None,
                    ]
                ]
            )
        add_to_menu = div(class_="btn-group", role="group")[
            button(
                type="button",
                class_="btn btn-primary btn-sm dropdown-toggle",
                data_bs_toggle="dropdown",
                aria_expanded="false",
            )["Add to…"],
            ul(class_="dropdown-menu dropdown-menu-end")[tuple(menu_items)],
        ]

    edit_group = None
    if can_edit or is_owner:
        edit_group = div(class_="btn-group flex-nowrap")[
            a(
                href=reverse("core:pack-edit", args=[pack.id]),
                class_="btn btn-secondary btn-sm",
            )[i(class_="bi-pencil"), " Edit"]
            if can_edit
            else None,
            div(class_="btn-group", role="group")[
                button(
                    type="button",
                    class_="btn btn-secondary btn-sm dropdown-toggle",
                    data_bs_toggle="dropdown",
                    aria_expanded="false",
                    aria_label="More options",
                )[i(class_="bi-three-dots-vertical")],
                ul(class_="dropdown-menu dropdown-menu-end")[
                    li[
                        a(
                            href=reverse("core:pack-permissions", args=[pack.id]),
                            class_="dropdown-item icon-link",
                        )[i(class_="bi-people"), " Permissions"]
                    ]
                ],
            ]
            if is_owner
            else None,
        ]

    return nav(class_="d-flex flex-nowrap gap-2 ms-md-auto")[
        a(
            href=reverse("core:lists-new-packs") + "?pack=" + str(pack.id),
            class_="btn btn-primary btn-sm",
        )[i(class_="bi-plus-lg"), " Use in new List"],
        add_to_menu,
        edit_group,
    ]


def _header(pack: Any, context: dict[str, Any], can_edit: bool, is_owner: bool) -> Node:
    user = context.get("user")
    authenticated = bool(user and user.is_authenticated)

    if pack.listed:
        visibility = span(
            data_bs_toggle="tooltip",
            data_bs_title="This Content Pack is visible to all users",
        )[i(class_="bi-eye"), " Public"]
    else:
        visibility = span(
            data_bs_toggle="tooltip",
            data_bs_title="This Content Pack can only be accessed by users with the direct link",
        )[i(class_="bi-eye-slash"), " Unlisted"]

    return div(class_="vstack gap-0")[
        _breadcrumb(pack),
        div(
            class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2 mb-2"
        )[
            h1(class_="h2 mb-0")[pack.name],
            _header_nav(pack, context, can_edit, is_owner) if authenticated else None,
        ],
        div(class_="d-flex flex-wrap gap-2 text-secondary fs-7")[visibility],
    ]


def _pack_info(pack: Any) -> Node:
    if not (pack.summary or pack.description):
        return None
    return div(class_="vstack gap-1")[
        div(class_="mb-last-0")[bridge.safe_rich_text(pack.summary)]
        if pack.summary
        else None,
        div(class_="text-secondary fs-7 mb-last-0")[
            bridge.safe_rich_text(pack.description)
        ]
        if pack.description
        else None,
    ]


def _section_bar(title: Node, actions: Node) -> Node:
    return div(
        class_="d-flex justify-content-between align-items-center mb-2 bg-body-tertiary rounded px-2 py-2"
    )[h2(class_="h5 mb-0")[title], actions]


def _rich_desc(value: Any) -> Node:
    return div(
        class_="text-secondary fs-7 mb-last-0 pack-rich-desc border rounded p-2 bg-body-tertiary mt-1"
    )[bridge.safe_rich_text(value)]


# -- House rules -----------------------------------------------------------


def _house_rules_section(pack: Any, entries: list, can_edit: bool) -> Node:
    if not (entries or can_edit):
        return None

    picker_url = reverse("core:pack-house-rule-picker", args=[pack.id])

    if entries:
        body = ul(class_="list-unstyled mb-0")[
            tuple(_house_rule_row(pack, entry, can_edit) for entry in entries)
        ]
    else:
        body = p(class_="text-secondary mb-0")[
            "Override stats on library weapon profiles or fighters. Once created, the change applies to subscribed lists & gangs.",
            a(href=picker_url, class_="linked fs-7")["Add a house rule →"]
            if can_edit
            else None,
        ]

    return fragment[
        section(id="house-rule")[
            _section_bar(
                "House rules",
                a(href=picker_url, class_="btn btn-primary btn-sm")[_plus_add()]
                if can_edit
                else None,
            ),
            div(class_="px-2")[body],
        ],
        hr(class_="my-2"),
    ]


def _house_rule_row(pack: Any, entry: dict, can_edit: bool) -> Node:
    kind = entry["target_kind"]
    if kind == "contentweaponprofile":
        kind_label = "weapon profile"
    elif kind == "contentfighter":
        kind_label = "fighter"
    else:
        kind_label = "equipment"
    pack_item = entry["pack_item"]
    return li(class_="py-1", id=f"item-{pack_item.id}")[
        div(class_="d-flex justify-content-between align-items-center")[
            div[
                span[
                    strong[entry["target"] or "(unresolved target)"],
                    span(class_="text-secondary fs-7")[kind_label],
                ],
                div(class_="text-secondary fs-7")[entry["modifier"]],
            ],
            span(class_="d-flex gap-2")[
                a(
                    href=reverse(
                        "core:pack-house-rule-edit", args=[pack.id, pack_item.id]
                    ),
                    class_="linked-secondary fs-7",
                )["Edit"],
                a(
                    href=reverse(
                        "core:pack-house-rule-delete", args=[pack.id, pack_item.id]
                    ),
                    class_="linked-danger fs-7",
                )["Archive"],
            ]
            if can_edit
            else None,
        ]
    ]


# -- Files -----------------------------------------------------------------


def _files_section(
    pack: Any,
    attachments: list,
    can_edit: bool,
    pack_full: bool,
    max_attachments: int,
) -> Node:
    if not (attachments or can_edit):
        return None

    add_url = reverse("core:pack-attachment-add", args=[pack.id])

    if attachments:
        rows = ul(class_="list-unstyled mb-0")[
            tuple(_attachment_row(pack, att, can_edit) for att in attachments)
        ]
        body: Node = fragment[
            rows,
            p(class_="text-secondary fs-7 mb-0 mt-1")[
                f"This pack has the maximum of {max_attachments} files."
            ]
            if (can_edit and pack_full)
            else None,
        ]
    else:
        body = p(class_="text-secondary mb-0")[
            "Attach scenarios, campaign rules, or reference sheets (PDFs and images) to share alongside this pack.",
            a(href=add_url, class_="linked fs-7")["Add a file →"] if can_edit else None,
        ]

    return fragment[
        section(id="files")[
            _section_bar(
                "Files",
                a(href=add_url, class_="btn btn-primary btn-sm")[_plus_add()]
                if (can_edit and not pack_full)
                else None,
            ),
            div(class_="px-2")[body],
        ],
        hr(class_="my-2"),
    ]


def _attachment_row(pack: Any, att: Any, can_edit: bool) -> Node:
    return li(class_="py-1", id=f"attachment-{att.id}")[
        div(class_="d-flex justify-content-between align-items-center")[
            div[
                a(
                    href=att.file_url,
                    target="_blank",
                    rel="noopener",
                    class_="linked icon-link",
                )[i(class_="bi-file-earmark-arrow-down"), " ", att.display_name],
                span(class_="text-secondary fs-7")[filesizeformat(att.file_size)],
                div(class_="text-secondary fs-7")[att.description]
                if att.description
                else None,
            ],
            span(class_="d-flex gap-2")[
                a(
                    href=reverse("core:pack-attachment-delete", args=[pack.id, att.id]),
                    class_="linked-danger fs-7",
                )["Remove"]
            ]
            if can_edit
            else None,
        ]
    ]


# -- Content sections ------------------------------------------------------


def _add_item_url(pack: Any, slug: str) -> str:
    return reverse("core:pack-add-item", args=[pack.id, slug])


def _archived_url(pack: Any, slug: str) -> str:
    return reverse("core:pack-archived-items", args=[pack.id, slug])


def _archived_link(pack: Any, slug: str, text: str) -> Node:
    return a(href=_archived_url(pack, slug), class_="linked-secondary fs-7")[text]


def _btn_add(pack: Any, slug: str) -> Node:
    return a(href=_add_item_url(pack, slug), class_="btn btn-primary btn-sm")[
        _plus_add()
    ]


def _section_actions(pack: Any, sec: dict) -> Node:
    slug = sec["slug"]
    archived_count = sec["archived_count"]
    links: list[Node] = []

    if slug == "skill":
        if sec.get("skill_tree_archived_count", 0) > 0:
            links.append(
                _archived_link(
                    pack,
                    "skill-tree",
                    f"Archived trees ({sec['skill_tree_archived_count']})",
                )
            )
        if archived_count > 0:
            links.append(
                _archived_link(pack, "skill", f"Archived skills ({archived_count})")
            )
    elif slug == "psyker-power":
        if sec.get("discipline_archived_count", 0) > 0:
            links.append(
                _archived_link(
                    pack,
                    "psyker-discipline",
                    f"Archived disciplines ({sec['discipline_archived_count']})",
                )
            )
        if archived_count > 0:
            links.append(
                _archived_link(
                    pack, "psyker-power", f"Archived powers ({archived_count})"
                )
            )
    elif slug == "attribute-value":
        if sec.get("attribute_archived_count", 0) > 0:
            links.append(
                _archived_link(
                    pack,
                    "attribute",
                    f"Archived attributes ({sec['attribute_archived_count']})",
                )
            )
        if archived_count > 0:
            links.append(
                _archived_link(
                    pack, "attribute-value", f"Archived values ({archived_count})"
                )
            )
    elif archived_count > 0:
        links.append(_archived_link(pack, slug, f"Archived ({archived_count})"))

    if slug == "skill":
        links.append(
            a(href=_add_item_url(pack, "skill"), class_="linked fs-7")[
                "Add skill to existing tree"
            ]
        )
        links.append(_btn_add(pack, "skill-tree"))
    elif slug == "psyker-power":
        links.append(
            a(href=_add_item_url(pack, "psyker-power"), class_="linked fs-7")[
                "Add power to existing discipline"
            ]
        )
        links.append(_btn_add(pack, "psyker-discipline"))
    elif slug == "attribute-value":
        links.append(
            a(href=_add_item_url(pack, "attribute-value"), class_="linked fs-7")[
                "Add value to existing attribute"
            ]
        )
        links.append(_btn_add(pack, "attribute"))
    elif slug == "weapon":
        links.append(
            a(
                href=reverse("core:pack-customise-weapon-picker", args=[pack.id]),
                class_="linked fs-7",
            )["Customise existing weapon"]
        )
        if sec["can_add"]:
            links.append(_btn_add(pack, slug))
    elif sec["can_add"]:
        links.append(_btn_add(pack, slug))

    return span(class_="d-flex gap-2 align-items-center")[tuple(links)]


def _render_section(
    pack: Any, sec: dict, can_edit: bool, context: dict[str, Any], request: Any
) -> Node:
    slug = sec["slug"]
    if slug in ("skill-tree", "psyker-discipline", "attribute"):
        return None
    if not (can_edit or sec["has_content"]):
        return None

    body = _section_body(pack, sec, can_edit, context, request)
    node = section(id=slug)[
        _section_bar(sec["label"], _section_actions(pack, sec) if can_edit else None),
        div(class_="px-2")[body],
    ]
    if slug == "gear":
        return fragment[hr(class_="my-2"), node]
    return node


def _section_body(
    pack: Any, sec: dict, can_edit: bool, context: dict[str, Any], request: Any
) -> Node:
    slug = sec["slug"]
    if slug == "weapon":
        return _weapon_body(pack, sec, can_edit, context, request)
    if slug == "fighter":
        return _fighter_body(pack, sec, can_edit, context, request)
    if slug == "skill":
        return _skill_body(pack, sec, can_edit)
    if slug == "psyker-power":
        return _psyker_body(pack, sec, can_edit)
    if slug == "attribute-value":
        return _attribute_body(pack, sec, can_edit)
    if sec["items"]:
        return _generic_list_body(pack, sec, can_edit)
    return _empty_state(pack, sec, can_edit)


def _weapon_body(
    pack: Any, sec: dict, can_edit: bool, context: dict[str, Any], request: Any
) -> Node:
    if not sec["items"]:
        return p(class_="text-secondary mb-0")[
            "Custom weapons with one or more profiles. Once created, they can be added to fighters in this pack or subscribed lists & gangs.",
            a(href=_add_item_url(pack, "weapon"), class_="linked fs-7")[
                "Add a weapon →"
            ]
            if (can_edit and sec["can_add"])
            else None,
        ]

    headers = raw(
        render_to_string(
            "core/includes/weapon_stat_headers.html",
            {**context, "show_al": True},
            request=request,
        )
    )
    bodies = []
    for entry in sec["items"]:
        row_id = (
            f"item-{entry['pack_item'].id}"
            if entry.get("pack_item")
            else f"weapon-{entry['content_object'].id}"
        )
        profiles_html = raw(
            render_to_string(
                "core/pack/includes/weapon_profiles_display.html",
                {
                    **context,
                    "profiles": entry["profiles"],
                    "pack_item": entry.get("pack_item"),
                    "weapon": entry["content_object"],
                    "can_edit": can_edit,
                    "show_al": True,
                    "is_customised": entry.get("is_customised", False),
                    "show_actions_row": True,
                },
                request=request,
            )
        )
        bodies.append(tbody(class_="table-group-divider", id=row_id)[profiles_html])
    return table(class_="table table-sm table-borderless mb-0 fs-7")[
        headers, tuple(bodies)
    ]


def _fighter_body(
    pack: Any, sec: dict, can_edit: bool, context: dict[str, Any], request: Any
) -> Node:
    items = sec["items"]
    if not items:
        return p(class_="text-secondary mb-0")[
            "Custom fighter and vehicle archetypes that gangs in this pack can hire.",
            a(href=_add_item_url(pack, "fighter"), class_="linked fs-7")[
                "Add a fighter →"
            ]
            if (can_edit and sec["can_add"])
            else None,
        ]

    groups = []
    for grouper, group_iter in itertools.groupby(
        items, key=lambda e: e["content_object"].house
    ):
        group_entries = list(group_iter)
        groups.append(
            div[
                div(class_="caps-label mb-2")[grouper] if grouper else None,
                div(class_="row g-3")[
                    tuple(
                        div(
                            id=f"item-{entry['pack_item'].id}", class_="col-12 col-lg-6"
                        )[_fighter_card(pack, sec, entry, can_edit, context, request)]
                        for entry in group_entries
                    )
                ],
            ]
        )
    return div(class_="vstack gap-3")[tuple(groups)]


def _fighter_card(
    pack: Any,
    sec: dict,
    entry: dict,
    can_edit: bool,
    context: dict[str, Any],
    request: Any,
) -> Node:
    card_ctx = {
        **context,
        "content_fighter": entry["content_object"],
        "preview_statline": entry["preview_statline"],
        "preview_rules": entry["preview_rules"],
        "preview_skills": entry["preview_skills"],
        "preview_weapons": entry["preview_weapons"],
        "preview_gear": entry["preview_gear"],
        "preview_disciplines": entry["preview_disciplines"],
        "preview_default_powers": entry["preview_default_powers"],
        "auto_equipment": entry["auto_equipment"],
    }
    if can_edit:
        pack_item = entry["pack_item"]
        card_ctx.update(
            {
                "fighter_edit_url": reverse(
                    "core:pack-edit-item", args=[pack.id, pack_item.id]
                ),
                "fighter_archive_url": reverse(
                    "core:pack-delete-item", args=[pack.id, pack_item.id]
                ),
                "fighter_can_add": sec["can_add"],
                "fighter_equipment_url": reverse(
                    "core:pack-item-equipment", args=[pack.id, pack_item.id]
                ),
                "fighter_psyker_url": reverse(
                    "core:pack-fighter-default-psyker-powers",
                    args=[pack.id, pack_item.id],
                ),
            }
        )
    return raw(
        render_to_string(
            "core/pack/includes/fighter_preview_card.html", card_ctx, request=request
        )
    )


def _grouped_body(
    pack: Any,
    groups: list,
    can_edit: bool,
    *,
    grouper_key: str,
    add_slug: str,
    add_label: str,
    edit_label: str,
    archive_label: str,
    children_key: str,
    empty_text: str,
    generic_query: str | None = None,
    intro: Any = None,
) -> Node:
    blocks = []
    for group in groups:
        grouper = group[grouper_key]
        pack_item = group["pack_item"]
        query = f"?{generic_query}={grouper.id}" if generic_query else ""
        head_actions: list[Node] = []
        if can_edit:
            head_actions.append(
                a(href=_add_item_url(pack, add_slug) + query, class_="linked fs-7")[
                    add_label
                ]
            )
            if pack_item:
                head_actions.append(
                    a(
                        href=reverse(
                            "core:pack-edit-item", args=[pack.id, pack_item.id]
                        ),
                        class_="linked-secondary fs-7",
                    )[edit_label]
                )
                head_actions.append(
                    a(
                        href=reverse(
                            "core:pack-delete-item", args=[pack.id, pack_item.id]
                        ),
                        class_="linked-danger fs-7",
                    )[archive_label]
                )
        entries = group[children_key]
        if entries:
            inner = ul(class_="list-unstyled mb-0")[
                tuple(_grouped_entry(pack, e, can_edit) for e in entries)
            ]
        else:
            inner = p(class_="text-secondary fs-7 mb-0")[empty_text]
        blocks.append(
            div(**({"id": f"item-{pack_item.id}"} if pack_item else {}))[
                div(class_="d-flex justify-content-between align-items-center mb-1")[
                    div(class_="text-secondary text-uppercase fs-7 fw-semibold")[
                        grouper.name
                    ],
                    span(class_="d-flex gap-2 align-items-center")[tuple(head_actions)],
                ],
                intro(group) if intro else None,
                inner,
            ]
        )
    return div(class_="vstack gap-3")[tuple(blocks)]


def _grouped_entry(pack: Any, entry: dict, can_edit: bool) -> Node:
    obj = entry["content_object"]
    pack_item = entry["pack_item"]
    return li(class_="py-1", id=f"item-{pack_item.id}")[
        div(class_="d-flex justify-content-between align-items-start")[
            span[obj.name],
            span(class_="d-flex gap-2")[
                a(
                    href=reverse("core:pack-edit-item", args=[pack.id, pack_item.id]),
                    class_="linked-secondary fs-7",
                )["Edit"],
                a(
                    href=reverse("core:pack-delete-item", args=[pack.id, pack_item.id]),
                    class_="linked-danger fs-7",
                )["Archive"],
            ]
            if can_edit
            else None,
        ],
        _rich_desc(obj.description) if obj.description else None,
    ]


def _skill_body(pack: Any, sec: dict, can_edit: bool) -> Node:
    if sec["skill_groups"]:
        return _grouped_body(
            pack,
            sec["skill_groups"],
            can_edit,
            grouper_key="category",
            add_slug="skill",
            add_label="Add skill",
            edit_label="Edit tree",
            archive_label="Archive tree",
            children_key="skills",
            empty_text="No skills in this tree yet.",
            generic_query="category",
        )
    return p(class_="text-secondary mb-0")[
        "Custom Skill Trees and the skills inside them. Once created, they can be assigned to fighters in this pack or subscribed lists & gangs.",
        a(href=_add_item_url(pack, "skill-tree"), class_="linked fs-7")[
            "Add a skill tree →"
        ]
        if can_edit
        else None,
    ]


def _psyker_intro(group: dict) -> Node:
    disc = group["discipline"]
    return fragment[
        div(class_="text-secondary fs-7 mb-1")["Available to all psykers"]
        if disc.generic
        else None,
        div(
            class_="text-secondary fs-7 mb-1 mb-last-0 pack-rich-desc border rounded p-2 bg-body-tertiary"
        )[bridge.safe_rich_text(disc.description)]
        if disc.description
        else None,
    ]


def _psyker_body(pack: Any, sec: dict, can_edit: bool) -> Node:
    if sec["power_groups"]:
        return _grouped_body(
            pack,
            sec["power_groups"],
            can_edit,
            grouper_key="discipline",
            add_slug="psyker-power",
            add_label="Add power",
            edit_label="Edit discipline",
            archive_label="Archive discipline",
            children_key="powers",
            empty_text="No powers in this discipline yet.",
            generic_query="discipline",
            intro=_psyker_intro,
        )
    return p(class_="text-secondary mb-0")[
        "Custom Wyrd Power Disciplines and the powers within them. Once created, they can be assigned to psykers in this pack or subscribed lists & gangs.",
        a(href=_add_item_url(pack, "psyker-discipline"), class_="linked fs-7")[
            "Add a discipline →"
        ]
        if can_edit
        else None,
    ]


def _attribute_intro(group: dict) -> Node:
    attr = group["attribute"]
    if not attr.restricted_to.exists():
        return None
    houses = list(attr.restricted_to.all())
    return div(class_="text-secondary fs-7 mb-1")[
        "Restricted to: " + " , ".join(h.name for h in houses)
    ]


def _attribute_body(pack: Any, sec: dict, can_edit: bool) -> Node:
    if sec["attribute_groups"]:
        return _grouped_body(
            pack,
            sec["attribute_groups"],
            can_edit,
            grouper_key="attribute",
            add_slug="attribute-value",
            add_label="Add value",
            edit_label="Edit attribute",
            archive_label="Archive attribute",
            children_key="values",
            empty_text="No values for this attribute yet.",
            generic_query="attribute",
            intro=_attribute_intro,
        )
    return p(class_="text-secondary mb-0")[
        "Custom gang-level traits and the values gangs can pick from.",
        a(href=_add_item_url(pack, "attribute"), class_="linked fs-7")[
            "Add an attribute →"
        ]
        if can_edit
        else None,
    ]


_DESC_SLUGS = {
    "rule",
    "weapon-trait",
    "house",
    "gear",
    "weapon-accessory",
    "psyker-discipline",
}


def _generic_list_body(pack: Any, sec: dict, can_edit: bool) -> Node:
    slug = sec["slug"]
    rows = []
    for entry in sec["items"]:
        obj = entry["content_object"]
        pack_item = entry["pack_item"]
        rows.append(
            li(class_="py-1", id=f"item-{pack_item.id}")[
                div(class_="d-flex justify-content-between align-items-start")[
                    div[
                        span[obj],
                        span(class_="text-secondary fs-7")[f"({obj.cost}¢)"]
                        if slug == "weapon-accessory"
                        else None,
                    ],
                    span(class_="d-flex gap-2")[
                        a(
                            href=reverse(
                                "core:pack-edit-item", args=[pack.id, pack_item.id]
                            ),
                            class_="linked-secondary fs-7",
                        )["Edit"]
                        if sec["can_add"]
                        else None,
                        a(
                            href=reverse(
                                "core:pack-delete-item", args=[pack.id, pack_item.id]
                            ),
                            class_="linked-danger fs-7",
                        )["Archive"],
                    ]
                    if (can_edit and not entry.get("is_auto_equipment"))
                    else None,
                ],
                _rich_desc(obj.description)
                if (slug in _DESC_SLUGS and obj.description)
                else None,
            ]
        )
    return ul(class_="list-unstyled mb-0")[tuple(rows)]


_EMPTY_STATES = {
    "house": (
        "Make custom factions or houses available to gangs using this pack.",
        "house",
        "Add a house →",
        True,
    ),
    "rule": (
        "Short named special rules. Once created, they can be attached to fighters in this pack or subscribed lists & gangs.",
        "rule",
        "Add a special rule →",
        True,
    ),
    "gear": (
        "Custom non-weapon equipment. Once created, it can be added to fighters in this pack or subscribed lists & gangs.",
        "gear",
        "Add gear →",
        True,
    ),
    "weapon-trait": (
        "Custom weapon special rules. Once created, they can be attached to weapon profiles in this pack or subscribed lists & gangs.",
        "weapon-trait",
        "Add a trait →",
        True,
    ),
    "weapon-accessory": (
        "Custom weapon attachments that modify a weapon's stats when fitted. Once created, they can be added to fighters in this pack or subscribed lists & gangs.",
        "weapon-accessory",
        "Add an accessory →",
        True,
    ),
}


def _empty_state(pack: Any, sec: dict, can_edit: bool) -> Node:
    slug = sec["slug"]
    spec = _EMPTY_STATES.get(slug)
    if spec is None:
        return p(class_="text-secondary mb-0")[
            f"No {sec['label'].lower()} in this Content Pack yet."
        ]
    text, add_slug, add_label, needs_can_add = spec
    show_link = can_edit and (sec["can_add"] if needs_can_add else True)
    return p(class_="text-secondary mb-0")[
        text,
        a(href=_add_item_url(pack, add_slug), class_="linked fs-7")[add_label]
        if show_link
        else None,
    ]


# -- Activity --------------------------------------------------------------


def _activity_section(
    pack: Any,
    recent_activities: list,
    total_activity_count: int,
    context: dict[str, Any],
    request: Any,
) -> Node:
    activity_url = reverse("core:pack-activity", args=[pack.id])
    if recent_activities:
        items = raw(
            "".join(
                str(
                    render_to_string(
                        "core/includes/pack_activity_item.html",
                        {**context, "activity": activity},
                        request=request,
                    )
                )
                for activity in recent_activities
            )
        )
        body: Node = fragment[
            div(class_="list-group list-group-flush")[items],
            a(href=activity_url, class_="fs-7 mt-2 d-inline-block")[
                f"View all {total_activity_count} activities →"
            ]
            if total_activity_count > 5
            else None,
        ]
    else:
        body = p(class_="text-secondary fs-7 mb-0")["No activity yet."]

    return section[
        _section_bar(
            "Activity",
            a(href=activity_url, class_="linked fs-7")["View all →"]
            if total_activity_count > 0
            else None,
        ),
        div(class_="px-2")[body],
    ]


# -- Quick-add sidebar -----------------------------------------------------


def _quick_add_card(pack: Any, slug: str, title: str, desc: str) -> Node:
    return a(
        href=_add_item_url(pack, slug),
        class_="border rounded p-3 d-flex align-items-center gap-3 text-decoration-none",
    )[
        i(class_="bi-plus-lg flex-shrink-0"),
        div(class_="flex-grow-1")[
            h2(class_="h5 mb-1")[title],
            p(class_="text-secondary fs-7 mb-0")[desc],
        ],
        i(class_="bi-chevron-right flex-shrink-0"),
    ]


def _quick_add(pack: Any) -> Node:
    return div(class_="col-12 col-xl-4 order-1 order-xl-2")[
        div(class_="caps-label mb-2")["Quick add"],
        div(class_="vstack gap-2")[
            _quick_add_card(
                pack,
                "fighter",
                "Add a Fighter",
                "Custom fighter or vehicle archetypes that gangs in this pack can hire.",
            ),
            _quick_add_card(
                pack,
                "gear",
                "Add gear",
                "Custom non-weapon equipment that fighters in this pack can buy.",
            ),
            _quick_add_card(
                pack,
                "weapon",
                "Add a Weapon",
                "Custom weapons with one or more profiles for fire modes or ammo.",
            ),
        ],
    ]


@register_page("core/pack/pack.html")
def pack_detail(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    request = context["request"]
    can_edit = context["can_edit"]
    is_owner = context["is_owner"]
    content_sections = context["content_sections"]

    section_nodes = [
        _render_section(pack, sec, can_edit, context, request)
        for sec in content_sections
    ]

    main_column = div(class_="col-12 col-xl-8 order-2 order-xl-1 px-0 px-xl-2")[
        div(class_="vstack gap-4")[
            _house_rules_section(pack, context["house_rule_entries"], can_edit),
            _files_section(
                pack,
                context["attachments"],
                can_edit,
                context["pack_full"],
                context["max_attachments"],
            ),
            tuple(section_nodes),
            hr(class_="my-2") if content_sections else None,
            _activity_section(
                pack,
                context["recent_activities"],
                context["total_activity_count"],
                context,
                request,
            ),
        ]
    ]

    content: Node = div(class_="col-lg-12 px-0 vstack gap-4")[
        div(class_=["col-12 px-0 vstack gap-4", {"col-xl-8": not can_edit}])[
            _header(pack, context, can_edit, is_owner),
            _pack_info(pack),
        ],
        div(class_="row g-4")[
            main_column,
            _quick_add(pack) if can_edit else None,
        ],
    ]

    return Page(title=pack.name, content=content)
