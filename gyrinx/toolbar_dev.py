"""Memoise Django Debug Toolbar bookkeeping in development.

Cache frame entries per request and excluded-module list, template context
per template object, and rendered frame HTML in a bounded cache. Preserve
uncached stack capture when local variables are requested.

ToolbarDevConfig installs these wrappers during ready(). Validate the
expected toolbar API at startup so incompatible upgrades fail explicitly.
"""

import functools
import inspect
import linecache
import weakref

from debug_toolbar.apps import DebugToolbarConfig
from django.core.exceptions import ImproperlyConfigured

_MISSING = object()


def memoised_stack_trace_recorder(base):
    """Return a subclass of the toolbar's ``_StackTraceRecorder`` that memoises frames."""

    class MemoisedStackTraceRecorder(base):
        def __init__(self):
            super().__init__()
            # One frame cache per list of hidden modules, because whether a
            # frame is left out of the trace depends on that list.
            self.frame_caches = {}
            self.module_globals_cache = {}

        def get_stack_trace(
            self, *, excluded_modules=None, include_locals=False, skip=0
        ):
            from debug_toolbar.utils import _is_excluded_frame, _stack_frames

            if include_locals:
                # Locals differ on every call, so there is nothing to reuse.
                return super().get_stack_trace(
                    excluded_modules=excluded_modules,
                    include_locals=include_locals,
                    skip=skip + 1,
                )

            trace = []
            frame_cache = self.frame_caches.setdefault(
                tuple(excluded_modules or ()), {}
            )
            skip += 1  # Skip the frame for this method.
            for frame in _stack_frames(skip=skip):
                key = (frame.f_code, frame.f_lineno)
                entry = frame_cache.get(key, _MISSING)
                if entry is _MISSING:
                    if _is_excluded_frame(frame, excluded_modules):
                        entry = None
                    else:
                        entry = self.frame_entry(frame)
                    frame_cache[key] = entry
                if entry is not None:
                    trace.append(entry)
            trace.reverse()
            return trace

        def frame_entry(self, frame):
            filename, is_source = self.get_source_file(frame)
            line_no = frame.f_lineno
            if is_source:
                module_globals = self.module_globals_cache.get(filename, _MISSING)
                if module_globals is _MISSING:
                    module = inspect.getmodule(frame, filename)
                    module_globals = module.__dict__ if module is not None else None
                    self.module_globals_cache[filename] = module_globals
                source_line = linecache.getline(
                    filename, line_no, module_globals
                ).strip()
            else:
                source_line = ""
            return (filename, line_no, frame.f_code.co_name, source_line, None)

    return MemoisedStackTraceRecorder


def memoised_get_template_context(original):
    """Wrap the toolbar's ``get_template_context`` with a per-template cache."""
    cache = weakref.WeakKeyDictionary()

    # The toolbar spots re-entry by comparing frame names against this
    # function's __name__, so the wrapper keeps the original's name. The
    # original still runs on a cache miss, from its own module, as before.
    def get_template_context(node, context, context_lines=3):
        try:
            if context.template.origin == node.origin:
                template = context.template
            else:
                template = context.render_context.template
            per_template = cache.setdefault(template, {})
            key = (node.token.position, context_lines)
        except AttributeError, TypeError:
            return original(node, context, context_lines)

        info = per_template.get(key)
        if info is None:
            info = per_template[key] = original(node, context, context_lines)
        # Each caller gets its own copy, as it would from the original.
        return {
            "name": info["name"],
            "context": [dict(line) for line in info["context"]],
        }

    get_template_context.__wrapped__ = original
    return get_template_context


def memoised_render_stacktrace(original):
    """Wrap the toolbar's ``render_stacktrace`` so each frame's HTML is built once."""
    from debug_toolbar import settings as dt_settings
    from django.utils.safestring import SafeString

    @functools.lru_cache(maxsize=8192)
    def render_frame(frame):
        return original([frame])

    def render_stacktrace(trace):
        if dt_settings.get_config()["ENABLE_STACKTRACES_LOCALS"]:
            return original(trace)
        # Each frame comes back from the toolbar's own renderer already safe, and
        # safe strings stay safe when added together.
        html = SafeString()
        try:
            for frame in trace:
                html += render_frame(tuple(frame))
        except TypeError:  # An entry that cannot be hashed.
            return original(trace)
        return html

    render_stacktrace.__wrapped__ = original
    return render_stacktrace


def install():
    """Swap the memoised versions into ``debug_toolbar.utils``. Safe to call twice."""
    from debug_toolbar import utils
    from debug_toolbar.panels import cache
    from debug_toolbar.panels.sql import panel as sql_panel

    for module, name in (
        (utils, "_StackTraceRecorder"),
        (utils, "get_template_context"),
        (utils, "render_stacktrace"),
        (cache, "render_stacktrace"),
        (sql_panel, "render_stacktrace"),
    ):
        if not hasattr(module, name):
            raise ImproperlyConfigured(
                f"{module.__name__}.{name} is gone, so gyrinx/toolbar_dev.py "
                "can no longer speed up the toolbar. Update or remove it."
            )

    if not getattr(utils._StackTraceRecorder, "memoised", False):
        recorder = memoised_stack_trace_recorder(utils._StackTraceRecorder)
        recorder.memoised = True
        utils._StackTraceRecorder = recorder

    if not hasattr(utils.get_template_context, "__wrapped__"):
        utils.get_template_context = memoised_get_template_context(
            utils.get_template_context
        )

    # The panels import render_stacktrace by name, so each copy is replaced.
    if not hasattr(utils.render_stacktrace, "__wrapped__"):
        utils.render_stacktrace = memoised_render_stacktrace(utils.render_stacktrace)
    cache.render_stacktrace = utils.render_stacktrace
    sql_panel.render_stacktrace = utils.render_stacktrace


class ToolbarDevConfig(DebugToolbarConfig):
    """The toolbar's own app config, with the memoised bookkeeping swapped in."""

    def ready(self):
        super().ready()
        install()
