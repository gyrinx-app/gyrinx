"""Turn sanitised notification content into React-renderable text and elements."""

from html.parser import HTMLParser

from gyrinx.site.templatetags.platform_tags import safe_rich_text


def rich_text_nodes(value):
    class Parser(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.nodes = []
            self.stack = [(None, self.nodes)]

        def handle_starttag(self, tag, attrs):
            attributes = dict(attrs)
            # React requires a style object; the sanitizer already filtered CSS.
            style = {}
            for declaration in attributes.pop("style", "").split(";"):
                if ":" in declaration:
                    name, value = declaration.split(":", 1)
                    parts = name.strip().split("-")
                    style[parts[0] + "".join(part.title() for part in parts[1:])] = (
                        value.strip()
                    )
            if style:
                attributes["style"] = style
            for source, target in (
                ("class", "className"),
                ("colspan", "colSpan"),
                ("rowspan", "rowSpan"),
            ):
                if source in attributes:
                    attributes[target] = attributes.pop(source)
            node = {"tag": tag, "attrs": attributes, "children": []}
            self.stack[-1][1].append(node)
            if tag not in {"br", "img", "hr", "wbr", "col"}:
                self.stack.append((tag, node["children"]))

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

        def handle_endtag(self, tag):
            for i in range(len(self.stack) - 1, 0, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]
                    break

        def handle_data(self, data):
            self.stack[-1][1].append(data)

    parser = Parser()
    parser.feed(str(safe_rich_text(value)))
    return parser.nodes
