"""The debug toolbar's memoised bookkeeping matches what the toolbar records itself."""

from debug_toolbar import utils as toolbar_utils
from debug_toolbar.settings import CONFIG_DEFAULTS
from django.apps import apps
from django.template import Context, Engine

from gyrinx.toolbar_dev import install

HIDDEN = CONFIG_DEFAULTS["HIDE_IN_STACKTRACES"]


def toolbar_originals():
    recorder = toolbar_utils._StackTraceRecorder
    return recorder.__mro__[1], toolbar_utils.get_template_context.__wrapped__


def test_the_toolbar_is_installed_with_the_speed_ups():
    assert apps.is_installed("debug_toolbar")
    config = apps.get_app_config("debug_toolbar")
    assert config.__class__.__module__ == "gyrinx.toolbar_dev"

    assert toolbar_utils._StackTraceRecorder.memoised is True
    assert hasattr(toolbar_utils.get_template_context, "__wrapped__")


def test_installing_twice_does_not_wrap_twice():
    recorder = toolbar_utils._StackTraceRecorder
    get_template_context = toolbar_utils.get_template_context

    install()

    assert toolbar_utils._StackTraceRecorder is recorder
    assert toolbar_utils.get_template_context is get_template_context


def record(recorder, depth=3):
    """Capture a trace a few frames deep, from the same line for every recorder."""
    if depth:
        return record(recorder, depth - 1)
    return recorder.get_stack_trace(excluded_modules=HIDDEN)


def test_a_memoised_stack_trace_matches_the_toolbars_own():
    original, _ = toolbar_originals()
    memoised = toolbar_utils._StackTraceRecorder()

    expected, first, second = [
        record(recorder) for recorder in (original(), memoised, memoised)
    ]

    assert first == expected
    # The second trace is served from the frame cache and is still the same.
    assert second == expected
    assert first is not second
    assert any(entry[2] == "record" for entry in expected)
    assert not any("/debug_toolbar/" in entry[0] for entry in expected)


def test_a_stack_trace_with_locals_is_left_to_the_toolbar():
    memoised = toolbar_utils._StackTraceRecorder()

    trace = memoised.get_stack_trace(excluded_modules=HIDDEN, include_locals=True)

    assert trace[-1][2] == "test_a_stack_trace_with_locals_is_left_to_the_toolbar"
    assert trace[-1][4] is not None
    assert memoised.frame_caches == {}


def test_changing_the_hidden_modules_changes_the_trace():
    """A frame hidden for one list of modules is shown for another, on one recorder."""
    original, _ = toolbar_originals()
    memoised = toolbar_utils._StackTraceRecorder()
    hide_tests = (*HIDDEN, __name__)

    expected_hidden, expected_shown, hidden, shown, hidden_again = [
        recorder.get_stack_trace(excluded_modules=modules)
        for recorder, modules in (
            (original(), hide_tests),
            (original(), HIDDEN),
            (memoised, hide_tests),
            (memoised, HIDDEN),
            (memoised, hide_tests),
        )
    ]

    assert hidden == expected_hidden
    assert shown == expected_shown
    assert hidden_again == expected_hidden
    assert hidden != shown


def test_a_memoised_template_context_matches_the_toolbars_own():
    _, original = toolbar_originals()
    # A debug engine, as in development: only it records where each token is.
    template = Engine(debug=True).from_string(
        "one\ntwo\n{% if flag %}\nthree {{ value }}\n{% endif %}\nfour\nfive\n"
    )
    context = Context({"flag": True, "value": 1})
    context.template = template
    node = next(n for n in template.nodelist if n.token.contents.startswith("if"))

    expected = original(node, context)
    first = toolbar_utils.get_template_context(node, context)
    second = toolbar_utils.get_template_context(node, context)

    assert first == expected
    assert second == expected
    # Callers get their own copies, never the cached entry.
    assert first is not second
    assert first["context"][0] is not second["context"][0]
    assert [line for line in expected["context"] if line["highlight"]] == [
        {"num": 3, "content": "{% if flag %}\n", "highlight": True}
    ]


def test_memoised_stack_trace_html_matches_the_toolbars_own():
    from debug_toolbar.panels import cache
    from debug_toolbar.panels.sql import panel as sql_panel

    original = toolbar_utils.render_stacktrace.__wrapped__
    trace = record(toolbar_utils._StackTraceRecorder())
    trace.append(("<frozen importlib._bootstrap>", 1, "<module>", "", None))

    expected = original(trace)

    assert toolbar_utils.render_stacktrace(trace) == expected
    assert toolbar_utils.render_stacktrace(trace) == expected
    assert type(toolbar_utils.render_stacktrace(trace)) is type(expected)
    assert cache.render_stacktrace is toolbar_utils.render_stacktrace
    assert sql_panel.render_stacktrace is toolbar_utils.render_stacktrace
