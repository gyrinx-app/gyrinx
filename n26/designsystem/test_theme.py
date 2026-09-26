"""The theme class must also name a colour scheme.

Browsers paint native scrollbars, form controls and selection colours from
`color-scheme`, not from the `dark` class. The class re-themes tokens; without
a matching scheme the chrome stays light on a dark page.
"""

from pathlib import Path


def stylesheet() -> str:
    """The Tailwind input. The built file is generated and gitignored."""
    return (Path(__file__).resolve().parent / "assets" / "app.css").read_text()


class TestColourSchemeFollowsTheThemeClass:
    def test_the_light_root_declares_a_light_scheme(self):
        assert "color-scheme: light" in stylesheet()

    def test_the_dark_class_declares_a_dark_scheme(self):
        assert "color-scheme: dark" in stylesheet()
