"""Fighter narrative (Lore) edit page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, img, input_, label

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _list_common_header(request: Any, lst: Any, fighter: Any) -> Node:
    """Port of the ``list_common_header.html`` include.

    The include has no component equivalent yet, so render it through the legacy
    loader (it is not registered with the component backend, so it falls through
    to DjangoTemplates) with the same ``with`` overrides the template passes."""
    return raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {
                "list": lst,
                "link_list": "true",
                "fighter": fighter,
                "fighter_url_name": "core:list-fighter-narrative-edit",
            },
            request=request,
        )
    )


def _field_errors(field: Any) -> Node:
    if not field.errors:
        return None
    return div(class_="invalid-feedback d-block")[
        tuple(str(error) for error in field.errors)
    ]


@register_page("core/list_fighter_narrative_edit.html")
def list_fighter_narrative_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = context["fighter"]
    request = context["request"]
    return_url = context.get("return_url")
    instance = form_obj.instance

    image_field = form_obj["image"]
    narrative_field = form_obj["narrative"]

    image_block = div(class_="mb-3")[
        label(for_=image_field.id_for_label, class_="form-label")[image_field.label],
        div(class_="d-flex flex-column flex-md-row gap-2")[
            div(class_="mb-2 me-2 flex-shrink-0")[
                img(
                    src=fighter.image.url if fighter.image else None,
                    alt=fighter.name,
                    class_="size-em-4 size-em-md-5 img-thumbnail",
                )
            ]
            if fighter.image
            else None,
            div(class_="flex-grow-1")[
                raw(str(image_field)),
                div(class_="form-text")[image_field.help_text]
                if image_field.help_text
                else None,
            ],
        ],
        _field_errors(image_field),
    ]

    narrative_block = div(class_="mb-3")[
        label(for_=narrative_field.id_for_label, class_="form-label")[
            narrative_field.label
        ],
        raw(str(narrative_field)),
        div(class_="form-text")[narrative_field.help_text]
        if narrative_field.help_text
        else None,
        _field_errors(narrative_field),
    ]

    body = form(
        action=reverse("core:list-fighter-narrative-edit", args=[lst.id, instance.id]),
        method="post",
        enctype="multipart/form-data",
    )[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url or ""),
        raw(str(form_obj.media)),
        image_block,
        narrative_block,
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=return_url, class_="btn btn-link")["Cancel"],
        ],
    ]

    content = fragment[
        _list_common_header(request, lst, instance),
        PageShell(
            h1(class_="h3")[
                f"Lore: {instance.name} - {instance.content_fighter.name()}"
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Lore - {instance.name} - {instance.content_fighter.name()} - {lst.name}"
        ),
        content=content,
    )
