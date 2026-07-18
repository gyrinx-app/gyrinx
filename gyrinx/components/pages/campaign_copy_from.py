"""Campaign "copy content from another campaign" page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from gyrinx.core.templatetags.custom_tags import plain_text_truncate

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
    h3,
    h5,
    h6,
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


def _summary_list(label_text: str, choices, selected, *, wrapper_class: str) -> Node:
    """One "Ready to Copy" section: caps label + the chosen items as a list."""
    return div(class_=wrapper_class)[
        span(class_="caps-label")[label_text],
        ul(class_="mb-0 ps-3")[
            tuple(
                li(class_="fs-7")[choice_label]
                for choice_id, choice_label in choices
                if choice_id in selected
            )
        ],
    ]


def _conflict_list(label_text: str, names, *, wrapper_class: str) -> Node:
    return div(class_=wrapper_class)[
        span(class_="caps-label")[label_text],
        ul(class_="mb-0 ps-3 fs-7")[tuple(li[name] for name in names)],
    ]


def _confirmation(context: dict[str, Any]) -> Node:
    campaign = context["campaign"]
    source_campaign = context["source_campaign"]
    conflicts = context["conflicts"]
    form_obj = context["form"]
    request = context["request"]

    cleaned = getattr(form_obj, "cleaned_data", {}) or {}
    asset_types = cleaned.get("asset_types") or []
    resource_types = cleaned.get("resource_types") or []
    attribute_types = cleaned.get("attribute_types") or []
    packs = cleaned.get("packs") or []

    ready_body: list[Node] = [
        h5(class_="mb-2")["Ready to Copy"],
        p(class_="text-secondary fs-7 mb-2")[
            "Copying from ",
            strong[source_campaign.name],
            " to ",
            strong[campaign.name],
            ".",
        ],
    ]
    if asset_types:
        ready_body.append(
            _summary_list(
                "Asset Types",
                form_obj.fields["asset_types"].choices,
                asset_types,
                wrapper_class="mb-2",
            )
        )
    if resource_types:
        ready_body.append(
            _summary_list(
                "Resource Types",
                form_obj.fields["resource_types"].choices,
                resource_types,
                wrapper_class="mb-2",
            )
        )
    if attribute_types:
        ready_body.append(
            _summary_list(
                "Attribute Types",
                form_obj.fields["attribute_types"].choices,
                attribute_types,
                wrapper_class="mb-2",
            )
        )
    if packs:
        ready_body.append(
            _summary_list(
                "Content Packs",
                form_obj.fields["packs"].choices,
                packs,
                wrapper_class="mb-0",
            )
        )

    conflicts_block: Node = None
    if conflicts and conflicts.has_conflicts:
        conflict_body: list[Node] = [
            h5(class_="mb-2 text-warning-emphasis")[
                i(class_="bi-exclamation-triangle"), " Conflicts Found"
            ],
            p(class_="fs-7 mb-2")[
                "The following items already exist in ",
                strong[campaign.name],
                " and will be skipped:",
            ],
        ]
        if conflicts.asset_type_conflicts:
            conflict_body.append(
                _conflict_list(
                    "Asset Types",
                    conflicts.asset_type_conflicts,
                    wrapper_class="mb-2",
                )
            )
        if conflicts.resource_type_conflicts:
            conflict_body.append(
                _conflict_list(
                    "Resource Types",
                    conflicts.resource_type_conflicts,
                    wrapper_class="mb-2",
                )
            )
        if conflicts.attribute_type_conflicts:
            conflict_body.append(
                _conflict_list(
                    "Attribute Types",
                    conflicts.attribute_type_conflicts,
                    wrapper_class="mb-0",
                )
            )
        conflict_body.append(
            p(class_="fs-7 text-secondary mt-2 mb-0")[
                "Rename these items in the target campaign first if you want to copy them."
            ]
        )
        conflicts_block = div(
            class_="border border-warning rounded p-3 bg-warning-subtle"
        )[tuple(conflict_body)]

    hidden_inputs: list[Node] = [
        input_(type="hidden", name="action", value="confirm"),
        input_(type="hidden", name="source_campaign_id", value=source_campaign.id),
    ]
    hidden_inputs += [
        input_(type="hidden", name="selected_asset_types", value=at_id)
        for at_id in asset_types
    ]
    hidden_inputs += [
        input_(type="hidden", name="selected_resource_types", value=rt_id)
        for rt_id in resource_types
    ]
    hidden_inputs += [
        input_(type="hidden", name="selected_attribute_types", value=att_id)
        for att_id in attribute_types
    ]
    hidden_inputs += [
        input_(type="hidden", name="selected_packs", value=pack_id) for pack_id in packs
    ]

    return form(method="post")[
        CsrfInput(request),
        tuple(hidden_inputs),
        div(class_="vstack gap-3")[
            div(class_="border rounded p-3")[tuple(ready_body)],
            conflicts_block,
            div(class_="hstack gap-2")[
                button(type="submit", class_="btn btn-primary")[
                    i(class_="bi-clipboard"), " Copy Content"
                ],
                a(href=campaign.get_absolute_url(), class_="btn btn-link")["Cancel"],
            ],
        ],
    ]


def _type_block(form_obj: Any, field_name: str, empty_message: str | None) -> Node:
    bound = form_obj[field_name]
    if not form_obj.fields[field_name].choices:
        if empty_message is None:
            return None
        return p(class_="text-secondary fs-7")[empty_message]

    inner: list[Node] = [
        div(class_="d-flex justify-content-between align-items-center mb-1")[
            label(class_="form-label mb-0")[bound.label],
            a(
                href="#",
                class_="fs-7 link-secondary",
                onclick=(
                    f"document.querySelectorAll('[name={field_name}]')"
                    ".forEach(cb => cb.checked = true); return false;"
                ),
            )["Select all"],
        ]
    ]
    if bound.help_text:
        inner.append(div(class_="form-text mb-2")[bound.help_text])
    for choice in bound:
        inner.append(
            div(class_="form-check")[
                choice.tag(),
                label(class_="form-check-label", for_=choice.id_for_label)[
                    choice.choice_label
                ],
            ]
        )
    if bound.errors:
        inner.append(div(class_="text-danger fs-7 mt-1")[bound.errors[0]])
    return div[tuple(inner)]


def _selection_form(context: dict[str, Any]) -> Node:
    campaign = context["campaign"]
    source_campaign = context["source_campaign"]
    form_obj = context["form"]
    template_campaigns = context["template_campaigns"]
    request = context["request"]

    stack: list[Node] = []

    if source_campaign:
        # Show selected source with change link.
        if source_campaign.template:
            source_card: Node = div(class_="border rounded p-3")[
                h6(class_="mb-1")[source_campaign.name],
                div(class_="text-secondary fs-7 mb-0 mb-last-0")[
                    plain_text_truncate(source_campaign.summary, 150)
                ]
                if source_campaign.summary
                else None,
            ]
        else:
            source_card = div(class_="border rounded p-2")[span[source_campaign.name]]
        stack.append(
            div[
                div(class_="d-flex justify-content-between align-items-center mb-1")[
                    label(class_="form-label mb-0")[form_obj["source_campaign"].label],
                    a(
                        href=reverse("core:campaign-copy-in", args=[campaign.id]),
                        class_="fs-7 link-secondary",
                    )["Change"],
                ],
                input_(type="hidden", name="source_campaign", value=source_campaign.id),
                source_card,
            ]
        )
    else:
        # Source campaign dropdown.
        source_field = form_obj["source_campaign"]
        stack.append(
            div[
                label(for_="id_source_campaign", class_="form-label")[
                    source_field.label
                ],
                raw(str(source_field)),
                div(class_="form-text")[source_field.help_text]
                if source_field.help_text
                else None,
                div(class_="text-danger fs-7 mt-1")[source_field.errors[0]]
                if source_field.errors
                else None,
            ]
        )
        if template_campaigns:
            stack.append(
                div[
                    p(class_="text-secondary fs-7 mb-2")["Or use a template:"],
                    div(class_="vstack gap-2")[
                        tuple(
                            div(class_="border rounded p-3")[
                                div(
                                    class_="d-flex justify-content-between align-items-start gap-3"
                                )[
                                    div[
                                        h6(class_="mb-1")[tc.name],
                                        div(
                                            class_="text-secondary fs-7 mb-0 mb-last-0"
                                        )[plain_text_truncate(tc.summary, 150)]
                                        if tc.summary
                                        else None,
                                    ],
                                    button(
                                        type="button",
                                        class_="btn btn-sm btn-outline-primary flex-shrink-0",
                                        onclick=(
                                            "document.getElementById('id_source_campaign')"
                                            f".value='{tc.id}'; this.closest('form').submit();"
                                        ),
                                    )["Use this template"],
                                ]
                            ]
                            for tc in template_campaigns
                        )
                    ],
                ]
            )

    if source_campaign:
        stack.append(
            _type_block(
                form_obj, "asset_types", "This campaign has no asset types to copy."
            )
        )
        stack.append(
            _type_block(
                form_obj,
                "resource_types",
                "This campaign has no resource types to copy.",
            )
        )
        stack.append(
            _type_block(
                form_obj,
                "attribute_types",
                "This campaign has no attribute types to copy.",
            )
        )
        stack.append(_type_block(form_obj, "packs", None))

    non_field_errors = form_obj.non_field_errors()
    if non_field_errors:
        stack.append(div(class_="text-danger fs-7")[non_field_errors[0]])

    if source_campaign:
        submit_button = button(type="submit", class_="btn btn-primary")[
            i(class_="bi-arrow-right"), " Preview Copy"
        ]
    else:
        submit_button = button(type="submit", class_="btn btn-primary")[
            "Next ", i(class_="bi-arrow-right")
        ]
    stack.append(
        div(class_="hstack gap-2")[
            submit_button,
            a(href=campaign.get_absolute_url(), class_="btn btn-link")["Cancel"],
        ]
    )

    return form(method="post")[
        CsrfInput(request),
        input_(type="hidden", name="action", value="preview"),
        div(class_="vstack gap-3")[tuple(stack)],
    ]


@register_page("core/campaign/campaign_copy_from.html")
def campaign_copy_from(context: dict[str, Any]) -> Page:
    campaign = context["campaign"]
    show_confirmation = context.get("show_confirmation")

    if show_confirmation:
        body = _confirmation(context)
    else:
        body = _selection_form(context)

    content: Node = fragment[
        back_link(
            context,
            url=campaign.get_absolute_url(),
            text="Back to Campaign",
        ),
        div(class_="col-12 col-md-8 col-lg-6 px-0 vstack gap-4")[
            div[
                h1(class_="h3 mb-2")["Copy from another Campaign"],
                h3(class_="mb-2 text-secondary")[campaign.name],
                p(class_="text-secondary mb-0")[
                    "Copy asset types, assets, resource types, attribute types, and custom content packs to ",
                    strong[campaign.name],
                    ".",
                ],
            ],
            body,
        ],
    ]
    return Page(
        title=f"Copy Content From Another Campaign - {campaign.name}",
        content=content,
    )
