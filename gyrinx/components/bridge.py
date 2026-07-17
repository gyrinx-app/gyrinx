"""Bridges to existing Django template tags / filters.

Rather than reimplement battle-tested helpers (rich-text sanitising, house
icons, badges, credit formatting, nav-active logic), components call through to
the real functions. Keeping these in one module means the coupling to the
template-tag layer is explicit and easy to retarget.
"""

from __future__ import annotations

from typing import Any

from django.urls import Resolver404, resolve

from .elements import Node, raw

__all__ = [
    "active_view",
    "active_path",
    "active_aria",
    "active_flatpage",
    "active_flatpage_aria",
    "safe_referer",
    "safe_rich_text",
    "credits",
    "user_badge",
    "house_icon",
    "badge_icon",
    "get_page_by_url",
    "root_pages",
]


def _view_name(request: Any) -> str | None:
    try:
        return resolve(request.path).view_name
    except (Resolver404, AttributeError):
        return None


def active_view(request: Any, name: str) -> str:
    """``"active"`` when the current resolved view name equals ``name``."""
    return "active" if _view_name(request) == name else ""


def active_aria(request: Any, name: str) -> Node:
    """``aria-current="page"`` attribute-safe marker for the active nav item.

    Returns a dict suitable for splatting into an element's attributes."""
    return {"aria-current": "page"} if _view_name(request) == name else {}


def active_path(request: Any, *prefixes: str) -> str:
    """``"active"`` when the request path starts with any of ``prefixes``."""
    try:
        path = request.path
    except AttributeError:
        return ""
    return "active" if any(path.startswith(p) for p in prefixes) else ""


def active_flatpage(request: Any, url: str) -> str:
    from gyrinx.pages.templatetags.pages import _is_flatpage_active

    return "active" if _is_flatpage_active({"request": request}, url) else ""


def active_flatpage_aria(request: Any, url: str) -> dict:
    """``aria-current="page"`` attribute dict when the flatpage is active."""
    from gyrinx.pages.templatetags.pages import _is_flatpage_active

    return (
        {"aria-current": "page"}
        if _is_flatpage_active({"request": request}, url)
        else {}
    )


def safe_referer(request: Any, fallback: str = "/") -> str:
    """Return the request referer if it is same-host, else ``fallback``.

    Open-redirect guard mirroring the ``{% safe_referer %}`` tag."""
    from django.utils.http import url_has_allowed_host_and_scheme

    try:
        referer = request.META.get("HTTP_REFERER")
        host = request.get_host()
        secure = request.is_secure()
    except AttributeError:
        return fallback
    if referer and url_has_allowed_host_and_scheme(
        referer, allowed_hosts={host}, require_https=secure
    ):
        return referer
    return fallback


def safe_rich_text(value: Any) -> Node:
    """Sanitise TinyMCE rich text via the project's bleach allowlist. Returns a
    safe HTML node (already escaped where needed)."""
    from gyrinx.core.templatetags.custom_tags import safe_rich_text as _srt

    return raw(str(_srt(value)))


def credits(value: Any, *, show_sign: bool = False) -> str:
    """Format a cost integer with the credits symbol (¢)."""
    from gyrinx.models import format_cost_display

    return format_cost_display(value, show_sign=show_sign)


def user_badge(user: Any, *, extra_classes: str = "") -> Node:
    from gyrinx.core.templatetags.badge_tags import user_badge as _ub

    return raw(str(_ub(user, extra_classes)))


def badge_icon(badge: Any, *, extra_classes: str = "") -> Node:
    from gyrinx.core.templatetags.badge_tags import badge_icon as _bi

    return raw(str(_bi(badge, extra_classes)))


def house_icon(house: Any, *, extra_classes: str = "") -> Node:
    from gyrinx.core.templatetags.color_tags import house_icon as _hi

    return raw(str(_hi(house, extra_classes)))


def get_page_by_url(url: str) -> Any:
    from gyrinx.pages.templatetags.pages import get_page_by_url as _gp

    return _gp(url)


def root_pages(user: Any, request: Any = None) -> list[Any]:
    """Top-level visible flatpages for ``user`` (footer help links).

    Reuses the flatpages tag's ``FlatpageNode`` so site + visibility filtering
    matches ``{% get_root_pages for user as flatpages %}`` exactly."""
    from django.template import Context

    from gyrinx.pages.templatetags.pages import FlatpageNode

    node = FlatpageNode("_pages", user=None)
    node.depth = 1
    node.user = _LiteralVar(user)  # FlatpageNode resolves self.user as a Variable
    data: dict[str, Any] = {"user": user}
    if request is not None:
        data["request"] = request
    ctx = Context(data)
    node.render(ctx)
    return list(ctx["_pages"])


class _LiteralVar:
    """Minimal stand-in for a template ``Variable`` that resolves to a constant."""

    def __init__(self, value: Any) -> None:
        self._value = value

    def resolve(self, context: Any) -> Any:  # noqa: D401 - Variable protocol
        return self._value
