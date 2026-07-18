"""Pack gear/weapon "Modifiers" tab edit form page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput, PageShell
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h1, i
from ._shared import back_link


@register_page("core/pack/pack_item_modifiers.html")
def pack_item_modifiers(context: dict[str, Any]) -> Page:
    form_obj = context["form"]
    pack = context["pack"]
    pack_item = context["pack_item"]
    content_obj = context["content_obj"]
    label = context["label"]
    icon = context["icon"]
    back_url = context["back_url"]
    request = context["request"]

    # {{ form.non_field_errors }} then the hidden fields, then the two
    # un-ported {% include %} partials (the fighter-mod picker and its shared
    # styles/JS), bridged through the DjangoTemplates loader.
    form_children: list[Node] = [
        CsrfInput(request),
        raw(str(form_obj.non_field_errors())),
    ]
    form_children.extend(raw(str(field)) for field in form_obj.hidden_fields())
    form_children.append(
        raw(
            render_to_string(
                "core/pack/includes/_equipment_mods_picker.html",
                {"form": form_obj},
                request=request,
            )
        )
    )
    form_children.append(
        raw(
            render_to_string(
                "core/pack/includes/_mod_picker_shared.html",
                {},
                request=request,
            )
        )
    )
    form_children.append(
        div(class_="mt-3")[
            button(type="submit", class_="btn btn-success")["Save"],
            a(href=back_url, class_="btn btn-link")["Cancel"],
        ]
    )

    body = form(
        action=reverse("core:pack-item-modifiers", args=[pack.id, pack_item.id]),
        method="post",
        class_="vstack gap-3",
    )[tuple(form_children)]

    tabs = raw(
        render_to_string(
            "core/pack/includes/pack_item_edit_tabs_equipment.html",
            {"pack": pack, "pack_item": pack_item, "active_tab": "modifiers"},
            request=request,
        )
    )

    content: Node = fragment[
        back_link(context, url=back_url, text=pack.name),
        PageShell(
            h1(class_="h3")[i(class_=icon), " Edit ", label],
            tabs,
            body,
            kind="form",
        ),
    ]
    return Page(
        title=f"Modifiers for {content_obj} - {pack.name}",
        content=content,
    )
