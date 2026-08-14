"""Turning a catalogue row's tones into the button kit's colours.

A row says what an act *means* — the one the reader came to do, one that
takes a thing away, or one of the rarer rest. Which colour that is
belongs to the drawing, and this is the one place the two meet. Without
it every screen picks its own, and the first one to disagree makes Sell
a different red from the Sell on the screen beside it.

The surprise worth stating plainly: the affirmative tone renders
**green**, not the kit's `primary`. The edition's rule is that the
control which brings a thing into existence is green — a `success`
button ends a form, a `primary` one starts one — and a purchase ends
this form. A reader who came here wondering why `primary` is not blue
has their answer.

The rest of a row's acts are links into a confirmation and carry no
colour of their own: they sit in a menu, where a coloured item would be
shouting from inside a drawer.
"""

from django import template

from n26.core.listing import DANGER, PRIMARY, SECONDARY

register = template.Library()

TONE_VARIANTS = {
    PRIMARY: "success",
    DANGER: "danger",
    SECONDARY: "default",
}


@register.filter
def tone_variant(tone):
    """``{{ action.tone|tone_variant }}`` — the kit variant for a tone.

    An unknown tone draws the plain button rather than raising: a control
    nobody can find the colour for is still a control that has to work.
    """
    return TONE_VARIANTS.get(tone, "default")
