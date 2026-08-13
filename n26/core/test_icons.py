"""The icon registry's contract, where it is not simply path data.

Everything in the set is a stroke on a 24 grid except the brand marks, and a
mark drawn with the wrong canvas or the wrong paint is not a smaller logo —
it is an empty box, or a clipped corner of one.
"""

from n26.core import icons


class TestTheCanvasAMarkIsDrawnOn:
    """Heroicons all share the 24 grid; a logo comes on its owner's."""

    def test_a_drawing_says_nothing_and_gets_the_house_grid(self):
        assert icons.viewbox("plus") == icons.DEFAULT_VIEWBOX == "0 0 24 24"

    def test_a_mark_published_on_its_own_canvas_keeps_it(self):
        assert icons.viewbox("patreon") == "0 0 1080 1080"

    def test_a_name_the_registry_never_heard_of_still_answers(self):
        """The lookup is total. A missing canvas would render an <svg>
        with no viewBox at all, which draws the top-left 24 pixels of a
        1080 drawing — an apparently blank icon rather than an error."""
        assert icons.viewbox("nonsense") == "0 0 24 24"


class TestWhichMarksAreFilled:
    """A logo is a shape. Stroked, it is a hollow outline of itself."""

    def test_every_brand_mark_is_solid(self):
        assert all(icons.is_solid(name) for name in ("github", "discord", "patreon"))

    def test_a_line_drawing_is_not(self):
        assert not icons.is_solid("pencil")

    def test_every_name_with_a_canvas_of_its_own_has_a_drawing(self):
        """A viewBox for a name the set does not hold is a line nothing
        reads, and it would keep on saying nothing after the drawing it
        was written for was renamed."""
        assert not set(icons.VIEWBOXES) - set(icons.ICONS)
