import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, override_settings

from gyrinx.page_inspection import (
    PANEL_NAMES,
    PageCapture,
    build_report,
    capture_request,
    render_text,
)


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


def test_report_redacts_sensitive_headers():
    capture = _capture()
    capture.panels["HeadersPanel"] = {
        "request_headers": {
            "Authorization": "Bearer request-secret",
            "Cookie": "sessionid=cookie-secret",
            "X-Api-Key": "api-secret",
            "X-Public": "visible",
        },
        "response_headers": {
            "Set-Cookie": "response-secret",
            "Location": "/next/?token=location-secret",
        },
        "environ": {
            "HTTP_AUTHORIZATION": "Bearer environ-secret",
            "HTTP_COOKIE": "sessionid=environ-cookie-secret",
        },
    }

    report = build_report(
        [capture],
        username="agent",
        warmup_requests=0,
        detail_panels=["headers"],
        limit=10,
    )

    headers = report["details"]["headers"]
    assert headers["request"] == {
        "Authorization": "<redacted>",
        "Cookie": "<redacted>",
        "X-Api-Key": "<redacted>",
        "X-Public": "visible",
    }
    assert headers["response"]["Set-Cookie"] == "<redacted>"
    assert headers["response"]["Location"] == "/next/?token=<redacted>"
    assert headers["wsgi"]["HTTP_AUTHORIZATION"] == "<redacted>"
    assert headers["wsgi"]["HTTP_COOKIE"] == "<redacted>"
    assert "secret" not in str(report)


def test_report_redacts_sensitive_query_values_in_urls():
    capture = _capture()
    capture.path = "/reset/?token=path-secret&next=%2Fsafe%2F"
    capture.redirect_chain = [
        ("/login/?signature=redirect-secret&next=%2Fsafe%2F", 302)
    ]
    capture.panels["HistoryPanel"] = {
        "request_url": "/reset/?password=history-secret",
        "request_method": "GET",
        "status_code": 200,
    }

    report = build_report(
        [capture],
        username="agent",
        warmup_requests=0,
        detail_panels=["history"],
        limit=10,
    )

    assert report["request"]["path"] == "/reset/?token=<redacted>&next=%2Fsafe%2F"
    assert report["request"]["followed_redirects"] == [
        {
            "url": "/login/?signature=<redacted>&next=%2Fsafe%2F",
            "status_code": 302,
        }
    ]
    assert report["details"]["history"]["request_url"] == (
        "/reset/?password=<redacted>"
    )
    assert "secret" not in json.dumps(report)
    assert "secret" not in render_text(report)


def test_all_detailed_panels_bound_nested_toolbar_data():
    long_value = "x" * 200
    capture = _capture(
        [
            _query("SELECT * FROM owner WHERE id = %s", [1], 2.0),
            _query("SELECT * FROM owner WHERE id = %s", [2], 3.0),
        ]
    )
    capture.panels.update(
        {
            "TimerPanel": {
                "total_time": 20.0,
                "utime": 1.0,
                "stime": 2.0,
                "ignored": long_value,
            },
            "CachePanel": {
                "counts": {"get": 2, "set": 1},
                "calls": [
                    {
                        "name": long_value,
                        "backend": long_value,
                        "args": [long_value, long_value],
                        "kwargs": {"first": 1, "second": 2},
                    },
                    {"name": "ignored"},
                ],
            },
            "RequestPanel": {
                "view_func": long_value,
                "view_urlname": long_value,
                "view_args": [long_value, long_value],
                "view_kwargs": {"first": long_value, "second": long_value},
                "get": {"list": [("first", [long_value, long_value]), ("second", 2)]},
                "post": {"list": [("first", long_value), ("second", 2)]},
                "cookies": {"list": [("first", "secret"), ("second", "secret")]},
                "session": {"list": [("first", "secret"), ("second", "secret")]},
            },
            "HeadersPanel": {
                "request_headers": {"Authorization": "secret", "X-Next": "ignored"},
                "response_headers": {"X-First": long_value, "X-Next": "ignored"},
                "environ": {"PATH_INFO": long_value, "SERVER_NAME": "ignored"},
            },
            "StaticFilesPanel": {
                "staticfiles": [long_value, long_value],
            },
            "SignalsPanel": {
                "signals": [
                    ("first", [long_value, long_value]),
                    ("second", [long_value, long_value]),
                ]
            },
            "TasksPanel": {"tasks": [[long_value, long_value], [long_value]]},
            "AlertsPanel": {"alerts": [[long_value, long_value], [long_value]]},
            "SettingsPanel": {
                "settings": {"FIRST": [long_value, long_value], "SECOND": long_value}
            },
            "VersionsPanel": {
                "versions": [[long_value, long_value], [long_value]],
                "paths": [long_value, long_value],
            },
            "HistoryPanel": {
                "request_url": long_value,
                "request_method": "GET",
                "status_code": 200,
                "data": {"first": [long_value, long_value], "second": long_value},
                "ignored": long_value,
            },
        }
    )

    details = build_report(
        [capture],
        username="agent",
        warmup_requests=0,
        detail_panels=list(PANEL_NAMES),
        limit=1,
    )["details"]

    assert len(details["sql"]["similar"]) == 1
    assert len(details["templates"]["templates"]) == 1
    assert len(details["cache"]["operations"]) == 1
    assert len(details["cache"]["entries"]) == 1
    assert len(details["cache"]["entries"][0]["args"]) == 1
    assert len(details["cache"]["entries"][0]["kwargs"]) == 1
    assert len(details["request"]["args"]) == 1
    assert len(details["request"]["kwargs"]) == 1
    assert len(details["request"]["get"]) == 1
    assert len(details["request"]["cookie_names"]) == 1
    assert len(details["headers"]["request"]) == 1
    assert details["headers"]["request"]["Authorization"] == "<redacted>"
    assert len(details["static"]["files"]) == 1
    assert len(details["signals"]["signals"]) == 1
    assert len(details["signals"]["signals"][0]["receivers"]) == 1
    assert len(details["tasks"]["tasks"]) == 1
    assert len(details["tasks"]["tasks"][0]) == 1
    assert len(details["alerts"]["alerts"]) == 1
    assert len(details["settings"]["settings"]) == 1
    assert len(details["versions"]["packages"]) == 1
    assert len(details["versions"]["python_paths"]) == 1
    assert details["timing"] == {"total_time": 20.0, "utime": 1.0, "stime": 2.0}
    assert len(details["history"]["data"]) == 1
    assert len(details["history"]["data"]["first"]) == 1
    assert details["history"]["request_url"].endswith("…")


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
