"""A Django template backend that renders registered page components.

Listed FIRST in ``settings.TEMPLATES``, it claims only the template names that
have a registered page component and raises ``TemplateDoesNotExist`` for
everything else — so unconverted pages and third-party templates fall through to
the ``DjangoTemplates`` backend. This is what makes the migration incremental
and keeps views unchanged (``render(request, name, context)`` just works).
"""

from __future__ import annotations

from typing import Any

from django.template import TemplateDoesNotExist
from django.template.backends.base import BaseEngine
from django.utils.module_loading import import_string

from .layout import render_page
from .registry import coerce_page, resolve_page

__all__ = ["Components", "ComponentTemplate"]


class Components(BaseEngine):
    """Template backend for Gyrinx page components."""

    app_dirname = "components"  # unused (no on-disk templates), required attr

    def __init__(self, params: dict[str, Any]) -> None:
        params = params.copy()
        options = params.pop("OPTIONS", {}).copy()
        context_processor_paths = options.pop("context_processors", [])
        super().__init__(params)
        self._context_processor_paths = list(context_processor_paths)
        self._context_processors: list[Any] | None = None

    @property
    def context_processors(self) -> list[Any]:
        if self._context_processors is None:
            self._context_processors = [
                import_string(path) for path in self._context_processor_paths
            ]
        return self._context_processors

    def from_string(
        self, template_code: str
    ) -> Any:  # pragma: no cover - not supported
        raise NotImplementedError(
            "The components backend renders registered components, not strings."
        )

    def get_template(self, template_name: str) -> "ComponentTemplate":
        component = resolve_page(template_name)
        if component is None:
            raise TemplateDoesNotExist(template_name, backend=self)
        return ComponentTemplate(component, self)


class ComponentTemplate:
    """Wraps a page component to satisfy Django's template interface."""

    def __init__(self, component: Any, backend: Components) -> None:
        self.component = component
        self.backend = backend
        self.origin = _Origin(getattr(component, "template_name", "<component>"))

    def render(self, context: dict[str, Any] | None = None, request: Any = None) -> str:
        ctx: dict[str, Any] = dict(context or {})
        if request is not None:
            ctx["request"] = request
            for processor in self.backend.context_processors:
                ctx.update(processor(request))
        page = coerce_page(self.component(ctx), ctx)
        return render_page(page, ctx)


class _Origin:
    """Minimal template Origin, used for error messages / debug toolbars."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.template_name = name
        self.loader_name = "gyrinx.components"
