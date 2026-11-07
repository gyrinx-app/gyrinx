"""Convert platform badge artwork into an allowlisted element tree for React islands. The
platform selects the account's badge; this module exports its SVG as data rather than
inserting markup.
"""

import re
from html.parser import HTMLParser

from gyrinx.svg import SVG_ALLOWED_ATTRS, SVG_ALLOWED_TAGS

# Restore allowlist casing after HTMLParser lowercases tag and attribute names.
_TAGS = {tag.lower(): tag for tag in SVG_ALLOWED_TAGS}
_ATTRS = {
    name.lower(): name
    for names in SVG_ALLOWED_ATTRS.values()
    if not callable(names)
    for name in names
} | {"href": "href"}
# Export tags for the browser's additional validation.
SVG_TAGS = sorted(SVG_ALLOWED_TAGS)
# Retain text only in SVG title and description elements.
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
    """Convert SVG attribute names to React props, including className and strokeWidth."""
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
                # Match reference validation by trimming href before passing it to
                # React.
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


# Export allowed attributes using React prop names.
SVG_PROPS = sorted({_prop(name) for name in _ATTRS.values()})


def svg_tree(markup):
    """Return the first root SVG as tag, props and children data, filtering tags and
    attributes through the platform allowlist. Return None when no root SVG survives.
    """
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
    """Return a badge's accessible label and SVG tree, or None if its artwork has no root
    SVG.
    """
    tree = svg_tree(badge.inline_svg())
    if tree is None:
        return None
    return {"label": badge.description, "svg": tree}
