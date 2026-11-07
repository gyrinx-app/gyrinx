"""Read component props, documentation and slots from the templates selected by Django.
Public props come from c-vars; the first comment block supplies displayed documentation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import django_cotton_ui
from django.conf import settings

KIT_TEMPLATES = (
    Path(django_cotton_ui.__file__).resolve().parent / "templates" / "cotton"
)
UI_ROOT = KIT_TEMPLATES / "ui"

# BASE_DIR is the repository root; edition components live under the core template tree.
LOCAL_ROOT = Path(settings.BASE_DIR) / "n26" / "core" / "templates" / "cotton"

# Search local kit overrides before installed templates to match Django's template
# resolution order.
LOCAL_UI_ROOT = LOCAL_ROOT / "ui"

ROOTS = (LOCAL_UI_ROOT, LOCAL_ROOT, UI_ROOT)

_CVARS = re.compile(r"<c-vars\b(.*?)/>", re.DOTALL)
_COMMENT = re.compile(r"\{%\s*comment\s*%\}(.*?)\{%\s*endcomment\s*%\}", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)

# Exclude with and for bindings from slot detection: they use the same placeholder
# syntax as public slots.
_WITH = re.compile(r"\{%\s*with\s+([^%]*?)%\}")
_WITH_NAME = re.compile(r"([a-z_][a-z0-9_]*)\s*=", re.IGNORECASE)
_FOR = re.compile(r"\{%\s*for\s+(.+?)\s+in\s", re.DOTALL)

# Names that appear as {{ ... }} but are Cotton machinery rather than a slot.
_NOT_SLOTS = {"attrs", "class", "slot"}


@dataclass(frozen=True)
class Prop:
    name: str
    default: str
    """Rendered default, or "" for a bare flag."""

    dynamic: bool
    """Declared as ``:name=`` — the value is a Python literal, not a string."""

    @property
    def is_flag(self) -> bool:
        return self.default == ""

    @property
    def choices(self) -> tuple[str, ...]:
        """Top-level keys of a dictionary default. Nested dictionaries describe separate
        dimensions and do not add choices here.
        """
        if not (self.dynamic and self.default.startswith("{")):
            return ()
        # Track nesting depth so only top-level dictionary keys become choices.
        keys: list[str] = []
        depth = 0
        for match in re.finditer(r"['\"]([\w-]+)['\"]\s*(:)|([{}\[\]])", self.default):
            if bracket := match.group(3):
                depth += 1 if bracket in "{[" else -1
            elif match.group(2) and depth == 1:
                keys.append(match.group(1))
        return tuple(dict.fromkeys(keys))


@dataclass(frozen=True)
class ComponentApi:
    path: Path
    props: tuple[Prop, ...]
    doc: str
    slots: tuple[str, ...]

    @property
    def is_local(self) -> bool:
        """True for this project's own components, False for the kit's."""
        return self.path.is_relative_to(LOCAL_ROOT)

    @property
    def source_label(self) -> str:
        """Template path displayed as the source of the component API."""
        root = LOCAL_ROOT if self.is_local else UI_ROOT
        return str(self.path.relative_to(root))

    @property
    def enums(self) -> dict[str, tuple[str, ...]]:
        """Infer selector choices from dictionary defaults. Match each selector's default
        value to a dictionary's top-level keys, independently of property naming.
        """
        selectors = [
            p
            for p in self.props
            if not p.is_flag and p.default not in {"True", "False"}
        ]
        found: dict[str, tuple[str, ...]] = {}
        for prop in self.props:
            choices = prop.choices
            if not choices:
                continue
            for selector in selectors:
                if selector.name != prop.name and selector.default in choices:
                    found.setdefault(selector.name, choices)
                    break
        return found


def _split_attributes(text: str) -> list[tuple[str, str]]:
    """Parse a c-vars body into name and raw-value pairs. Scan quoted values so nested
    punctuation and the other quote character remain intact.
    """
    pairs: list[tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        if not (text[i].isalpha() or text[i] in ":_"):
            i += 1
            continue
        start = i
        while i < n and (text[i].isalnum() or text[i] in ":_-."):
            i += 1
        name = text[start:i]
        while i < n and text[i].isspace():
            i += 1
        if i < n and text[i] == "=":
            i += 1
            while i < n and text[i].isspace():
                i += 1
            if i < n and text[i] in "\"'":
                quote = text[i]
                i += 1
                value_start = i
                while i < n and text[i] != quote:
                    i += 1
                pairs.append((name, text[value_start:i]))
                i += 1
                continue
            value_start = i
            while i < n and not text[i].isspace():
                i += 1
            pairs.append((name, text[value_start:i]))
            continue
        pairs.append((name, ""))
    return pairs


def _normalise(value: str) -> str:
    """Collapse whitespace in a default value for display."""
    return re.sub(r"\s+", " ", value).strip()


@cache
def _read(relative: str) -> ComponentApi | None:
    path = next(
        (root / relative for root in ROOTS if (root / relative).is_file()), None
    )
    if path is None:
        return None
    raw = path.read_text()

    props: list[Prop] = []
    if match := _CVARS.search(raw):
        # Strip comments before parsing c-vars; prose would create false props and hide
        # slots with matching names.
        for name, value in _split_attributes(_COMMENT.sub("", match.group(1))):
            dynamic = name.startswith(":")
            props.append(
                Prop(name=name.lstrip(":"), default=_normalise(value), dynamic=dynamic)
            )

    doc = ""
    if match := _COMMENT.search(raw):
        doc = "\n".join(line.strip() for line in match.group(1).strip().splitlines())

    body = raw[match.end() :] if (match := _CVARS.search(raw)) else raw
    local = {
        name for block in _WITH.findall(body) for name in _WITH_NAME.findall(block)
    } | {
        target.strip()
        for targets in _FOR.findall(body)
        for target in targets.split(",")
        if target.strip().isidentifier()
    }
    declared = {p.name for p in props} | _NOT_SLOTS | local
    slots = tuple(
        sorted({n for n in _PLACEHOLDER.findall(body) if n not in declared}),
    )

    return ComponentApi(path=path, props=tuple(props), doc=doc, slots=slots)


def api_for(relative: str) -> ComponentApi | None:
    """Read the API for a relative template path, such as button.html or
    accordion/index.html.
    """
    if settings.DEBUG:
        _read.cache_clear()
    return _read(relative)


_REACT_TAG = re.compile(r"\{%\s*react_(?:island|host)\b")
_COTTON_TAG = re.compile(r"<c-([\w.-]+)")


def _tag_template(tag: str) -> str:
    """``ui.switch.impl`` -> ``switch/impl``; ``n26.pick-list.box`` -> ``n26/pick_list/box``."""
    name = tag.removeprefix("ui.")
    return name.replace(".", "/").replace("-", "_")


@cache
def _mounts_react(relative: str) -> bool:
    path = next(
        (root / relative for root in ROOTS if (root / relative).is_file()), None
    )
    if path is None:
        return False
    source = path.read_text()
    if _REACT_TAG.search(source):
        return True
    # Follow subcomponents only within this component's folder. The shared n26 directory
    # contains unrelated components.
    parent = relative.rsplit("/", 1)[0] if "/" in relative else ""
    if parent in ("", "n26"):
        return False
    folder = parent + "/"
    for tag in _COTTON_TAG.findall(source):
        stem = _tag_template(tag)
        if not stem.startswith(folder):
            continue
        for candidate in (f"{stem}.html", f"{stem}/index.html"):
            if candidate != relative and _mounts_react(candidate):
                return True
    return False


def mounts_react(relative: str) -> bool:
    """Whether the template that renders ``relative`` mounts a React island."""
    if settings.DEBUG:
        _mounts_react.cache_clear()
    return _mounts_react(relative)


def kit_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("django-cotton-ui")
    except PackageNotFoundError:  # pragma: no cover - installed by definition
        return "unknown"
