"""Edit-weapon-profile form page component (pack editor)."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i, span
from ._shared import back_link

FORM_SHELL = "col-12 col-md-8 col-lg-6 px-0 vstack gap-3"


@register_page("core/pack/weapon_profile_edit.html")
def weapon_profile_edit(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    pack = context["pack"]
    equipment = context["equipment"]
    profile = context["profile"]
    back_url = context["back_url"]
    form_action_url = context["form_action_url"]
    customise_another_url = context.get("customise_another_url")
    delete_url = context.get("delete_url")
    request = context["request"]

    # The weapon-profile stat inputs partial isn't ported; bridge it through the
    # DjangoTemplates loader with the same ``with`` override the template passes.
    stats_form = raw(
        render_to_string(
            "core/pack/includes/weapon_profile_stats_form.html",
            {"weapon_stats": context["weapon_stat_values"]},
            request=request,
        )
    )

    head_children: list[Any] = [i(class_="bi-crosshair"), " Edit profile "]
    if profile.name:
        head_children += [": ", profile.name, " "]
    head_children += ["— ", equipment.name]

    actions: list[Node] = [
        button(type="submit", class_="btn btn-success")["Save"],
    ]
    if customise_another_url:
        actions += [
            span["or"],
            button(
                type="submit",
                name="save_and_customise_another",
                class_="btn btn-secondary",
            )["Save and customise a different weapon"],
        ]
    actions.append(a(href=back_url, class_="btn btn-link")["Cancel"])
    if profile.name:
        actions.append(
            a(href=delete_url, class_="btn btn-link text-danger ms-auto")[
                "Archive profile"
            ]
        )

    body = form(action=form_action_url, method="post", class_="vstack gap-3")[
        CsrfInput(request),
        raw(str(form_obj)),
        stats_form,
        div(class_="mt-3 d-flex align-items-center gap-2 flex-wrap")[actions],
    ]

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")[head_children],
            body,
            kind=FORM_SHELL,
        ),
    ]
    return Page(
        title=f"Edit profile - {equipment.name} - {pack.name}",
        content=content,
    )
