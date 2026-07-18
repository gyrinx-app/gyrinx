"""Fighter advancement confirmation page component."""

from __future__ import annotations

from typing import Any

from django.http import QueryDict
from django.template.loader import render_to_string
from django.urls import reverse

from ..design import CsrfInput
from ..elements import Node, raw
from ..layout import Page
from ..registry import register_page
from ..tags import a, button, div, form, h3, i, nav, span


def _querystring(request: Any, **kwargs: Any) -> str:
    """Port of Django's built-in ``{% querystring %}`` tag: start from
    ``request.GET``, apply the keyword overrides (``None`` removes a key), and
    return the encoded string prefixed with ``?``."""
    params = QueryDict(mutable=True)
    for source in (request.GET, kwargs):
        items = source.lists() if isinstance(source, QueryDict) else source.items()
        for key, value in items:
            if value is None:
                params.pop(key, None)
            elif isinstance(value, (list, tuple)):
                params.setlist(key, [v for v in value if v is not None])
            else:
                params[key] = value
    query_string = params.urlencode() if params else ""
    return f"?{query_string}"


@register_page("core/list_fighter_advancement_confirm.html")
def list_fighter_advancement_confirm(context: dict[str, Any]) -> Page:
    fighter = context["fighter"]
    lst = context["list"]
    details = context["details"]
    request = context["request"]

    progress = raw(
        render_to_string(
            "core/includes/advancement_progress.html",
            {**context, "total_steps": context["steps"]},
            request=request,
        )
    )

    back_href = reverse(
        "core:list-fighter-advancement-type", args=[lst.id, fighter.id]
    ) + _querystring(request, campaign_action_id=details["campaign_action_id"])

    cost_increase = details.get("cost_increase") or "0"

    content: Node = div(class_="col-12 col-md-8 col-lg-6 vstack gap-4")[
        div(class_="vstack gap-1")[
            progress,
            h3(class_="h5 mb-0")["Confirm Advancement"],
        ],
        div[
            "Advance ",
            details["description"],
            " for ",
            span(class_="badge text-bg-primary")[f"{details['xp_cost']} XP"],
            f" (+{cost_increase}¢)?",
        ],
        nav(class_="hstack gap-3", aria_label="Form navigation")[
            a(href=back_href, class_="icon-link")[
                i(class_="bi-chevron-left"),
                " Back",
            ],
            form(
                method="post",
                class_="d-inline",
                aria_label="Confirm advancement form",
            )[
                CsrfInput(request),
                button(
                    type="submit",
                    class_="btn btn-success",
                    aria_describedby="confirm-final-help",
                )[
                    i(class_="bi-check-lg", aria_hidden="true"),
                    " Confirm Advancement",
                ],
            ],
            span(id="confirm-final-help", class_="visually-hidden")[
                "Confirm and apply the advancement to the fighter"
            ],
        ],
    ]

    return Page(
        title=f"Confirm Advancement - {fighter.name}",
        content=content,
    )
