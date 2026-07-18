"""Bulk post-battle updates editor page component."""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, fragment, raw
from ..layout import Page
from ..registry import register_page
from ..tags import (
    button,
    details,
    div,
    form,
    h1,
    i,
    label,
    p,
    script,
    span,
    summary,
)
from ._shared import cancel_link

_PB_SCRIPT = """
 (function () {
     function initEditor(ta) {
         if (!window.tinymce || ta.dataset.pbInit) return;
         ta.dataset.pbInit = "1";
         var dark = document.documentElement.getAttribute("data-bs-theme") === "dark";
         window.tinymce.init({
             target: ta,
             menubar: false,
             statusbar: false,
             plugins: "lists link autolink autoresize",
             toolbar: "bold italic underline | bullist numlist | link | removeformat",
             min_height: 180,
             branding: false,
             promotion: false,
             skin: dark ? "oxide-dark" : "oxide",
             content_css: dark ? "dark" : "default",
         });
     }
     document.querySelectorAll("details[data-pb-notes]").forEach(function (d) {
         d.addEventListener("toggle", function () {
             if (d.open) {
                 var ta = d.querySelector("textarea");
                 if (ta) initEditor(ta);
             }
         });
     });
     // Reason is only meaningful alongside an injury: keep it disabled
     // until one is chosen. Server-side validation is the source of
     // truth; this is just an affordance, so no-JS submits still work.
     document.querySelectorAll('select[name^="injury_"]').forEach(function (sel) {
         var reason = document.querySelector(
             '[name="' + sel.name.replace(/^injury_/, "injury_reason_") + '"]'
         );
         if (!reason) return;
         function sync() { reason.disabled = !sel.value; }
         sel.addEventListener("change", sync);
         sync();
     });
     var form = document.querySelector("form[data-pb-form]");
     if (form) {
         form.addEventListener("submit", function () {
             if (!window.tinymce) return;
             // Only write back editors the user actually edited. Merely
             // opening a fighter's notes mounts TinyMCE, which would
             // reserialise the HTML on a blanket triggerSave() and log a
             // spurious "notes changed" — so leave clean editors' textareas
             // holding their original server-rendered value.
             window.tinymce.get().forEach(function (ed) {
                 if (ed.isDirty()) ed.save();
             });
         });
     }
 })();
"""


def _field_errors(field: Any) -> list[Node]:
    return [div(class_="text-danger fs-7")[error] for error in field.errors]


def _fighter_row(row: dict[str, Any]) -> Node:
    fighter = row["fighter"]

    if fighter.is_dead:
        state_badge: Node = span(class_="badge text-bg-dark")["Dead"]
    elif not fighter.is_active:
        state_badge = span(class_="badge text-bg-secondary")[
            fighter.get_injury_state_display()
        ]
    else:
        state_badge = None

    xp_field = row["xp"]
    xp_col = div(class_="col-6 col-md-2")[
        label(class_="form-label fs-7 mb-1", for_=xp_field.id_for_label)[
            "Add XP",
            span(class_="text-secondary")[f"({fighter.xp_current})"],
        ],
        raw(str(xp_field)),
        _field_errors(xp_field),
    ]

    counter_cols = [
        div(class_="col-6 col-md-2")[
            label(class_="form-label fs-7 mb-1", for_=c["field"].id_for_label)[
                c["counter"].name,
                span(class_="text-secondary")[f"({c['value']})"],
            ],
            raw(str(c["field"])),
            _field_errors(c["field"]),
        ]
        for c in row["counters"]
    ]

    injury_field = row["injury"]
    injury_col = div(class_="col-12 col-md")[
        label(class_="form-label fs-7 mb-1", for_=injury_field.id_for_label)["Injury"],
        raw(str(injury_field)),
        _field_errors(injury_field),
    ]

    reason_field = row["injury_reason"]
    reason_col = div(class_="col-12 col-md")[
        label(class_="form-label fs-7 mb-1", for_=reason_field.id_for_label)["Reason"],
        raw(str(reason_field)),
        _field_errors(reason_field),
    ]

    return div(class_="py-3 border-bottom")[
        div(class_="d-flex flex-wrap align-items-baseline gap-2 mb-2")[
            span(class_="fw-semibold fs-5")[fighter.name],
            span(class_="text-secondary fw-normal")[fighter.get_category_label()],
            state_badge,
        ],
        div(class_="row g-2 g-md-3")[
            xp_col,
            counter_cols,
            injury_col,
            reason_col,
        ],
        details(class_="mt-2", data_pb_notes=True)[
            summary(class_="fs-7 linked")["Private notes"],
            div(class_="mt-2")[raw(str(row["private_notes"]))],
        ],
    ]


@register_page("core/list_post_battle_updates.html")
def post_battle_updates(context: dict[str, Any]) -> Page:
    lst = context["list"]
    form_obj = context["form"]
    rows = context["rows"]
    has_battles = context["has_battles"]
    request = context["request"]

    list_url = reverse("core:list", args=[lst.id])

    header = raw(
        render_to_string(
            "core/includes/list_common_header.html",
            {"list": lst, "link_list": "true"},
            request=request,
        )
    )

    if rows:
        non_field_errors = form_obj.non_field_errors()
        non_field_block: Node = (
            div(class_="alert alert-danger alert-icon", role="alert")[
                i(class_="bi-exclamation-triangle"),
                div[non_field_errors],
            ]
            if non_field_errors
            else None
        )

        battle_block: Node = None
        if has_battles:
            battle_field = form_obj["battle"]
            battle_block = div(class_="col-12 col-md-6 col-lg-4")[
                label(class_="form-label mb-1", for_=battle_field.id_for_label)[
                    battle_field.label,
                    span(class_="text-secondary fs-7")["(optional)"],
                ],
                raw(str(battle_field)),
                div(class_="form-text")[
                    "Actions logged below will be attached to this battle."
                ],
            ]

        form_body: Node = div(class_="vstack gap-4")[
            non_field_block,
            battle_block,
            div(class_="border-top")[[_fighter_row(row) for row in rows]],
            div(class_="d-flex gap-2")[
                button(type="submit", class_="btn btn-success")["Apply updates"],
                cancel_link(context, url=list_url, text="Cancel"),
            ],
        ]
    else:
        form_body = div(class_="border rounded p-2")[
            i(class_="bi-info-circle"),
            " This gang has no fighters to update.",
        ]

    outer = div(class_="col-12 px-0 vstack gap-3")[
        h1(class_="h3 mb-0")["Post-battle updates"],
        p(class_="text-secondary mb-0")[
            "Record what happened this battle across the whole gang. The action fields "
            "start blank and notes show what's already saved — only what you fill in or "
            "change is applied, nothing else is touched."
        ],
        form(method="post", data_pb_form=True)[
            CsrfInput(request),
            form_body,
        ],
    ]

    scripts: Node = (
        fragment[
            script(src=static("tinymce/tinymce.min.js")),
            script[raw(_PB_SCRIPT)],
        ]
        if rows
        else None
    )

    content: Node = fragment[header, outer, scripts]
    return Page(title=f"Post-battle updates - {lst.name}", content=content)
