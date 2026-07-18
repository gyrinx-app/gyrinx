"""Edit gang skill trees form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, i, input_, label, noscript, p
from ._shared import cancel_link


@register_page("core/list_skill_trees_edit.html")
def edit_list_skill_trees(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]
    include_restricted = context["include_restricted"]
    return_url = context["return_url"]
    request = context["request"]

    list_url = reverse("core:list", args=[lst.id])
    cancel_url = return_url if return_url else list_url
    tree_count = lst.content_house.gang_skill_tree_count
    non_field_errors = form_obj.non_field_errors()

    # Un-ported {% include "core/includes/list_common_header.html" %}: bridge it
    # through the DjangoTemplates loader with the same ``with`` overrides.
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    get_form = form(method="get", class_="mb-3")[
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None,
        div(class_="form-check form-switch")[
            input_(
                class_="form-check-input",
                type="checkbox",
                role="switch",
                id="include_restricted",
                name="include_restricted",
                value="1",
                checked=bool(include_restricted),
                onchange="this.form.submit()",
            ),
            label(class_="form-check-label", for_="include_restricted")[
                "Show restricted skill trees"
            ],
        ],
        noscript[
            button(type="submit", class_="btn btn-secondary btn-sm mt-1")["Apply"]
        ],
    ]

    post_form = form(method="post")[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url)
        if return_url
        else None,
        div(class_="alert alert-danger alert-icon mb-3", role="alert")[
            i(class_="bi-exclamation-triangle"),
            div[raw(str(non_field_errors))],
        ]
        if non_field_errors
        else None,
        tuple(
            div(class_="mb-3")[
                label(for_=field.id_for_label, class_="form-label")[field.label],
                raw(str(field)),
                div(class_="text-danger fs-7")[raw(str(field.errors))]
                if field.errors
                else None,
            ]
            for field in form_obj.slot_fields
        ),
        div(class_="hstack gap-2")[
            button(type="submit", class_="btn btn-success btn-sm")[
                i(class_="bi-check-lg"), " Save"
            ],
            cancel_link(context, url=cancel_url),
        ],
    ]

    content: Node = fragment[
        header,
        div(class_="row g-3 mb-3")[
            div(class_="col-12 col-xl-6")[
                h1(class_="h3")["Gang skill trees"],
                p(class_="text-secondary")[
                    f"Pick and rank {tree_count} skill trees for your "
                    "gang. Fighters gain these as primary or secondary skills based on "
                    "their rank. You can leave trees unset and finish later."
                ],
                get_form,
                post_form,
            ]
        ],
    ]

    return Page(
        title=f"Edit gang skill trees - {lst.name}",
        content=content,
    )
