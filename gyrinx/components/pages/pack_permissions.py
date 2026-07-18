"""Pack editor-permissions management page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import button, div, form, h1, h2, input_, label, li, p, span, ul
from ._shared import back_link

SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-4"


@register_page("core/pack/pack_permissions.html")
def pack_permissions(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    editors = context["editors"]
    error = context["error"]
    request = context["request"]

    action_url = reverse("core:pack-permissions", args=[pack.id])

    add_form = form(action=action_url, method="post", class_="vstack gap-2")[
        CsrfInput(request),
        input_(type="hidden", name="action", value="add"),
        label(for_="username", class_="form-label fw-semibold")["Add an editor"],
        div(class_="input-group")[
            input_(
                type="text",
                name="username",
                id="username",
                class_="form-control",
                placeholder="Username",
                autocomplete="off",
            ),
            button(type="submit", class_="btn btn-success btn-sm")["Add"],
        ],
        div(class_="text-danger fs-7")[error] if error else None,
    ]

    if editors:
        editors_body: Node = ul(class_="list-unstyled mb-0")[
            tuple(
                li(
                    class_="py-2 d-flex justify-content-between align-items-center border-bottom"
                )[
                    span[perm.user.username],
                    form(action=action_url, method="post", class_="d-inline")[
                        CsrfInput(request),
                        input_(type="hidden", name="action", value="remove"),
                        input_(type="hidden", name="permission_id", value=perm.id),
                        button(type="submit", class_="btn btn-sm btn-outline-danger")[
                            "Remove"
                        ],
                    ],
                ]
                for perm in editors
            )
        ]
    else:
        editors_body = p(class_="text-secondary mb-0")["No editors yet."]

    content: Node = fragment[
        back_link(context, url=pack.get_absolute_url(), text="Back"),
        PageShell(
            h1(class_="h3")["Permissions"],
            p(class_="text-secondary mb-0")[
                "Editors can add, edit, and archive items in this Content Pack. "
                "They cannot change the listed status or manage permissions."
            ],
            raw("<!-- Add editor -->"),
            add_form,
            raw("<!-- Current editors -->"),
            div[
                h2(class_="h5")["Editors"],
                editors_body,
            ],
            kind=SHELL,
        ),
    ]
    return Page(title=f"Permissions — {pack.name}", content=content)
