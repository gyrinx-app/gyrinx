"""Read the component API straight out of the installed django-cotton-ui templates.

A Cotton component declares its public props in a ``<c-vars/>`` block at the top
of its template, and most of the kit's components follow it with a
``{% comment %}`` block explaining themselves. Both are better documentation than
anything kept by hand in this app, because they ship with the version actually
installed — upgrade the package and the reference page follows.

So nothing here is transcribed. The gallery's prop tables and descriptions are
parsed, at runtime, from::

    .venv/.../django_cotton_ui/templates/cotton/ui/**/*.html
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

# This project's own Cotton components, which are documented exactly the same way:
# they declare <c-vars> and explain themselves in a {% comment %}, so the gallery
# reads them rather than being told about them. They live in the core app's
# template tree — the edition mounts inside a larger repository, so BASE_DIR is
# that repository's root, not the edition's.
LOCAL_ROOT = Path(settings.BASE_DIR) / "n26" / "core" / "templates" / "cotton"

# Our overrides of *kit* components. A kit component is asked for by a bare name
# ("button.html") because UI_ROOT already ends in ui/, so this is the same name
# under our own ui/ — and it has to be searched first, because that is the order
# Django resolves them in and therefore which file actually renders.
#
# This root did not exist before, on the reasoning that the namespaces (ui/… and
# n26/…) could not collide. They can and they do: templates/cotton/ui/ holds four
# overrides now, and colliding is the entire point of one. Without this the
# gallery read the kit's copy of a template it does not render — c-ui.button's
# prop table listed six variants while seven worked, and error, label and
# description have been documented from the wrong file since the day they were
# overridden.
LOCAL_UI_ROOT = LOCAL_ROOT / "ui"

ROOTS = (LOCAL_UI_ROOT, LOCAL_ROOT, UI_ROOT)

_CVARS = re.compile(r"<c-vars\b(.*?)/>", re.DOTALL)
_COMMENT = re.compile(r"\{%\s*comment\s*%\}(.*?)\{%\s*endcomment\s*%\}", re.DOTALL)
_PLACEHOLDER = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}", re.IGNORECASE)

# A slot is read as a bare {{ name }}, but so is any name the template binds
# itself — {% with row_class="…" %} and {% for pos, classes in … %}. Those look
# identical from the outside and are not part of the component's API.
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
        """Top-level keys of a dict-valued default, which is how the kit spells an enum.

        ``:variants="{'default': ..., 'primary': ...}"`` on a component with a
        ``variant`` prop means variant accepts exactly those keys. Only depth-1 keys
        count: alert's ``:styles`` nests appearance over variant
        (``{'soft': {'info': ...}}``) and the two levels are different props.
        """
        if not (self.dynamic and self.default.startswith("{")):
            return ()
        # Walk the literal so nesting depth is tracked alongside the keys.
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
        """Where the props on this page were read from, as shown to the reader."""
        root = LOCAL_ROOT if self.is_local else UI_ROOT
        return str(self.path.relative_to(root))

    @property
    def enums(self) -> dict[str, tuple[str, ...]]:
        """Prop name -> allowed values, recovered from the kit's lookup-dict idiom.

        The kit spells an enum as a plain prop holding the chosen key
        (``variant="primary"``) plus a dict prop mapping every key to classes
        (``:variants="{'primary': ...}"``). The reliable link between the two is the
        *value*, not the name: whichever prop's default appears among a dict's
        top-level keys is the prop that dict enumerates. That handles the naming
        variations (``variants`` / ``size_classes`` / ``icon_paths``) and alert's
        two-level ``:styles`` without special-casing any of them.
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
    """Tokenise a ``<c-vars>`` body into (name, raw_value) pairs.

    Values are quoted but routinely contain commas, braces, newlines and the other
    quote character (``:variants="{'a': 'b'}"``), so this walks the string rather
    than trying to be a regex.
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
    """Collapse a multi-line dict/list default onto one line for display."""
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
        # A {% comment %} inside the <c-vars> block is prose about the props
        # around it, and a perfectly ordinary thing to write. Left in, every
        # word of it is tokenised as a prop: one component published forty-three
        # of them, including "and", "from" and "endcomment". Worse than the
        # noise, a phantom silently eats the real slot of the same name — the
        # word "empty" in a sentence is why that component's `empty` slot went
        # undocumented — because a name counted as declared is a name the slot
        # scan below then skips.
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
    """``api_for("button.html")``, ``api_for("accordion/index.html")``."""
    if settings.DEBUG:
        _read.cache_clear()
    return _read(relative)


def kit_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("django-cotton-ui")
    except PackageNotFoundError:  # pragma: no cover - installed by definition
        return "unknown"
