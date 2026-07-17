"""Bootstrap icon component and the design-system icon vocabulary.

The design system uses Bootstrap Icons in **hyphenated** form (``bi-pencil``,
never ``bi bi-pencil``). :func:`Icon` enforces that and gives semantic names a
single home so the "which icon means edit?" decision lives in one place.
"""

from __future__ import annotations

from typing import Any

from ..elements import Element
from ..tags import i

__all__ = ["Icon", "ICONS"]

# Semantic concept -> Bootstrap icon name (see docs/DESIGN-SYSTEM.md § Icons).
ICONS = {
    "add": "plus-lg",
    "edit": "pencil",
    "delete": "trash",
    "back": "chevron-left",
    "search": "search",
    "warning": "exclamation-triangle",
    "info": "info-circle",
    "confirm": "check-lg",
    "save": "check-lg",
    "more": "three-dots-vertical",
    "pack": "box-seam",
    "archive": "archive",
    "clone": "copy",
    "person": "person",
    "eye": "eye",
    "gear": "gear",
    "dice": "dice-6",
}


def Icon(name: str, *, class_: Any = None, **attrs: Any) -> Element:
    """Render a Bootstrap icon: ``Icon("pencil")`` -> ``<i class="bi-pencil">``.

    ``name`` may be a raw Bootstrap icon name (``"pencil"``) or a semantic
    concept from :data:`ICONS` (``"edit"``). A leading ``bi-`` is tolerated and
    stripped. Extra classes (e.g. ``"fs-7"``, ``"text-secondary"``) go via
    ``class_``.
    """
    resolved = ICONS.get(name, name)
    if resolved.startswith("bi-"):
        resolved = resolved[3:]
    return i(class_=[f"bi-{resolved}", class_], **attrs)
