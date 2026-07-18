"""Campaign asset edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, FormField, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, h3, i, p, span
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _sub_asset_sections(campaign: Any, asset: Any) -> list[Node]:
    """Port of the sub-asset schema loop in the legacy template."""
    schema = asset.asset_type.sub_asset_schema
    if not schema:
        return []

    sections: list[Node] = []
    for type_key, type_def in schema.items():
        label_singular = type_def.get("label", "")
        label_plural = type_def.get("label_plural") or label_singular

        header_children: list[Node] = [h3(class_="h5 mb-0")[label_plural]]
        if not campaign.archived:
            header_children.append(
                a(
                    href=reverse(
                        "core:campaign-sub-asset-new",
                        args=[campaign.id, asset.id, type_key],
                    ),
                    class_="icon-link linked fs-7",
                )[i(class_="bi-plus-lg"), " Add ", label_singular]
            )

        section_children: list[Node] = [
            div(class_="d-flex justify-content-between align-items-center mb-2")[
                tuple(header_children)
            ],
        ]

        if type_def.get("description"):
            section_children.append(
                p(class_="text-secondary fs-7")[type_def.get("description")]
            )

        for sub_asset in asset.sub_assets.all():
            if sub_asset.sub_asset_type != type_key:
                continue

            props = sub_asset.properties_with_labels
            info_children: list[Node] = [span(class_="fw-semibold")[sub_asset.name]]
            if props:
                prop_nodes: list[Node] = []
                for index, (prop_label, prop_value) in enumerate(props):
                    if index:
                        prop_nodes.append(" · ")
                    prop_nodes.append(f"{prop_label}: {prop_value}")
                info_children.append(
                    div(class_="fs-7 text-secondary")[tuple(prop_nodes)]
                )

            card_row_children: list[Node] = [div[tuple(info_children)]]
            if not campaign.archived:
                card_row_children.append(
                    div(class_="text-nowrap ms-2")[
                        a(
                            href=reverse(
                                "core:campaign-sub-asset-edit",
                                args=[campaign.id, asset.id, sub_asset.id],
                            ),
                            class_="linked-secondary fs-7",
                        )["Edit"],
                        a(
                            href=reverse(
                                "core:campaign-sub-asset-remove",
                                args=[campaign.id, asset.id, sub_asset.id],
                            ),
                            class_="link-danger link-underline-opacity-50 link-underline-opacity-100-hover fs-7 ms-2",
                        )["Remove"],
                    ]
                )

            section_children.append(
                div(class_="border rounded p-2 mb-2")[
                    div(class_="d-flex justify-content-between align-items-start")[
                        tuple(card_row_children)
                    ]
                ]
            )

        sections.append(div(class_="mt-4")[tuple(section_children)])

    return sections


@register_page("core/campaign/campaign_asset_edit.html")
def campaign_asset_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    campaign = context["campaign"]
    asset = context["asset"]
    request = context["request"]

    fields: list[Node] = [
        CsrfInput(request),
        FormField(form_obj["name"]),
        FormField(form_obj["description"]),
    ]
    if "holder" in form_obj.fields:
        fields.append(FormField(form_obj["holder"]))
    fields.append(
        raw(
            render_to_string(
                "core/campaign/includes/asset_properties_fields.html",
                {**context},
                request=request,
            )
        )
    )
    fields.extend(_sub_asset_sections(campaign, asset))
    fields.append(
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")[
                "Update ", asset.asset_type.name_singular
            ],
            a(
                href=reverse("core:campaign-assets", args=[campaign.id]),
                class_="btn btn-link",
            )["Cancel"],
        ]
    )

    body = form(
        action=reverse("core:campaign-asset-edit", args=[campaign.id, asset.id]),
        method="post",
        class_="vstack gap-3",
    )[fields]

    content: Node = fragment[
        raw(str(form_obj.media)),
        back_link(
            context,
            url=reverse("core:campaign-assets", args=[campaign.id]),
            text="Back to Assets",
        ),
        PageShell(
            h1(class_="h3")["Edit ", asset.asset_type.name_singular],
            h2(class_="h5 text-secondary")[asset.name],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Edit {asset.name}", content=content)
