import html
import json

import bootstrap  # noqa: F401 -- configure the isolated Django environment first
from callout_preview import TYPES, clean_rich, normalise, rendered_preview

for kind in TYPES:
    config = {
        "type": kind,
        "colour": "violet",
        "icon": "info",
        "label": "<script>Text</script>",
        "body": '<img onerror="alert(1)" src="x">',
        "striped": True,
        "slides": [{"eyebrow": "First", "body": "First card"}],
        "links": [{"label": "Help", "href": "javascript:alert(1)"}],
    }
    source = f'<p>Before</p><aside data-callout="{html.escape(json.dumps(config), quote=True)}"><p>Fallback</p></aside><p>After</p><script>alert(1)</script>'
    result = rendered_preview(source)
    assert result["callouts"][0]["type"] == kind
    assert result["callouts"][0]["body"] == config["body"], (
        "Plain strings remain display text"
    )
    assert "<script" not in result["html"] and "<img" not in result["html"]
    assert (
        result["html"].index("Before")
        < result["html"].index("gyrinx-callout-0")
        < result["html"].index("After")
    )
for bad in ["null", "[]", '{"type":[]}', '{"type":"unknown"}']:
    result = rendered_preview(
        f'<aside data-callout="{html.escape(bad, quote=True)}"><p>Fallback</p></aside>'
    )
    assert result["callouts"] == [] and "Fallback" in result["html"]
result = rendered_preview(
    '<p>Plain &amp; safe</p><a href="javascript:alert(1)">bad</a>'
)
assert "Plain &amp; safe" in result["html"] and "javascript:" not in result["html"]
print(
    "Passed: callout extraction preserves order and settings; text and malformed configurations remain safe."
)


for name in ["compass", "arrow-down-wide-narrow", "lighthouse", "book-open"]:
    assert normalise({"type": "info", "icon": name})["icon"] == name
for name in ["unknown-icon", "<script>", None]:
    assert normalise({"type": "info", "icon": name})["icon"] == "info"


rich = {
    "type": "doc",
    "content": [
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": "<script>safe text</script>",
                    "marks": [
                        {"type": "bold"},
                        {"type": "link", "attrs": {"href": "javascript:alert(1)"}},
                    ],
                },
                {"type": "image", "attrs": {"src": "x"}},
            ],
        }
    ],
}
clean = clean_rich(rich)
assert clean["content"][0]["content"] == [
    {"type": "text", "text": "<script>safe text</script>", "marks": [{"type": "bold"}]}
]
assert normalise({"type": "info", "bodyRich": rich})["bodyRich"] == clean

assert normalise({"type": "info"})["glow"] is False
assert normalise({"type": "info", "glow": True})["glow"] is True
assert normalise({"type": "info", "glow": "true"})["glow"] is False

# Collection fields obey the same limits as the editor, even for malformed input.
config = normalise(
    {
        "type": "carousel",
        "slides": [{"eyebrow": "x" * 300, "body": "y" * 13000}],
        "links": [{"label": "x" * 300, "href": "y" * 3000}],
    }
)
assert len(config["slides"][0]["eyebrow"]) == 200
assert len(config["slides"][0]["body"]) == 12000
assert len(config["links"][0]["label"]) == 200
assert len(config["links"][0]["href"]) == 2000
assert normalise({"type": "info", "colour": [], "icon": {}})["icon"] == "info"
assert clean_rich({"type": "doc", "content": [{"type": []}]}) == {
    "type": "doc",
    "content": [],
}
# Compact settings retain compatibility with the original verbose format.
assert (
    normalise({"type": "info", "label": "Legacy text", "body": "Preserved"})["body"]
    == "Preserved"
)
print("Passed: shared field limits, compact settings and malformed field types.")

code = '<h2>HTML heading</h2><p><strong>HTML content</strong></p><script>alert(1)</script><img src="x" onerror="alert(1)"><iframe src="https://example.com"></iframe>'
result = rendered_preview(
    f'<p>Before HTML</p><div data-html-block="{html.escape(json.dumps(code), quote=True)}"><pre><code>Fallback</code></pre></div><p>After HTML</p>'
)
assert (
    "<h2>HTML heading</h2>" in result["html"]
    and "<strong>HTML content</strong>" in result["html"]
)
assert (
    "<script" not in result["html"]
    and "<iframe" not in result["html"]
    and "onerror" not in result["html"]
)
assert "Fallback" not in result["html"] and "html-block-preview" in result["html"]
assert (
    result["html"].index("Before HTML")
    < result["html"].index("HTML heading")
    < result["html"].index("After HTML")
)
for value in [None, {}, "x" * 100001]:
    result = rendered_preview(
        f'<div data-html-block="{html.escape(json.dumps(value), quote=True)}"><pre>Fallback</pre></div>'
    )
    assert "Fallback" in result["html"] and "html-block-preview" not in result["html"]
print(
    "Passed: HTML blocks render in order with safe markup and malformed-source fallback."
)
