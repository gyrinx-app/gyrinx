"""Campaign attributes management/display page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import urlencode as _urlencode
from django.urls import reverse

from .. import bridge
from ..design import CsrfInput
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import (
    a,
    button,
    div,
    form,
    h1,
    h2,
    i,
    label,
    noscript,
    option,
    p,
    section,
    select,
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


def _lookup(dictionary: Any, key: Any) -> Any:
    """Port of the ``lookup`` template filter used in the template."""
    if dictionary is None:
        return None
    return dictionary.get(key)


def _swatch(colour: str, size: str, indent: int) -> Node:
    """A coloured circle swatch. The legacy template spreads the ``style``
    attribute across multiple indented lines, so reproduce the exact whitespace
    (the golden test does not normalise inside attribute values)."""
    style = (
        f"width: {size};\n"
        + " " * indent
        + f"height: {size};\n"
        + " " * indent
        + "background-color: "
        + colour
    )
    return span(class_="d-inline-block rounded-circle", style=style)


@register_page("core/campaign/campaign_attributes.html")
def campaign_attributes(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    is_admin = context["is_admin"]
    attribute_types = context["attribute_types"]
    single_select_attribute_types = context["single_select_attribute_types"]
    campaign_lists = context["campaign_lists"]
    user_list_ids = context["user_list_ids"]
    assignment_lookup = context["assignment_lookup"]

    can_edit = is_admin and not campaign.archived

    add_type_action = (
        div(class_="hstack gap-3 ms-md-auto")[
            a(
                href=reverse("core:campaign-attribute-type-new", args=[campaign.id]),
                class_="icon-link linked fs-7",
            )[i(class_="bi-plus-lg"), " Add Attribute type"]
        ]
        if can_edit
        else None
    )
    header = div[
        h1(class_="h3 mb-2")["Campaign Attributes"],
        div(
            class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2"
        )[
            p(class_="text-secondary mb-0")[campaign.name],
            add_type_action,
        ],
    ]

    group_section = None
    if is_admin and not campaign.archived and single_select_attribute_types:
        group_section = _group_section(context, campaign, single_select_attribute_types)

    if attribute_types:
        type_sections: list[Node] = [
            _type_section(
                context,
                campaign,
                attribute_type,
                is_admin,
                can_edit,
                campaign_lists,
                user_list_ids,
                assignment_lookup,
            )
            for attribute_type in attribute_types
        ]
    else:
        type_sections = [_empty_types(campaign, can_edit)]

    content: Node = fragment[
        back_link(context, url=campaign.get_absolute_url(), text="Back to Campaign"),
        div(class_="col-12 px-0 vstack gap-4")[
            header,
            group_section,
            tuple(type_sections),
        ],
    ]
    return Page(
        title=f"Campaign Attributes - {campaign.name}",
        content=content,
    )


def _group_section(
    context: dict[str, Any], campaign: Any, single_select_attribute_types: Any
) -> Node:
    options: list[Node] = [option(value="")["None"]]
    for attr_type in single_select_attribute_types:
        options.append(
            option(
                value=str(attr_type.id),
                selected=(campaign.group_attribute_type_id == attr_type.id),
            )[attr_type.name]
        )
    return section[
        form(
            method="post",
            action=reverse("core:campaign-set-group-attribute", args=[campaign.id]),
            class_="d-flex flex-column flex-md-row align-items-start align-items-md-center gap-2",
        )[
            CsrfInput(context["request"]),
            label(
                for_="group_attribute_type",
                class_="form-label mb-0 text-nowrap fw-semibold",
            )["Group gangs by"],
            select(
                name="group_attribute_type",
                id="group_attribute_type",
                class_="form-select form-select-sm w-auto",
                onchange="this.form.submit()",
            )[tuple(options)],
            noscript[button(type="submit", class_="btn btn-sm btn-success")["Save"]],
            span(class_="text-secondary fs-7")[
                "Gangs will be visually grouped using this attribute on the Campaign page."
            ],
        ]
    ]


def _type_section(
    context: dict[str, Any],
    campaign: Any,
    attribute_type: Any,
    is_admin: bool,
    can_edit: bool,
    campaign_lists: Any,
    user_list_ids: Any,
    assignment_lookup: Any,
) -> Node:
    actions = (
        div(class_="hstack gap-3")[
            a(
                href=reverse(
                    "core:campaign-attribute-value-new",
                    args=[campaign.id, attribute_type.id],
                ),
                class_="icon-link linked fs-7",
            )[i(class_="bi-plus-lg"), " Add value"],
            a(
                href=reverse(
                    "core:campaign-attribute-type-edit",
                    args=[campaign.id, attribute_type.id],
                ),
                class_="icon-link linked-secondary fs-7",
            )[i(class_="bi-pencil"), " Edit"],
            a(
                href=reverse(
                    "core:campaign-attribute-type-remove",
                    args=[campaign.id, attribute_type.id],
                ),
                class_="icon-link link-danger link-underline-opacity-50 link-underline-opacity-100-hover fs-7",
            )[i(class_="bi-trash"), " Remove"],
        ]
        if can_edit
        else None
    )
    header_row = div(class_="d-flex justify-content-between align-items-center mb-2")[
        h2(class_="h5 mb-0")[attribute_type.name],
        actions,
    ]

    description = (
        div(class_="text-secondary fs-7 mb-3 mb-last-0")[attribute_type.description]
        if attribute_type.description
        else None
    )

    values = list(attribute_type.values.all())
    if values:
        body: Node = fragment[
            _values_grid(campaign, values, can_edit),
            _assignments_table(
                context,
                campaign,
                attribute_type,
                is_admin,
                campaign_lists,
                user_list_ids,
                assignment_lookup,
            ),
        ]
    else:
        body = _no_values(campaign, attribute_type, can_edit)

    return section[header_row, description, body]


def _values_grid(campaign: Any, values: Any, can_edit: bool) -> Node:
    cols: list[Node] = []
    for value in values:
        colour_swatch = _swatch(value.colour, "16px", 61) if value.colour else None
        value_actions = (
            div(class_="hstack gap-2")[
                a(
                    href=reverse(
                        "core:campaign-attribute-value-edit",
                        args=[campaign.id, value.id],
                    ),
                    class_="icon-link linked-secondary fs-7",
                )[i(class_="bi-pencil")],
                a(
                    href=reverse(
                        "core:campaign-attribute-value-remove",
                        args=[campaign.id, value.id],
                    ),
                    class_="icon-link link-danger link-underline-opacity-50 link-underline-opacity-100-hover fs-7",
                )[i(class_="bi-trash")],
            ]
            if can_edit
            else None
        )
        cols.append(
            div(class_="col-12 col-md-6 col-lg-4")[
                div(
                    class_="border rounded p-2 d-flex align-items-center justify-content-between"
                )[
                    div(class_="d-flex align-items-center gap-2")[
                        colour_swatch,
                        strong[value.name],
                    ],
                    value_actions,
                ]
            ]
        )
    return div(class_="row g-2 mb-3")[tuple(cols)]


def _assignments_table(
    context: dict[str, Any],
    campaign: Any,
    attribute_type: Any,
    is_admin: bool,
    campaign_lists: Any,
    user_list_ids: Any,
    assignment_lookup: Any,
) -> Node:
    request = context["request"]
    type_assignments = _lookup(assignment_lookup, attribute_type.id)

    rows: list[Node] = []
    for list_ in campaign_lists:
        list_assignments = _lookup(type_assignments, list_.id)
        if list_assignments:
            badges: list[Node] = []
            for assignment in list_assignments:
                attribute_value = assignment.attribute_value
                swatch = (
                    _swatch(attribute_value.colour, "10px", 85)
                    if attribute_value.colour
                    else None
                )
                badges.append(
                    span(
                        class_="badge fw-normal text-bg-light border d-inline-flex align-items-center gap-1"
                    )[swatch, attribute_value.name]
                )
            values_cell: Node = div(class_="hstack gap-2 flex-wrap")[tuple(badges)]
        else:
            values_cell = span(class_="text-secondary fs-7")["Not assigned"]

        assign_action = None
        if not campaign.archived and (is_admin or list_.id in user_list_ids):
            assign_href = (
                reverse(
                    "core:campaign-list-attribute-assign",
                    args=[campaign.id, list_.id, attribute_type.id],
                )
                + "?return_url="
                + _urlencode(request.get_full_path())
            )
            assign_action = a(
                href=assign_href, class_="icon-link linked-secondary fs-7"
            )[i(class_="bi-pencil"), " Assign"]

        rows.append(
            tr[
                td(class_="ps-0")[
                    a(
                        href=reverse("core:list", args=[list_.id]),
                        class_="link-underline-opacity-50 link-underline-opacity-100-hover",
                    )[bridge.list_with_theme(list_)]
                ],
                td[values_cell],
                td(class_="text-end pe-0")[assign_action],
            ]
        )

    return table(class_="table table-sm table-borderless mb-0 align-middle")[
        thead[
            tr[
                th(class_="caps-label ps-0")["Gang"],
                th(class_="caps-label")["Assigned values"],
                th(class_="caps-label text-end pe-0"),
            ]
        ],
        tbody[tuple(rows)],
    ]


def _no_values(campaign: Any, attribute_type: Any, can_edit: bool) -> Node:
    link = (
        a(
            href=reverse(
                "core:campaign-attribute-value-new",
                args=[campaign.id, attribute_type.id],
            )
        )["Create first value →"]
        if can_edit
        else None
    )
    return p(class_="text-secondary fs-7 mb-0")[
        "No values have been defined for this attribute yet.",
        link,
    ]


def _empty_types(campaign: Any, can_edit: bool) -> Node:
    link = (
        a(href=reverse("core:campaign-attribute-type-new", args=[campaign.id]))[
            "Create first Attribute type →"
        ]
        if can_edit
        else None
    )
    return p(class_="text-secondary fs-7 mb-0")[
        "No attribute types have been defined for this Campaign yet.",
        link,
    ]
