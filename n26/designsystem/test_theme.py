"""Verify that theme classes declare matching colour-scheme values for native browser
controls.
"""

from pathlib import Path


def stylesheet() -> str:
    """Read the Tailwind source; built stylesheets are generated and ignored."""
    return (Path(__file__).resolve().parent / "assets" / "app.css").read_text()


class TestColourSchemeFollowsTheThemeClass:
    def test_the_light_root_declares_a_light_scheme(self):
        assert "color-scheme: light" in stylesheet()

    def test_the_dark_class_declares_a_dark_scheme(self):
        assert "color-scheme: dark" in stylesheet()
