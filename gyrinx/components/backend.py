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
from django.test.signals import template_rendered
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
        self.name = getattr(component, "template_name", "<component>")
        self.origin = _Origin(self.name)

    def render(self, context: dict[str, Any] | None = None, request: Any = None) -> str:
        ctx: dict[str, Any] = dict(context or {})
        if request is not None:
            ctx["request"] = request
            for processor in self.backend.context_processors:
                ctx.update(processor(request))
        # Fire the page's template_rendered signal BEFORE running the component,
        # so that under the test client `response.context`/`response.templates`
        # reflect the PAGE's context and name. A component may bridge legacy
        # partials via render_to_string(); those fire their own signals while it
        # runs, and firing ours first keeps the page context first in the
        # ContextList (so response.context["form"] etc. resolve to the page's
        # values, not a nested include's). No receivers in production — a no-op.
        template_rendered.send(sender=self, template=self, context=ctx)
        page = coerce_page(self.component(ctx), ctx)
        return render_page(page, ctx)


class _Origin:
    """Minimal template Origin, used for error messages / debug toolbars."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.template_name = name
        self.loader_name = "gyrinx.components"
