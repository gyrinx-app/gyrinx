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
from django.template.base import token_kwargs
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
            "`PATH=$PWD/.venv/bin:$PATH npm run js`."
        ) from exc


def asset_url(filename):
    # Vite owns these hashes and relative module imports. Django must not
    # give an imported module a second URL (and a second React instance).
    return urljoin("/", f"{settings.STATIC_URL.rstrip('/')}/n26/react/{filename}")


def _entry(name):
    """The island's module URL and the modulepreloads its imports need."""
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
    return asset_url(manifest[entry]["file"]), preloads


def _host(name, props, *, css, content, after="", fallback=False):
    module, preloads = _entry(name)
    identifier = f"react-{uuid4().hex}"
    loader = format_html(
        '<script type="module" src="{}"></script>',
        urljoin("/", static("n26/react-islands.js")),
    )
    return format_html(
        '{}<div id="{}" data-react-module="{}" data-react-props="{}"{} x-ignore hx-disable class="{}">'
        "{}</div>{}{}{}",
        preloads,
        identifier,
        module,
        f"{identifier}-props",
        # The body is a working control; a failed load leaves it standing.
        format_html(" {}", "data-react-fallback") if fallback else "",
        css,
        content,
        json_script(props, f"{identifier}-props"),
        after,
        loader,
    )


@register.simple_tag
def react_island(name, props):
    return _host(
        name,
        props,
        css="min-h-32",
        content=format_html(
            '<p role="status" class="text-sm text-muted">{}</p>', "Loading…"
        ),
        after=format_html(
            "<noscript><p>{}</p></noscript>", "Enable JavaScript to use this section."
        ),
    )


class ReactHostNode(template.Node):
    def __init__(self, name, props, css, nodelist):
        self.name = name
        self.props = props
        self.css = css
        self.nodelist = nodelist

    def render(self, context):
        return _host(
            self.name.resolve(context),
            self.props.resolve(context),
            css=self.css.resolve(context) if self.css else "",
            # Template output is already safe; format_html keeps it as it is.
            content=self.nodelist.render(context),
            fallback=True,
        )


@register.tag
def react_host(parser, token):
    """An island drawn in place of server-rendered markup.

    ``{% react_host "name" props class="..." %}…{% endreact_host %}``. The
    body is what the page shows until the island mounts, and all it shows
    without JavaScript; React replaces it on mount. For a control that
    holds a place in a bar, where ``react_island``'s loading box would
    shift the layout.
    """
    bits = token.split_contents()
    if len(bits) < 3:
        raise template.TemplateSyntaxError(
            f"{bits[0]} takes an island name and its props"
        )
    name = parser.compile_filter(bits[1])
    props = parser.compile_filter(bits[2])
    extra = token_kwargs(bits[3:], parser)
    if set(extra) - {"class"} or len(bits[3:]) != len(extra):
        raise template.TemplateSyntaxError(f"{bits[0]} takes only class=")
    nodelist = parser.parse(("endreact_host",))
    parser.delete_first_token()
    return ReactHostNode(name, props, extra.get("class"), nodelist)
