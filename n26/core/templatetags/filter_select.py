"""Plain props for the searchable native-select island."""

from html.parser import HTMLParser

from django import template

register = template.Library()


class SelectParser(HTMLParser):
    """Read the first select as the browser control React will replace."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.select = None
        self.options = []
        self._in_select = False
        self._option = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "select" and self.select is None:
            self.select = attributes
            self._in_select = True
        elif tag == "option" and self._in_select and self._option is None:
            self._option = attributes
            self._text = []

    def handle_data(self, data):
        if self._option is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self._option is not None:
            label = " ".join("".join(self._text).split())
            self.options.append(
                {
                    "value": self._option.get("value", label),
                    "label": label,
                    "selected": "selected" in self._option,
                    "disabled": "disabled" in self._option,
                }
            )
            self._option = None
            self._text = []
        elif tag == "select" and self._in_select:
            self._in_select = False


def _selected_like_a_browser(options, multiple):
    if multiple:
        return options
    selected = [index for index, option in enumerate(options) if option["selected"]]
    if selected:
        keep = selected[-1]
    else:
        keep = next(
            (index for index, option in enumerate(options) if not option["disabled"]),
            -1,
        )
    return [
        {**option, "selected": index == keep} for index, option in enumerate(options)
    ]


@register.simple_tag
def filter_select_props(markup, min_options=15, placeholder="", empty=""):
    """Return JSON-safe props when a native select is long enough to enhance."""
    parser = SelectParser()
    parser.feed(str(markup))
    if parser.select is None or len(parser.options) < int(min_options):
        return None

    attributes = parser.select
    multiple = "multiple" in attributes
    passthrough = {
        name: value or ""
        for name, value in attributes.items()
        if name.startswith("data-")
    }
    return {
        "name": attributes.get("name", ""),
        "id": attributes.get("id", ""),
        "multiple": multiple,
        "required": "required" in attributes,
        "disabled": "disabled" in attributes,
        "attrs": passthrough,
        "options": _selected_like_a_browser(parser.options, multiple),
        "placeholder": str(placeholder),
        "empty": str(empty),
    }
