"""Shared helpers for page components (back/cancel links resolved from context)."""

from __future__ import annotations

from typing import Any

from .. import bridge
from ..design import BackLink
from ..elements import Node
from ..tags import a


def resolve_back_url(context: dict[str, Any], url: str | None = None) -> str:
    """Resolve a back/cancel target the way ``back.html`` / ``cancel.html`` do:
    explicit ``url`` → ``return_url`` in context → same-host referer → ``/``."""
    if url:
        return url
    if context.get("return_url"):
        return context["return_url"]
    request = context.get("request")
    if request is not None:
        return bridge.safe_referer(request, "/")
    return "/"


def back_link(
    context: dict[str, Any], *, url: str | None = None, text: Any = "Back"
) -> Node:
    """A breadcrumb back link (port of ``core/includes/back.html``)."""
    return BackLink(url=resolve_back_url(context, url), text=text)


def cancel_link(
    context: dict[str, Any], *, url: str | None = None, text: Any = "Cancel"
) -> Node:
    """A ``btn btn-link`` cancel link (port of ``core/includes/cancel.html``)."""
    return a(href=resolve_back_url(context, url), class_="btn btn-link")[text]
