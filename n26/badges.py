"""The badge beside a person's name, as data a React island can draw.

The platform decides which badge a person shows and holds its artwork, whether
committed with the app or uploaded. Templates draw that artwork inline with
``{% badge_svg %}``. An island cannot take markup, so this seam turns the
artwork into an element tree limited to the platform's SVG allowlist, and React
draws it as elements.
"""

import re
from html.parser import HTMLParser

from gyrinx.svg import SVG_ALLOWED_ATTRS, SVG_ALLOWED_TAGS

# HTMLParser lower-cases names, so map each back to the allowlist's spelling.
_TAGS = {tag.lower(): tag for tag in SVG_ALLOWED_TAGS}
_ATTRS = {
    name.lower(): name
    for names in SVG_ALLOWED_ATTRS.values()
    if not callable(names)
    for name in names
} | {"href": "href"}
# The tags an island may draw, for the browser's second check.
SVG_TAGS = sorted(SVG_ALLOWED_TAGS)
# Only these carry text worth keeping: an accessible name or a description.
_TEXT_TAGS = {"title", "desc"}


def _local(value):
    """Whether a paint or clip value refers only within the drawing."""
    lowered = value.lower()
    return "url(" not in lowered or lowered.strip().startswith("url(#")


def _allowed(tag, name, value):
    rule = SVG_ALLOWED_ATTRS.get(tag, SVG_ALLOWED_ATTRS["*"])
    if callable(rule):
        return rule(tag, name, value)
    return name in rule or name in SVG_ALLOWED_ATTRS["*"]


def _prop(name):
    """React's name for an SVG attribute: class becomes className, and
    stroke-width becomes strokeWidth."""
    if name == "class":
        return "className"
    return re.sub(r"-([a-z])", lambda match: match[1].upper(), name)


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = {"children": []}
        self.stack = [self.root]
        self.skipping = 0

    def _node(self, tag, attrs):
        name = _TAGS.get(tag)
        if name is None:
            return None
        props = {}
        for key, value in attrs:
            attr = _ATTRS.get(key)
            if (
                attr is not None
                and value is not None
                and _local(value)
                and _allowed(name, attr, value)
            ):
                # The allowlist judges a reference after trimming it; so does the island.
                props[_prop(attr)] = value.strip() if attr == "href" else value
        return {"tag": name, "props": props, "children": []}

    def handle_starttag(self, tag, attrs):
        node = None if self.skipping else self._node(tag, attrs)
        if node is None:
            self.skipping += 1
            return
        self.stack[-1]["children"].append(node)
        self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        node = None if self.skipping else self._node(tag, attrs)
        if node is not None:
            self.stack[-1]["children"].append(node)

    def handle_endtag(self, tag):
        if self.skipping:
            self.skipping -= 1
        elif len(self.stack) > 1 and self.stack[-1]["tag"] == _TAGS.get(tag):
            self.stack.pop()

    def handle_data(self, data):
        if not self.skipping and self.stack[-1].get("tag") in _TEXT_TAGS:
            if data.strip():
                self.stack[-1]["children"].append(data)


# The attributes an island may draw, under React's names.
SVG_PROPS = sorted({_prop(name) for name in _ATTRS.values()})


def svg_tree(markup):
    """The first ``<svg>`` in some markup as ``{tag, props, children}`` nodes,
    keeping only allowlisted tags and attributes; ``None`` if there is none."""
    parser = _Tree()
    parser.feed(markup)
    parser.close()
    return next(
        (node for node in parser.root["children"] if node["tag"] == "svg"), None
    )


def shown_badge(user):
    """The badge ``user`` shows beside their name, or ``None``.

    Reads the profile and the user's badge grants, so prefetch those when
    asking for many users.
    """
    from gyrinx.site.templatetags.badge_tags import badge_for

    return badge_for(user)


def badge_mark(badge):
    """A badge as ``{"label", "svg"}``: its accessible name and its artwork
    as a tree. ``None`` when its artwork has no ``<svg>``."""
    tree = svg_tree(badge.inline_svg())
    if tree is None:
        return None
    return {"label": badge.description, "svg": tree}
