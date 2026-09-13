from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings

from gyrinx.page_inspection import PageCapture, build_report, capture_request


def _query(sql, params, duration, *, template=None):
    return {
        "raw_sql": sql,
        "params": params,
        "duration": duration,
        "is_slow": duration > 500,
        "stacktrace": [],
        "template_info": template,
    }


def _capture(queries=None):
    queries = queries or []
    return PageCapture(
        path="/example/?tab=active",
        status_code=200,
        content_type="text/html; charset=utf-8",
        redirect_chain=[],
        request_id="request-id",
        panels={
            "TimerPanel": {"total_time": 20.5, "total": 12.25},
            "SQLPanel": {
                "queries": queries,
                "sql_time": sum(query["duration"] for query in queries),
            },
            "TemplatesPanel": {
                "templates": [
                    {
                        "template": {
                            "name": "example.html",
                            "origin_name": "/app/example.html",
                        }
                    },
                    {"template": {"name": "row.html", "origin_name": "/app/row.html"}},
                    {"template": {"name": "row.html", "origin_name": "/app/row.html"}},
                ]
            },
            "CachePanel": {
                "total_calls": 2,
                "total_time": 0.5,
                "hits": 1,
                "misses": 1,
            },
            "RequestPanel": {"view_func": "app.view", "view_urlname": "example"},
            "StaticFilesPanel": {"num_used": 3},
            "TasksPanel": {"tasks": []},
            "AlertsPanel": {"alerts": []},
        },
    )


def test_report_summarises_and_bounds_toolbar_data():
    template = {
        "name": "/workspace/templates/row.html",
        "context": [
            {"num": 4, "content": "before", "highlight": False},
            {"num": 5, "content": "{{ row.owner }}", "highlight": True},
        ],
    }
    queries = [
        _query("SELECT * FROM owner WHERE id = %s", [1], 2.0, template=template),
        _query("SELECT * FROM owner WHERE id = %s", [2], 3.0, template=template),
        _query("SELECT * FROM flags", [], 1.0),
        _query("SELECT * FROM flags", [], 1.5),
    ]

    report = build_report(
        [_capture(queries)],
        username="agent",
        warmup_requests=1,
        detail_panels=["sql", "templates"],
        limit=1,
        project_root=Path("/workspace"),
    )

    assert report["summary"]["sql"] == {
        "query_count": 4,
        "time_ms": 7.5,
        "similar_groups": 2,
        "similar_queries": 4,
        "duplicate_groups": 1,
        "duplicate_queries": 2,
        "slow_queries": 0,
    }
    assert len(report["details"]["sql"]["similar"]) == 1
    assert report["details"]["sql"]["similar"][0]["source"] == {
        "template": "templates/row.html",
        "line": 5,
        "code": "{{ row.owner }}",
    }
    assert report["details"]["templates"] == {
        "renders": 3,
        "unique": 2,
        "templates": [{"name": "row.html", "renders": 2, "origin": "/app/row.html"}],
    }


def test_command_emits_compact_summary(monkeypatch):
    monkeypatch.setattr(
        "n23.core.management.commands.inspect_page.capture_request",
        lambda *args, **kwargs: _capture(),
    )
    stdout = StringIO()

    with override_settings(DEBUG=True):
        call_command(
            "inspect_page",
            "/example/",
            anonymous=True,
            warmup=0,
            repeat=1,
            stdout=stdout,
        )

    output = stdout.getvalue()
    assert "GET /example/?tab=active -> 200 as anonymous" in output
    assert "SQL: 0 queries in 0.00ms" in output
    assert "Templates: 3 renders, 2 unique" in output


@override_settings(DEBUG=False)
def test_command_refuses_without_debug():
    with pytest.raises(CommandError, match="only available with DEBUG enabled"):
        call_command("inspect_page", "/example/")


def _show_toolbar(request):
    return True


@override_settings(
    DEBUG=True,
    DEBUG_TOOLBAR_CONFIG={
        "SHOW_COLLAPSED": True,
        "SHOW_TOOLBAR_CALLBACK": _show_toolbar,
    },
)
@pytest.mark.django_db
def test_capture_request_reads_real_toolbar_panels():
    from debug_toolbar import settings as toolbar_settings
    from debug_toolbar.middleware import show_toolbar_func_or_path

    toolbar_settings.get_config.cache_clear()
    show_toolbar_func_or_path.cache_clear()
    try:
        capture = capture_request(Client(), "/n26/", follow=True)
    finally:
        toolbar_settings.get_config.cache_clear()
        show_toolbar_func_or_path.cache_clear()

    assert capture.status_code == 200
    assert capture.request_id
    assert "TimerPanel" in capture.panels
    assert "SQLPanel" in capture.panels
    assert "TemplatesPanel" in capture.panels
