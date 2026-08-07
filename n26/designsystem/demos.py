"""Demo discovery.

Every example in the gallery is a real template file under
``designsystem/templates/designsystem/demos/<component-slug>/``. The page renders
that file *and* prints its source, so the code you read is by construction the
code that produced the preview above it — there is no second copy to drift.

Files are ordered by a numeric filename prefix (``10-variants.html``) and carry
their own metadata in leading comments::

    {# title: Variants #}
    {# note: Six fills, plus an outlined flavour of each. #}
    <c-ui.button variant="primary">Save</c-ui.button>

``note`` is optional. A file with no ``title`` falls back to a title derived
from its filename.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings

DEMO_ROOT = Path(__file__).resolve().parent / "templates" / "designsystem" / "demos"

_META = re.compile(r"^\{#\s*(title|note|layout)\s*:\s*(.*?)\s*#\}\s*$")
_ORDER = re.compile(r"^(\d+)[-_]")


@dataclass(frozen=True)
class Demo:
    """One example: where to render it from, and the source to display."""

    slug: str
    """Stable id, unique within the component (the filename minus order prefix)."""

    title: str
    note: str
    layout: str
    """How the preview arranges children: ``row`` (default), ``col`` or ``full``."""

    template_name: str
    source: str
    """The file's body, metadata stripped, so the snippet is copy-pasteable."""

    @property
    def dom_id(self) -> str:
        return f"demo-{self.slug}"


def _parse(path: Path, component_slug: str) -> Demo:
    raw = path.read_text()
    meta: dict[str, str] = {}
    lines = raw.splitlines()

    # Metadata is a contiguous run of comment lines at the very top; stop at the
    # first line that is not one, so a comment inside the markup stays in the source.
    body_start = 0
    for i, line in enumerate(lines):
        if not line.strip():
            body_start = i + 1
            continue
        match = _META.match(line.strip())
        if not match:
            body_start = i
            break
        meta[match.group(1)] = match.group(2)
        body_start = i + 1

    slug = _ORDER.sub("", path.stem)
    return Demo(
        slug=slug,
        title=meta.get("title") or slug.replace("-", " ").capitalize(),
        note=meta.get("note", ""),
        layout=meta.get("layout", "row"),
        template_name=f"designsystem/demos/{component_slug}/{path.name}",
        source="\n".join(lines[body_start:]).strip(),
    )


@cache
def _discover(component_slug: str) -> tuple[Demo, ...]:
    directory = DEMO_ROOT / component_slug
    if not directory.is_dir():
        return ()
    return tuple(
        _parse(path, component_slug) for path in sorted(directory.glob("*.html"))
    )


def demos_for(component_slug: str) -> tuple[Demo, ...]:
    # Under DEBUG the source is re-read every request, so editing a demo file and
    # hitting refresh shows both the new preview and the new listing.
    if settings.DEBUG:
        _discover.cache_clear()
    return _discover(component_slug)
