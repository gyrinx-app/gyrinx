"""Read callout configuration separately from the sanitised rich-text HTML."""

import json
from html.parser import HTMLParser
from pathlib import Path

from n26.core.colours import GANG_COLOURS
from n26.core.templatetags.richtext import safe_rich_text

SCHEMA = json.loads((Path(__file__).parent / "src/callout-schema.json").read_text())
TYPES = {
    "info",
    "expanding-info",
    "carousel",
    "download",
    "link-cluster",
    "mail-link",
    "example",
}
ICONS = set(json.loads((Path(__file__).parent / "src/lucide-icons.json").read_text()))
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


def clean_rich(raw):
    """Restrict nested bodies to text, basic marks, paragraphs and lists."""
    count = 0
    characters = 0

    def visit(node, depth=0):
        nonlocal count, characters
        count += 1
        if not isinstance(node, dict) or depth > 12 or count > 2000:
            return None
        kind = node.get("type")
        if kind == "text":
            value = node.get("text")
            if not isinstance(value, str):
                return None
            value = value[: max(0, 12000 - characters)]
            characters += len(value)
            if not value:
                return None
            marks = node.get("marks", [])
            return {
                "type": "text",
                "text": value,
                "marks": [
                    {"type": mark["type"]}
                    for mark in marks
                    if isinstance(mark, dict)
                    and isinstance(mark.get("type"), str)
                    and mark["type"] in {"bold", "italic", "underline"}
                ]
                if isinstance(marks, list)
                else [],
            }
        if not isinstance(kind, str) or kind not in {
            "doc",
            "paragraph",
            "bulletList",
            "orderedList",
            "listItem",
            "hardBreak",
        }:
            return None
        if kind == "hardBreak":
            return {"type": kind}
        children = node.get("content", [])
        return {
            "type": kind,
            "content": [
                result for child in children if (result := visit(child, depth + 1))
            ]
            if isinstance(children, list)
            else [],
        }

    return visit(raw) if isinstance(raw, dict) and raw.get("type") == "doc" else None


def normalise(raw):
    if (
        not isinstance(raw, dict)
        or not isinstance(raw.get("type"), str)
        or raw["type"] not in TYPES
    ):
        raise ValueError("Unknown callout")
    config = {
        "type": raw["type"],
        "colour": raw.get("colour")
        if isinstance(raw.get("colour"), str) and raw["colour"] in GANG_COLOURS
        else "default",
        "icon": raw.get("icon")
        if isinstance(raw.get("icon"), str) and raw["icon"] in ICONS
        else "info",
        "striped": raw.get("striped") is True,
        "glow": raw.get("glow") is True,
    }
    for key, limit in SCHEMA["textLimits"].items():
        value = raw.get(key, "")
        config[key] = value[:limit] if isinstance(value, str) else ""
    config["bodyRich"] = clean_rich(raw.get("bodyRich"))
    config["detailRich"] = clean_rich(raw.get("detailRich"))
    for key, collection in SCHEMA["collections"].items():
        items = raw.get(key, [])
        config[key] = []
        if not isinstance(items, list):
            continue
        for item in items[: collection["limit"]]:
            if not isinstance(item, dict):
                continue
            entry = {
                field: item.get(field, "")[:limit]
                if isinstance(item.get(field), str)
                else ""
                for field, limit in collection["fields"].items()
            }
            if key == "slides":
                entry["bodyRich"] = clean_rich(item.get("bodyRich"))
            config[key].append(entry)
    if not config["slides"]:
        config["slides"] = [{"eyebrow": config["eyebrow"], "body": config["body"]}]
    return config


class CalloutParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.parts = []
        self.callouts = []
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if self.depth:
            if tag not in VOID:
                self.depth += 1
            return
        source = dict(attrs).get("data-html-block") if tag == "div" else None
        if source is not None:
            try:
                code = json.loads(source)
                if not isinstance(code, str) or len(code) > 100000:
                    raise ValueError("Invalid HTML block")
            except ValueError, TypeError:
                pass
            else:
                self.parts.append(
                    '<div class="html-block-preview">'
                    + str(safe_rich_text(code))
                    + "</div>"
                )
                self.depth = 1
                return
        raw = dict(attrs).get("data-callout") if tag == "aside" else None
        if raw and len(self.callouts) < 200:
            try:
                config = normalise(json.loads(raw))
            except ValueError, TypeError, KeyError:
                pass
            else:
                self.parts.append(
                    f'<div id="gyrinx-callout-{len(self.callouts)}"></div>'
                )
                self.callouts.append(config)
                self.depth = 1
                return
        self.parts.append(self.get_starttag_text())

    def handle_startendtag(self, tag, attrs):
        if not self.depth:
            self.parts.append(self.get_starttag_text())

    def handle_endtag(self, tag):
        if self.depth:
            if tag not in VOID:
                self.depth -= 1
        else:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.depth:
            self.parts.append(data)

    def handle_entityref(self, name):
        if not self.depth:
            self.parts.append(f"&{name};")

    def handle_charref(self, name):
        if not self.depth:
            self.parts.append(f"&#{name};")


def rendered_preview(html):
    parser = CalloutParser()
    parser.feed(html)
    return {
        "html": str(safe_rich_text("".join(parser.parts))),
        "callouts": parser.callouts,
    }
