"""Compact, structured reports from Django Debug Toolbar page captures."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.test import Client

PANEL_IDS = {
    "timing": "TimerPanel",
    "sql": "SQLPanel",
    "templates": "TemplatesPanel",
    "cache": "CachePanel",
    "request": "RequestPanel",
    "headers": "HeadersPanel",
    "static": "StaticFilesPanel",
    "signals": "SignalsPanel",
    "tasks": "TasksPanel",
    "alerts": "AlertsPanel",
    "settings": "SettingsPanel",
    "versions": "VersionsPanel",
    "history": "HistoryPanel",
}
PANEL_NAMES = tuple(PANEL_IDS)


@dataclass
class PageCapture:
    """One response and the toolbar statistics collected for it."""

    path: str
    status_code: int
    content_type: str
    redirect_chain: list[tuple[str, int]]
    request_id: str
    panels: dict[str, dict[str, Any]]


def capture_request(
    client: Client,
    path: str,
    *,
    follow: bool = True,
    headers: dict[str, str] | None = None,
) -> PageCapture:
    """Issue a GET and return the toolbar created for its final response."""
    try:
        from debug_toolbar.toolbar import DebugToolbar
    except ImportError as error:  # pragma: no cover - dependency is installed here
        raise RuntimeError("django-debug-toolbar is not installed") from error

    toolbars = []
    dispatch_uid = f"inspect-page-{id(toolbars)}"

    def collect_toolbar(sender, toolbar, **kwargs):
        toolbars.append(toolbar)

    DebugToolbar._created.connect(  # noqa: SLF001 - pinned development dependency
        collect_toolbar,
        weak=False,
        dispatch_uid=dispatch_uid,
    )
    try:
        response = client.get(path, follow=follow, headers=headers or {})
    finally:
        DebugToolbar._created.disconnect(  # noqa: SLF001
            dispatch_uid=dispatch_uid
        )

    if not toolbars:
        raise RuntimeError(
            "Django Debug Toolbar did not capture the request. "
            "Run this command with DEBUG enabled and development settings."
        )

    toolbar = toolbars[-1]
    return PageCapture(
        path=path,
        status_code=response.status_code,
        content_type=response.get("Content-Type", ""),
        redirect_chain=list(getattr(response, "redirect_chain", [])),
        request_id=toolbar.request_id,
        panels={
            panel.panel_id: toolbar.store.panel(toolbar.request_id, panel.panel_id)
            for panel in toolbar.panels
        },
    )


def build_report(
    captures: list[PageCapture],
    *,
    username: str | None,
    warmup_requests: int,
    detail_panels: list[str],
    limit: int,
    setting_filters: list[str] | None = None,
    project_root: Path | None = None,
) -> dict[str, Any]:
    """Build a bounded report from one or more measured requests."""
    if not captures:
        raise ValueError("At least one measured capture is required")

    capture = captures[-1]
    report = {
        "request": {
            "path": capture.path,
            "status_code": capture.status_code,
            "content_type": capture.content_type,
            "user": username or "anonymous",
            "followed_redirects": [
                {"url": url, "status_code": status}
                for url, status in capture.redirect_chain
            ],
            "warmup_requests": warmup_requests,
            "measured_requests": len(captures),
            "toolbar_request_id": capture.request_id,
        },
        "samples": [_sample(item) for item in captures],
        "summary": _summary(capture.panels),
        "details": {},
    }

    for name in detail_panels:
        stats = capture.panels.get(PANEL_IDS[name], {})
        report["details"][name] = _panel_detail(
            name,
            stats,
            limit=limit,
            setting_filters=setting_filters or [],
            project_root=project_root,
        )
    return report


def render_text(report: dict[str, Any]) -> str:
    """Render a report for a person or a small agent context window."""
    request = report["request"]
    lines = [
        f"GET {request['path']} -> {request['status_code']} as {request['user']}",
    ]
    if request["followed_redirects"]:
        chain = " -> ".join(
            f"{item['status_code']} {item['url']}"
            for item in request["followed_redirects"]
        )
        lines.append(f"Redirects: {chain}")

    samples = report["samples"]
    if len(samples) > 1:
        formatted = ", ".join(
            f"{sample['query_count']}q/{sample['elapsed_ms']:.2f}ms"
            for sample in samples
        )
        stable = len({sample["query_count"] for sample in samples}) == 1
        lines.append(
            f"Samples: {formatted} (query count {'stable' if stable else 'varied'})"
        )

    summary = report["summary"]
    timing = summary["timing"]
    lines.append(
        f"Time: {timing['elapsed_ms']:.2f}ms elapsed, {timing['cpu_ms']:.2f}ms CPU"
    )
    sql = summary["sql"]
    lines.append(
        "SQL: "
        f"{sql['query_count']} queries in {sql['time_ms']:.2f}ms; "
        f"{sql['similar_groups']} similar groups, "
        f"{sql['duplicate_groups']} duplicate groups, "
        f"{sql['slow_queries']} slow"
    )
    templates = summary["templates"]
    lines.append(
        f"Templates: {templates['renders']} renders, {templates['unique']} unique"
    )
    cache = summary["cache"]
    lines.append(
        f"Cache: {cache['calls']} calls in {cache['time_ms']:.2f}ms; "
        f"{cache['hits']} hits, {cache['misses']} misses"
    )
    lines.append(f"Static files: {summary['static_files']['used']} used")
    lines.append(
        f"Tasks: {summary['tasks']['count']} queued; "
        f"alerts: {summary['alerts']['count']}"
    )
    view = summary["view"]
    if view["function"] or view["url_name"]:
        lines.append(f"View: {view['function']} ({view['url_name']})")

    for name, detail in report["details"].items():
        lines.extend(
            [
                "",
                name.upper(),
                json.dumps(detail, indent=2, sort_keys=True, default=str),
            ]
        )
    return "\n".join(lines)


def _sample(capture: PageCapture) -> dict[str, Any]:
    timer = capture.panels.get("TimerPanel", {})
    sql = capture.panels.get("SQLPanel", {})
    return {
        "status_code": capture.status_code,
        "elapsed_ms": _milliseconds(timer.get("total_time", 0)),
        "query_count": len(sql.get("queries", [])),
        "sql_time_ms": _milliseconds(sql.get("sql_time", 0)),
    }


def _summary(panels: dict[str, dict[str, Any]]) -> dict[str, Any]:
    timer = panels.get("TimerPanel", {})
    sql = panels.get("SQLPanel", {})
    queries = sql.get("queries", [])
    templates = panels.get("TemplatesPanel", {}).get("templates", [])
    cache = panels.get("CachePanel", {})
    request = panels.get("RequestPanel", {})
    return {
        "timing": {
            "elapsed_ms": _milliseconds(timer.get("total_time", 0)),
            "cpu_ms": _milliseconds(timer.get("total", 0)),
            "toolbar_ms": _milliseconds(timer.get("toolbar_time", 0)),
        },
        "sql": {
            "query_count": len(queries),
            "time_ms": _milliseconds(sql.get("sql_time", 0)),
            "similar_groups": len(_query_groups(queries, similar=True)),
            "similar_queries": sum(
                len(group) for group in _query_groups(queries, similar=True)
            ),
            "duplicate_groups": len(_query_groups(queries, similar=False)),
            "duplicate_queries": sum(
                len(group) for group in _query_groups(queries, similar=False)
            ),
            "slow_queries": sum(bool(query.get("is_slow")) for query in queries),
        },
        "templates": {
            "renders": len(templates),
            "unique": len({_template_name(item) for item in templates}),
        },
        "cache": {
            "calls": int(cache.get("total_calls", 0)),
            "time_ms": _milliseconds(cache.get("total_time", 0)),
            "hits": int(cache.get("hits", 0)),
            "misses": int(cache.get("misses", 0)),
        },
        "static_files": {
            "used": int(panels.get("StaticFilesPanel", {}).get("num_used", 0))
        },
        "tasks": {"count": len(panels.get("TasksPanel", {}).get("tasks", []))},
        "alerts": {"count": len(panels.get("AlertsPanel", {}).get("alerts", []))},
        "view": {
            "function": request.get("view_func", ""),
            "url_name": request.get("view_urlname", ""),
        },
    }


def _panel_detail(
    name: str,
    stats: dict[str, Any],
    *,
    limit: int,
    setting_filters: list[str],
    project_root: Path | None,
) -> Any:
    if name == "sql":
        return _sql_detail(stats, limit=limit, project_root=project_root)
    if name == "templates":
        return _templates_detail(stats, limit=limit)
    if name == "cache":
        return _cache_detail(stats, limit=limit)
    if name == "request":
        return _request_detail(stats)
    if name == "static":
        return {
            "found": stats.get("num_found", 0),
            "used": stats.get("num_used", 0),
            "files": stats.get("staticfiles", [])[:limit],
        }
    if name == "signals":
        signals = stats.get("signals", [])
        return {
            "signal_count": len(signals),
            "receiver_count": sum(len(receivers) for _, receivers in signals),
            "signals": [
                {"name": signal, "receivers": receivers}
                for signal, receivers in signals[:limit]
            ],
        }
    if name == "tasks":
        tasks = stats.get("tasks", [])
        return {
            "available": stats.get("tasks_available", False),
            "count": len(tasks),
            "tasks": tasks[:limit],
        }
    if name == "alerts":
        alerts = stats.get("alerts", [])
        return {"count": len(alerts), "alerts": alerts[:limit]}
    if name == "settings":
        return _settings_detail(stats, limit=limit, filters=setting_filters)
    if name == "versions":
        return {
            "django": stats.get("django_version"),
            "packages": stats.get("versions", [])[:limit],
            "python_paths": stats.get("paths", [])[:limit],
        }
    if name == "headers":
        return {
            "request": stats.get("request_headers", {}),
            "response": stats.get("response_headers", {}),
            "wsgi": stats.get("environ", {}),
        }
    if name == "timing":
        return stats
    if name == "history":
        return stats
    return stats


def _sql_detail(
    stats: dict[str, Any], *, limit: int, project_root: Path | None
) -> dict[str, Any]:
    queries = stats.get("queries", [])
    similar = _query_groups(queries, similar=True)
    duplicates = _query_groups(queries, similar=False)
    longest = sorted(queries, key=lambda query: query.get("duration", 0), reverse=True)
    return {
        "query_count": len(queries),
        "time_ms": _milliseconds(stats.get("sql_time", 0)),
        "similar": [
            _query_group_report(group, project_root=project_root)
            for group in similar[:limit]
        ],
        "duplicates": [
            _query_group_report(group, project_root=project_root)
            for group in duplicates[:limit]
        ],
        "longest": [
            _query_report(query, project_root=project_root) for query in longest[:limit]
        ],
    }


def _query_groups(
    queries: list[dict[str, Any]], *, similar: bool
) -> list[list[dict[str, Any]]]:
    grouped = defaultdict(list)
    for query in queries:
        key: Any = query.get("raw_sql", query.get("sql", ""))
        if not similar:
            key = (key, json.dumps(query.get("params"), sort_keys=True, default=str))
        grouped[key].append(query)
    groups = [group for group in grouped.values() if len(group) > 1]
    return sorted(
        groups,
        key=lambda group: (
            -len(group),
            -sum(float(query.get("duration", 0)) for query in group),
        ),
    )


def _query_group_report(
    group: list[dict[str, Any]], *, project_root: Path | None
) -> dict[str, Any]:
    representative = group[0]
    return {
        "count": len(group),
        "time_ms": _milliseconds(
            sum(float(query.get("duration", 0)) for query in group)
        ),
        "sql": _compact_sql(
            representative.get("raw_sql", representative.get("sql", ""))
        ),
        "source": _query_source(representative, project_root=project_root),
    }


def _query_report(
    query: dict[str, Any], *, project_root: Path | None
) -> dict[str, Any]:
    return {
        "time_ms": _milliseconds(query.get("duration", 0)),
        "slow": bool(query.get("is_slow")),
        "sql": _compact_sql(query.get("raw_sql", query.get("sql", ""))),
        "source": _query_source(query, project_root=project_root),
    }


def _query_source(
    query: dict[str, Any], *, project_root: Path | None
) -> dict[str, Any] | None:
    template = query.get("template_info")
    if template:
        name = Path(str(template.get("name") or ""))
        if project_root is not None:
            try:
                name = name.resolve().relative_to(project_root.resolve())
            except ValueError:
                pass
        highlighted = next(
            (line for line in template.get("context", []) if line.get("highlight")),
            {},
        )
        return {
            "template": name.as_posix(),
            "line": highlighted.get("num"),
            "code": str(highlighted.get("content", "")).strip(),
        }
    if project_root is None:
        return None
    root = project_root.resolve()
    candidates = []
    for frame in query.get("stacktrace", []):
        if len(frame) < 4:
            continue
        filename = Path(frame[0])
        try:
            relative = filename.resolve().relative_to(root)
        except ValueError:
            continue
        if ".venv" in relative.parts or relative.as_posix() == "scripts/manage.py":
            continue
        candidates.append(
            {
                "path": relative.as_posix(),
                "line": frame[1],
                "function": frame[2],
                "code": frame[3],
            }
        )
    return candidates[-1] if candidates else None


def _compact_sql(sql: str, *, width: int = 500) -> str:
    compact = " ".join(str(sql).split())
    return compact if len(compact) <= width else compact[: width - 1] + "…"


def _templates_detail(stats: dict[str, Any], *, limit: int) -> dict[str, Any]:
    templates = stats.get("templates", [])
    counts = Counter(_template_name(item) for item in templates)
    origins = {
        _template_name(item): item.get("template", {}).get("origin_name")
        for item in templates
    }
    rows = [
        {"name": name, "renders": count, "origin": origins.get(name)}
        for name, count in counts.most_common(limit)
    ]
    return {"renders": len(templates), "unique": len(counts), "templates": rows}


def _template_name(item: dict[str, Any]) -> str:
    return item.get("template", {}).get("name") or "<unnamed>"


def _cache_detail(stats: dict[str, Any], *, limit: int) -> dict[str, Any]:
    calls = stats.get("calls", [])
    return {
        "calls": len(calls),
        "time_ms": _milliseconds(stats.get("total_time", 0)),
        "hits": int(stats.get("hits", 0)),
        "misses": int(stats.get("misses", 0)),
        "operations": {
            key: value for key, value in stats.get("counts", {}).items() if value
        },
        "entries": [
            {
                "operation": call.get("name"),
                "time_ms": _milliseconds(call.get("time", 0)),
                "backend": call.get("backend"),
                "args": [_bounded_repr(value) for value in call.get("args", [])[:2]],
                "kwargs": sorted(call.get("kwargs", {})),
            }
            for call in calls[:limit]
        ],
    }


def _request_detail(stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "view_function": stats.get("view_func"),
        "url_name": stats.get("view_urlname"),
        "args": stats.get("view_args", []),
        "kwargs": stats.get("view_kwargs", {}),
        "get": _toolbar_pairs(stats.get("get")),
        "post": _toolbar_pairs(stats.get("post")),
        "cookie_names": sorted(_toolbar_pairs(stats.get("cookies"))),
        "session_keys": sorted(_toolbar_pairs(stats.get("session"))),
    }


def _toolbar_pairs(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("list"), list):
        return dict(value["list"])
    return {}


def _settings_detail(
    stats: dict[str, Any], *, limit: int, filters: list[str]
) -> dict[str, Any]:
    settings = stats.get("settings", {})
    lowered = [value.lower() for value in filters]
    selected = {
        key: value
        for key, value in sorted(settings.items())
        if not lowered or any(pattern in key.lower() for pattern in lowered)
    }
    return {
        "available": len(settings),
        "matched": len(selected),
        "settings": dict(list(selected.items())[:limit]),
    }


def _bounded_repr(value: Any, *, width: int = 160) -> str:
    rendered = repr(value)
    return rendered if len(rendered) <= width else rendered[: width - 1] + "…"


def _milliseconds(value: Any) -> float:
    return round(float(value or 0), 3)
