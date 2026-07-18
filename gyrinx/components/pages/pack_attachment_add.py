"""Pack attachment (file) upload form page component."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, p
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/pack_attachment_add.html")
def pack_attachment_add(context: dict[str, Any]) -> Page:
    pack = context["pack"]
    form_obj = context["form"]
    request = context["request"]
    pack_full = context["pack_full"]
    attachment_count = context["attachment_count"]
    max_attachments = context["max_attachments"]

    pack_url = reverse("core:pack", args=[pack.id])

    if pack_full:
        tail: Node = fragment[
            div(class_="border rounded p-2")[
                "This pack already has the maximum of ",
                max_attachments,
                " files. Remove one before adding another.",
            ],
            div[a(href=pack_url, class_="btn btn-secondary btn-sm")["Back to pack"],],
        ]
    else:
        tail = form(
            method="post", enctype="multipart/form-data", class_="vstack gap-3"
        )[
            CsrfInput(request),
            raw(str(form_obj)),
            div(class_="mt-3")[
                button(type="submit", class_="btn btn-success")["Add file"],
                a(href=pack_url, class_="btn btn-link")["Cancel"],
            ],
        ]

    content: Node = fragment[
        back_link(context, url=pack_url, text=pack.name),
        PageShell(
            h1(class_="h3")["Add a file"],
            p(class_="text-secondary mb-0")[
                "Attach a scenario, campaign rules, or a reference sheet to share "
                "alongside this Content Pack. PDFs and images up to 20MB. ",
                attachment_count,
                " of ",
                max_attachments,
                " files used.",
            ],
            tail,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=f"Add a file - {pack.name}", content=content)
