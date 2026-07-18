"""Registry mapping template names to page components.

A *page component* is a callable ``fn(context) -> Page | Node`` registered under
the template name a view already renders::

    @register_page("core/index.html")
    def index_page(context):
        return Page(title="...", content=...)

The :mod:`gyrinx.components.backend` template backend resolves these names, so
views keep calling ``render(request, "core/index.html", context)`` unchanged.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Callable

from .layout import Page

__all__ = ["register_page", "resolve_page", "registered_names", "autodiscover"]

_REGISTRY: dict[str, Callable[[dict[str, Any]], Any]] = {}
_DISCOVERED = False


def register_page(name: str) -> Callable[[Callable], Callable]:
    """Register a page component under a template ``name``."""

    def decorator(fn: Callable[[dict[str, Any]], Any]) -> Callable:
        _REGISTRY[name] = fn
        fn.template_name = name  # type: ignore[attr-defined]
        return fn

    return decorator


def autodiscover() -> None:
    """Import every module under ``gyrinx.components.pages`` so registrations run.

    Idempotent; safe to call repeatedly (e.g. from the backend on first lookup)."""
    global _DISCOVERED
    if _DISCOVERED:
        return
    try:
        pages_pkg = importlib.import_module("gyrinx.components.pages")
    except ModuleNotFoundError:
        _DISCOVERED = True
        return
    for module_info in pkgutil.walk_packages(
        pages_pkg.__path__, prefix=pages_pkg.__name__ + "."
    ):
        importlib.import_module(module_info.name)
    # Only publish completion once every page module has imported successfully:
    # setting the flag up-front would let a failed import (or a concurrent
    # caller mid-walk) leave a partially-populated registry looking complete,
    # silently falling every unregistered page back to DjangoTemplates.
    _DISCOVERED = True


def resolve_page(name: str) -> Callable[[dict[str, Any]], Any] | None:
    """Return the page component registered under ``name``, or ``None``."""
    if not _DISCOVERED:
        autodiscover()
    return _REGISTRY.get(name)


def registered_names() -> list[str]:
    if not _DISCOVERED:
        autodiscover()
    return sorted(_REGISTRY)


def coerce_page(result: Any, context: dict[str, Any]) -> Page:
    """Normalise a component's return value to a :class:`Page`."""
    if isinstance(result, Page):
        return result
    return Page(content=result, title=context.get("head_title", ""))
