"""New-list content-pack selection interstitial page component."""

from __future__ import annotations

from typing import Any

from django.template.defaultfilters import join, striptags, truncatewords, urlencode
from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, hr, i, input_, label, span


def _content_preview(parts: list[Any]) -> list[Node]:
    """Port of the ``pack.content_preview`` loop (names, ``, …`` suffix, ``·``)."""
    children: list[Node] = []
    last = len(parts) - 1
    for index, part in enumerate(parts):
        span_children: list[Node] = [join(part["names"], ", "), " "]
        if part["suffix"]:
            span_children.append(", …")
        children.append(span[tuple(span_children)])
        if index != last:
            children.append(span(class_="mx-1")["·"])
    return children


def _pack_item(pack: Any, preselected_pack_ids: Any) -> Node:
    return label(class_="border rounded p-2 d-flex align-items-start gap-2 pack-item")[
        input_(
            type="checkbox",
            name="pack_ids",
            value=str(pack.id),
            class_="form-check-input mt-1",
            checked=str(pack.id) in preselected_pack_ids,
        ),
        div(class_="flex-grow-1 overflow-hidden")[
            div[
                span(class_="fw-medium")[pack.name],
                span(class_="text-secondary")["· ", pack.owner],
            ],
            div(class_="text-secondary mt-1")[
                truncatewords(striptags(pack.summary), 20)
            ]
            if pack.summary
            else None,
            div(class_="text-secondary fs-7 mt-1 text-truncate")[
                tuple(_content_preview(pack.content_preview))
            ]
            if pack.content_preview
            else None,
        ],
    ]


@register_page("core/list_new_packs.html")
def list_new_packs(context: dict[str, Any]) -> Page:
    request = context["request"]
    name = context.get("name")
    available_packs = context.get("available_packs") or []
    preselected_pack_ids = context.get("preselected_pack_ids") or set()

    packs_new_url = reverse("core:lists-new-packs")

    # {% include breadcrumb.html ... only %} — rendered in isolation (no context
    # processors), matching the ``only`` keyword on the legacy include.
    breadcrumb = raw(
        render_to_string(
            "core/includes/breadcrumb.html",
            {
                "type": "Lists",
                "owner": request.user,
                "name": "New",
                "type_url": reverse("core:lists"),
            },
        )
    )

    # {% include packs_filter.html with action=action name=name %} — inherits the
    # page's request/user, bridged through the Django loader.
    packs_filter = raw(
        render_to_string(
            "core/includes/packs_filter.html",
            {"action": packs_new_url, "name": name},
            request=request,
        )
    )

    default_href = reverse("core:lists-new") + "?skip_packs=1"
    if name:
        default_href += "&name=" + urlencode(name)

    if available_packs:
        pack_nodes: list[Node] = [
            _pack_item(pack, preselected_pack_ids) for pack in available_packs
        ]
    else:
        pack_nodes = [div(class_="text-secondary fs-7")["No content packs found."]]

    content: Node = fragment[
        breadcrumb,
        div(class_="col-12 col-xl-8 px-0 vstack gap-3")[
            h1(class_="h3")["Add Content Packs?"],
            raw("<!-- Default game content -->"),
            div(class_="border rounded p-3")[
                div(class_="d-flex align-items-center gap-3")[
                    i(class_="bi-book fs-5"),
                    div[
                        div(class_="fw-medium")["Default Game Content"],
                        div(class_="text-secondary fs-7")[
                            "Standard fighters, equipment, and rules from the core rulebooks."
                        ],
                    ],
                    a(href=default_href, class_="btn btn-primary ms-auto")[
                        "Use default content ",
                        i(class_="bi-arrow-right"),
                    ],
                ],
            ],
            raw("<!-- Separator -->"),
            div(class_="d-flex align-items-center gap-3")[
                hr(class_="flex-grow-1"),
                span(class_="text-secondary fs-7")["Optionally add content packs"],
                hr(class_="flex-grow-1"),
            ],
            raw("<!-- Filter bar + Submit button -->"),
            div(class_="vstack gap-3")[
                packs_filter,
                button(
                    type="submit",
                    form="pack-form",
                    class_="btn btn-primary align-self-end flex-shrink-0",
                    id="include-packs-btn",
                    disabled=True,
                )[
                    "Include selected packs ",
                    i(class_="bi-arrow-right"),
                ],
            ],
            raw("<!-- Pack list (form wraps only the checkboxes) -->"),
            form(method="post", action=packs_new_url, id="pack-form")[
                CsrfInput(request),
                input_(type="hidden", name="name", value=name) if name else None,
                div(class_="vstack gap-2", id="pack-list")[tuple(pack_nodes)],
            ],
        ],
    ]

    return Page(title="Add Content Packs?", content=content)
