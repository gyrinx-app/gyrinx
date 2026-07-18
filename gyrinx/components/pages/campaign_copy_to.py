"""Copy campaign content to another campaign form/confirmation page component."""

from __future__ import annotations

from typing import Any

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
    h5,
    i,
    input_,
    label,
    li,
    p,
    span,
    strong,
    ul,
)
from ._shared import back_link


@register_page("core/campaign/campaign_copy_to.html")
def campaign_copy_to(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    form_obj = context["form"]
    target_campaign = context.get("target_campaign")
    conflicts = context.get("conflicts")
    show_confirmation = context.get("show_confirmation")
    request = context["request"]

    campaign_url = campaign.get_absolute_url()

    def checkbox_group(name: str) -> Node:
        field = form_obj[name]
        if not form_obj.fields[name].choices:
            return None
        onclick = (
            f"document.querySelectorAll('[name={name}]')"
            ".forEach(cb => cb.checked = true); return false;"
        )
        return div[
            div(class_="d-flex justify-content-between align-items-center mb-1")[
                label(class_="form-label mb-0")[field.label],
                a(href="#", class_="fs-7 link-secondary", onclick=onclick)[
                    "Select all"
                ],
            ],
            div(class_="form-text mb-2")[field.help_text] if field.help_text else None,
            tuple(
                div(class_="form-check")[
                    raw(str(choice.tag())),
                    label(class_="form-check-label", for_=choice.id_for_label)[
                        choice.choice_label
                    ],
                ]
                for choice in field
            ),
            div(class_="text-danger fs-7 mt-1")[field.errors[0]]
            if field.errors
            else None,
        ]

    if show_confirmation:
        body = _confirmation_form(
            form_obj, campaign, target_campaign, conflicts, campaign_url, request
        )
    else:
        body = _selection_form(form_obj, checkbox_group, campaign_url, request)

    content: Node = fragment[
        back_link(context, url=campaign_url, text="Back to Campaign"),
        div(class_="col-12 col-md-8 col-lg-6 px-0 vstack gap-4")[
            div[
                h1(class_="h3 mb-2")["Copy to another Campaign"],
                p(class_="text-secondary mb-0")[
                    "Copy asset types, assets, resource types, attribute types, and "
                    "custom content packs from ",
                    strong[campaign.name],
                    " to another Campaign.",
                ],
            ],
            body,
        ],
    ]

    return Page(
        title=f"Copy Content To Another Campaign - {campaign.name}",
        content=content,
    )


def _selection_form(form_obj, checkbox_group, campaign_url, request) -> Node:
    tc = form_obj["target_campaign"]
    non_field_errors = form_obj.non_field_errors()
    return form(method="post")[
        CsrfInput(request),
        input_(type="hidden", name="action", value="preview"),
        div(class_="vstack gap-3")[
            div[
                label(for_="id_target_campaign", class_="form-label")[tc.label],
                raw(str(tc)),
                div(class_="form-text")[tc.help_text] if tc.help_text else None,
                div(class_="text-danger fs-7 mt-1")[tc.errors[0]]
                if tc.errors
                else None,
            ],
            checkbox_group("asset_types"),
            checkbox_group("resource_types"),
            checkbox_group("attribute_types"),
            checkbox_group("packs"),
            div(class_="text-danger fs-7")[non_field_errors[0]]
            if non_field_errors
            else None,
            div(class_="hstack gap-2")[
                button(type="submit", class_="btn btn-primary")[
                    i(class_="bi-arrow-right"), " Preview Copy"
                ],
                a(href=campaign_url, class_="btn btn-link")["Cancel"],
            ],
        ],
    ]


def _confirmation_form(
    form_obj, campaign, target_campaign, conflicts, campaign_url, request
) -> Node:
    def summary_block(name: str, title: str, wrapper_class: str) -> Node:
        selected = form_obj.cleaned_data.get(name, [])
        if not selected:
            return None
        return div(class_=wrapper_class)[
            span(class_="caps-label")[title],
            ul(class_="mb-0 ps-3")[
                tuple(
                    li(class_="fs-7")[choice_label]
                    for choice_id, choice_label in form_obj.fields[name].choices
                    if choice_id in selected
                )
            ],
        ]

    def conflict_list(attr: str, title: str, wrapper_class: str) -> Node:
        names = getattr(conflicts, attr)
        if not names:
            return None
        return div(class_=wrapper_class)[
            span(class_="caps-label")[title],
            ul(class_="mb-0 ps-3 fs-7")[tuple(li[name] for name in names)],
        ]

    conflicts_block = None
    if conflicts is not None and conflicts.has_conflicts:
        conflicts_block = div(
            class_="border border-warning rounded p-3 bg-warning-subtle"
        )[
            h5(class_="mb-2 text-warning-emphasis")[
                i(class_="bi-exclamation-triangle"), " Conflicts Found"
            ],
            p(class_="fs-7 mb-2")[
                "The following items already exist in ",
                strong[target_campaign.name],
                " and will be skipped:",
            ],
            conflict_list("asset_type_conflicts", "Asset Types", "mb-2"),
            conflict_list("resource_type_conflicts", "Resource Types", "mb-2"),
            conflict_list("attribute_type_conflicts", "Attribute Types", "mb-0"),
            p(class_="fs-7 text-secondary mt-2 mb-0")[
                "Rename these items in the target campaign first if you want to copy them."
            ],
        ]

    return form(method="post")[
        CsrfInput(request),
        input_(type="hidden", name="action", value="confirm"),
        input_(type="hidden", name="target_campaign_id", value=target_campaign.id),
        tuple(
            input_(type="hidden", name="selected_asset_types", value=at_id)
            for at_id in form_obj.cleaned_data.get("asset_types", [])
        ),
        tuple(
            input_(type="hidden", name="selected_resource_types", value=rt_id)
            for rt_id in form_obj.cleaned_data.get("resource_types", [])
        ),
        tuple(
            input_(type="hidden", name="selected_attribute_types", value=att_id)
            for att_id in form_obj.cleaned_data.get("attribute_types", [])
        ),
        tuple(
            input_(type="hidden", name="selected_packs", value=pack_id)
            for pack_id in form_obj.cleaned_data.get("packs", [])
        ),
        div(class_="vstack gap-3")[
            div(class_="border rounded p-3")[
                h5(class_="mb-2")["Ready to Copy"],
                p(class_="text-secondary fs-7 mb-2")[
                    "Copying from ",
                    strong[campaign.name],
                    " to ",
                    strong[target_campaign.name],
                    ".",
                ],
                summary_block("asset_types", "Asset Types", "mb-2"),
                summary_block("resource_types", "Resource Types", "mb-2"),
                summary_block("attribute_types", "Attribute Types", "mb-2"),
                summary_block("packs", "Content Packs", "mb-0"),
            ],
            conflicts_block,
            div(class_="hstack gap-2")[
                button(type="submit", class_="btn btn-primary")[
                    i(class_="bi-clipboard"), " Copy Content"
                ],
                a(href=campaign_url, class_="btn btn-link")["Cancel"],
            ],
        ],
    ]
