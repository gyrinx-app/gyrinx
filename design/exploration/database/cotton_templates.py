"""Render Cotton to inert trees; React owns the dynamic slots."""

from html.parser import HTMLParser

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "fragment", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, text):
        if text.strip():
            self.stack[-1]["children"].append(text)


def render(source, **context):
    return Tree(
        Template(CottonCompiler().process(source)).render(Context(context))
    ).root


def slot(name):
    return {"tag": "span", "attrs": {"data-cotton-slot": name}, "children": []}


def walk(node):
    if isinstance(node, str):
        return
    yield node
    for child in node["children"]:
        yield from walk(child)


def find(node, predicate):
    return next(n for n in walk(node) if predicate(n))
