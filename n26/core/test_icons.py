"""The Lucide resolver and the stable n26 icon component."""

from pathlib import Path

import pytest
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core import icons


def render(source: str) -> str:
    """Compile a Cotton call site before rendering it from a string."""

    return Template(CottonCompiler().process(source)).render(Context())


class TestTheLibrary:
    def test_it_has_the_breadth_promised_by_the_design_library(self):
        assert len(icons.names()) >= 1700
        assert {"circle-check", "skull", "zoom-out"} <= set(icons.names())

    def test_every_installed_drawing_passes_the_inline_svg_contract(self):
        assert all(icons.resolve(name).body for name in icons.names())

    def test_svg_shapes_other_than_paths_survive(self):
        assert "<rect" in str(icons.resolve("dice-6").body)
        assert "<circle" in str(icons.resolve("circle").body)

    @pytest.mark.parametrize("legacy, canonical", icons.ALIASES.items())
    def test_legacy_names_resolve_to_their_lucide_replacement(self, legacy, canonical):
        assert icons.resolve(legacy) == icons.resolve(canonical)

    def test_an_unknown_name_fails_with_the_local_place_to_choose_one(self):
        with pytest.raises(KeyError, match=r"/n26/design/c/icon/"):
            icons.resolve("not-an-icon")

    @pytest.mark.parametrize(
        ("name", "source", "message"),
        [
            (
                "wrong-canvas",
                '<svg viewBox="0 0 16 16"><path d="M0 0" /></svg>',
                "unexpected SVG canvas",
            ),
            (
                "unsupported-element",
                '<svg viewBox="0 0 24 24"><script /></svg>',
                "unsupported 'script' geometry",
            ),
            (
                "unsupported-attribute",
                '<svg viewBox="0 0 24 24"><path d="M0 0" onclick="alert(1)" /></svg>',
                "unsupported attributes: onclick",
            ),
            (
                "unsupported-fill",
                '<svg viewBox="0 0 24 24"><path d="M0 0" fill="red" /></svg>',
                "unsupported fill",
            ),
        ],
    )
    def test_unsupported_svg_content_is_rejected(
        self, monkeypatch, name, source, message
    ):
        class Archive:
            def read(self, filename):
                assert filename == f"{name}.svg"
                return source

        monkeypatch.setattr(icons, "_lucide_archive", Archive)

        with pytest.raises(ValueError, match=message):
            icons._lucide_body(name)


class TestBrandMarks:
    @pytest.mark.parametrize("name", ["github", "discord", "patreon"])
    def test_the_approved_marks_are_filled(self, name):
        icon = icons.resolve(name)
        assert icon.solid
        assert icon.brand

    def test_patreon_keeps_its_published_canvas(self):
        assert icons.resolve("patreon").viewbox == "0 0 1080 1080"


class TestTheComponent:
    def test_a_page_gets_only_the_drawing_it_asks_for(self):
        html = render('<c-n26.icon name="plus" class="size-4" />')
        assert str(icons.resolve("plus").body) in html
        assert str(icons.resolve("skull").body) not in html
        assert 'class="size-4"' in html

    def test_arbitrary_attributes_reach_the_svg(self):
        html = render('<c-n26.icon name="plus" data-purpose="test" x-show="open" />')
        assert 'data-purpose="test"' in html
        assert 'x-show="open"' in html

    def test_a_label_names_a_meaningful_icon(self):
        html = render('<c-n26.icon name="truck" label="Deliveries" />')
        assert 'role="img"' in html
        assert 'aria-label="Deliveries"' in html
        assert "aria-hidden" not in html

    def test_a_decorative_icon_is_hidden(self):
        html = render('<c-n26.icon name="truck" />')
        assert 'aria-hidden="true"' in html
        assert 'role="img"' not in html

    def test_literal_call_sites_use_canonical_lucide_names(self):
        root = Path(__file__).parents[1]
        legacy_names = set(icons.ALIASES)
        offenders = []
        for template in root.rglob("*.html"):
            source = template.read_text()
            offenders.extend(
                (template, name)
                for name in legacy_names
                if f'<c-n26.icon name="{name}"' in source
            )
        assert not offenders
