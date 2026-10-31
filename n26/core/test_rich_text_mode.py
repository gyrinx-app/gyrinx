"""The rich text Edit and Preview switch, and the field it must leave alone.

The switch is a React island. The textarea stays in the form, outside that
island, because the island replaces its own contents and TinyMCE binds the
textarea that was in the page from the start. Without a field, the value is
still the sanitised article and there is no switch.
"""

import json

from bs4 import BeautifulSoup
from django import forms
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.templatetags.rich_text_mode import rich_text_mode_props
from n26.core.widgets import RichText


class Notes(forms.Form):
    notes = forms.CharField(widget=RichText(), required=False)


def render(source: str, **context) -> str:
    return Template(CottonCompiler().process(source)).render(Context(context))


def host(html: str):
    soup = BeautifulSoup(html, "html.parser")
    element = soup.select_one("[data-react-name='rich-text-mode']")
    assert element is not None
    return soup, element


class TestTheSwitch:
    def test_the_editor_stays_outside_the_island(self):
        html = render(
            '<c-n26.rich-text :field="form.notes" label="Notes" />',
            form=Notes(),
        )
        soup, element = host(html)
        assert element.find("textarea") is None
        editor = soup.select_one("[data-rich-text-editor] textarea")
        assert editor is not None
        assert editor["name"] == "notes"
        assert "tinymce" in editor["class"]
        assert soup.select_one("[data-rich-text-preview]").has_attr("hidden")
        assert "Nothing to preview yet." in html
        assert "x-data" not in html
        assert "x-html" not in html
        assert "x-show" not in html

    def test_the_fallback_names_edit_and_preview(self):
        html = render('<c-n26.rich-text :field="form.notes" />', form=Notes())
        soup, element = host(html)
        labels = [button.get_text(strip=True) for button in element.find_all("button")]
        assert labels == ["Edit", "Preview"]
        for button in element.find_all("button"):
            assert button["type"] == "button"
        props = json.loads(soup.find(id=element["data-react-props"]).string)
        assert props == {"initial": ""}

    def test_a_hostile_initial_value_is_sanitised_in_the_props(self):
        html = render(
            '<c-n26.rich-text :field="form.notes" :value="value" />',
            form=Notes(),
            value='<p>Kept</p><script>alert("x")</script>',
        )
        soup, element = host(html)
        props = json.loads(soup.find(id=element["data-react-props"]).string)
        assert props["initial"] == "<p>Kept</p>"
        assert "script" not in props["initial"]

    def test_without_the_switch_the_textarea_still_posts(self):
        html = render(
            '<c-n26.rich-text :field="form.notes" :toggle="False" />',
            form=Notes(),
        )
        soup = BeautifulSoup(html, "html.parser")
        assert soup.select_one("[data-react-name]") is None
        assert soup.find("textarea")["name"] == "notes"
        assert "Edit" not in html

    def test_a_saved_article_is_sanitised_and_has_no_switch(self):
        html = render(
            '<c-n26.rich-text :value="value" />',
            value='<p>Kept</p><script>alert("x")</script><img src="x" onerror="alert(1)">',
        )
        assert "<p>Kept</p>" in html
        assert "<script" not in html
        assert "onerror" not in html
        assert "data-react-name" not in html
        assert "textarea" not in html


def test_the_props_tag_sanitises_its_initial_html():
    assert rich_text_mode_props(initial="<p>Hi</p>") == {"initial": "<p>Hi</p>"}
    assert rich_text_mode_props(initial="<script>alert(1)</script>") == {"initial": ""}
    assert rich_text_mode_props() == {"initial": ""}
