"""Golden-equivalence helpers: prove a component reproduces its legacy template.

We render the legacy Django template and the new component with the *same*
context + request, normalise both (strip CSRF tokens, sort attributes, collapse
whitespace) and compare. A match proves the conversion is faithful — including
the shared layout shell, since both render through their full page layout.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup, Tag
from django.template import engines
from django.template.loader import render_to_string


def render_legacy(template_name: str, context: dict[str, Any], request: Any) -> str:
    """Render a template via the DjangoTemplates backend, bypassing the
    component backend (which would otherwise intercept the name)."""
    for engine in engines.all():
        if engine.__class__.__name__ == "DjangoTemplates":
            return engine.get_template(template_name).render(context, request)
    raise AssertionError("DjangoTemplates backend not configured")


def render_component(template_name: str, context: dict[str, Any], request: Any) -> str:
    """Render a template via the loader (component backend claims it first)."""
    return render_to_string(template_name, context, request=request)


def _normalise_tag(root: Tag) -> None:
    # Drop CSRF hidden inputs (random token each render).
    for csrf in root.find_all("input", attrs={"name": "csrfmiddlewaretoken"}):
        csrf.decompose()
    # Sort attributes for order-independent comparison.
    for node in root.find_all(True):
        if node.attrs:
            new_attrs = {}
            for key in sorted(node.attrs):
                value = node.attrs[key]
                if isinstance(value, list):  # e.g. class -> token list
                    value = " ".join(sorted(value))
                new_attrs[key] = value
            node.attrs = new_attrs
    # Trim/collapse text nodes so insignificant inline whitespace (present in
    # Django templates, absent in compact component output) doesn't matter.
    for text in list(root.find_all(string=True)):
        collapsed = re.sub(r"\s+", " ", str(text)).strip()
        if collapsed:
            text.replace_with(collapsed)
        else:
            text.extract()


def normalise_fragment(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _normalise_tag(soup)
    out = soup.decode()
    return re.sub(r">\s+<", "><", out).strip()


def extract_content(html: str) -> str:
    """Return the normalised ``#content`` subtree — the part a page component
    actually owns (the shared nav/footer shell is verified separately)."""
    soup = BeautifulSoup(html, "html.parser")
    content = soup.find(id="content")
    if content is None:
        raise AssertionError("No #content element in rendered page")
    _normalise_tag(content)
    out = content.decode()
    return re.sub(r">\s+<", "><", out).strip()


def assert_equivalent(
    template_name: str, context: dict[str, Any], request: Any, *, scope: str = "content"
) -> None:
    """Assert the component and legacy template render to equivalent HTML.

    ``scope="content"`` (default) compares only the ``#content`` subtree;
    ``scope="page"`` compares the whole document."""
    extract = extract_content if scope == "content" else normalise_fragment
    legacy = extract(render_legacy(template_name, dict(context), request))
    component = extract(render_component(template_name, dict(context), request))
    if legacy != component:  # pragma: no cover - diagnostic path
        _report_diff(legacy, component)
    assert legacy == component


def _report_diff(legacy: str, component: str) -> None:  # pragma: no cover
    import difflib

    # Split on tag boundaries for a readable diff.
    legacy_lines = legacy.replace("><", ">\n<").splitlines()
    component_lines = component.replace("><", ">\n<").splitlines()
    diff = "\n".join(
        difflib.unified_diff(
            legacy_lines, component_lines, "legacy", "component", lineterm=""
        )
    )
    raise AssertionError("Component output differs from legacy template:\n" + diff)
