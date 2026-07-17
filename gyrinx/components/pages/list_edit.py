"""Edit-list (edit gang) form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, h2, i, input_, p
from ._shared import cancel_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/list_edit.html")
def list_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = form_obj.instance
    request = context["request"]
    return_url = context.get("return_url", "")

    # The gang header is a large shared partial with no component port yet;
    # delegate to the legacy include (byte-identical output) the way the bridge
    # delegates other battle-tested template tags.
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    edit_form = form(
        action=reverse("core:list-edit", args=[lst.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        input_(type="hidden", name="return_url", value=return_url),
        raw(str(form_obj.media)),
        raw(str(form_obj)),
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            cancel_link(context),
        ],
    ]

    content_packs = div(class_="border-top pt-3 mt-2")[
        h2(class_="h5")["Content Packs"],
        p(class_="text-secondary fs-7")[
            "Content packs add custom fighters, rules, and other content to your list."
        ],
        a(
            href=reverse("core:list-packs", args=[lst.id]),
            class_="btn btn-secondary btn-sm",
        )[i(class_="bi-box-seam"), " Manage Content Packs"],
    ]

    skill_trees: Node = None
    if lst.content_house.gang_wide_skills:
        skill_trees = div(class_="border-top pt-3 mt-2")[
            h2(class_="h5")["Skill trees"],
            p(class_="text-secondary fs-7")[
                "Pick and rank the skill trees your gang's fighters draw their "
                "primary and secondary skills from, by rank."
            ],
            a(
                href=reverse("core:list-skill-trees-manage", args=[lst.id]),
                class_="btn btn-secondary btn-sm",
            )[i(class_="bi-diagram-3"), " Manage skill trees"],
        ]

    content: Node = fragment[
        header,
        PageShell(
            h1(class_="h3")["Edit gang"],
            edit_form,
            content_packs,
            skill_trees,
            kind=FORM_SHELL,
        ),
    ]
    return Page(title=str(lst.name), content=content)
