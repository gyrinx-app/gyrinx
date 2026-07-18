"""List-fighter edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


def _field(field: Any) -> Node:
    """Port of the template's inline field markup (label / widget / help / errors).

    Note this differs from the shared ``FormField`` component: the help text is a
    ``div.form-text`` (not ``small``) and each error gets its own div."""
    children: list[Any] = [field.label_tag(), raw(str(field))]
    if field.help_text:
        children.append(div(class_="form-text")[field.help_text])
    children.extend(
        div(class_="invalid-feedback d-block")[error] for error in field.errors
    )
    return div[tuple(children)]


@register_page("core/list_fighter_edit.html")
def list_fighter_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    lst = context["list"]
    fighter = form_obj.instance
    request = context["request"]

    # The gang/fighter header is a large shared partial with no component port
    # yet; delegate to the legacy include (byte-identical output) with the same
    # ``with`` overrides the template passes.
    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {
                **context,
                "list": lst,
                "link_list": "true",
                "fighter": fighter,
                "fighter_url_name": "core:list-fighter-edit",
            },
            request=request,
        )
    )

    fields: list[Any] = [
        _field(form_obj["name"]),
        _field(form_obj["content_fighter"]),
    ]
    if fighter.content_fighter.can_take_legacy:
        fields.append(_field(form_obj["legacy_content_fighter"]))
    fields.append(_field(form_obj["category_override"]))
    fields.append(_field(form_obj["cost_override"]))

    body = form(
        action=reverse("core:list-fighter-edit", args=[lst.id, fighter.id]),
        method="post",
        class_="vstack gap-3",
    )[
        CsrfInput(request),
        tuple(fields),
        div[
            a(
                href=reverse("core:list-fighter-stats-edit", args=[lst.id, fighter.id]),
                class_="icon-link link-primary",
            )[
                i(class_="bi-pencil-square"),
                " Edit ",
                fighter.term_singular,
                " Stats",
            ],
            div(class_="form-text")[
                "Customize ",
                fighter.proximal_demonstrative.lower(),
                "'s stat values (Movement, Weapon Skill, etc.)",
            ],
        ],
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=reverse("core:list", args=[lst.id]), class_="btn btn-link")[
                "Cancel"
            ],
        ],
    ]

    content: Node = fragment[
        header,
        PageShell(
            h1(class_="h3")[
                "Edit: ",
                fighter.name,
                " - ",
                fighter.content_fighter.name(),
            ],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=(
            f"Edit - {fighter.name} - {fighter.content_fighter.name()} - {lst.name}"
        ),
        content=content,
    )
