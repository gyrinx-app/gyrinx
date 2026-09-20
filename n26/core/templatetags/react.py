"""Client-rendered islands and Vite's content-addressed asset graph."""

import json
import re
from functools import cache
from pathlib import Path
from urllib.parse import urljoin
from uuid import uuid4

from django import template
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.templatetags.static import static
from django.utils.html import format_html, format_html_join, json_script

register = template.Library()
BUILD = Path(__file__).resolve().parents[1] / "static" / "n26" / "react"


@cache
def _manifest():
    try:
        return json.loads((BUILD / "manifest.json").read_text())
    except FileNotFoundError as exc:
        raise ImproperlyConfigured(
            "React assets are missing. Rebuild them with the worktree venv "
            "on PATH: `.codex/run.sh npm run js` or "
            "`PATH=$PWD/.venv/bin:$PATH npm run js`. "
            "Do not run npm audit fix unless the task is the audit itself."
        ) from exc


def asset_url(filename):
    # Vite owns these hashes and relative module imports. Django must not
    # give an imported module a second URL (and a second React instance).
    return urljoin("/", f"{settings.STATIC_URL.rstrip('/')}/n26/react/{filename}")


@register.simple_tag
def react_island(name, props):
    if not re.fullmatch(r"[a-z][a-z0-9-]*", name):
        raise ValueError("React island names must be kebab-case")
    if settings.DEBUG:
        _manifest.cache_clear()
    manifest = _manifest()
    entry = f"islands/{name}/entry.tsx"
    if entry not in manifest:
        raise ImproperlyConfigured(
            f"No built React entry for {name!r}. Rebuild with the worktree "
            "venv on PATH: `.codex/run.sh npm run js` or "
            "`PATH=$PWD/.venv/bin:$PATH npm run js`."
        )
    files = []

    def visit(key):
        chunk = manifest[key]
        if chunk["file"] in files:
            return
        files.append(chunk["file"])
        for dependency in chunk.get("imports", []):
            visit(dependency)

    visit(entry)
    preloads = format_html_join(
        "",
        '<link rel="modulepreload" href="{}">',
        ((asset_url(file),) for file in files),
    )
    identifier = f"react-{uuid4().hex}"
    loader = format_html(
        '<script type="module" src="{}"></script>',
        urljoin("/", static("n26/react-islands.js")),
    )
    return format_html(
        '{}<div id="{}" data-react-module="{}" data-react-props="{}" x-ignore hx-disable class="min-h-32">'
        '<p role="status" class="text-sm text-muted">Loading…</p></div>{}'
        "<noscript><p>Enable JavaScript to use this section.</p></noscript>{}",
        preloads,
        identifier,
        asset_url(manifest[entry]["file"]),
        f"{identifier}-props",
        json_script(props, f"{identifier}-props"),
        loader,
    )
