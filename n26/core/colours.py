"""The colours a gang may be given.

These are the colour picker's choices, and each names a Tailwind scale the
theme resolves. A gang's colour is drawn inside an inline style, so any value
outside this list is never drawn.
"""

GANG_COLOURS = (
    "ink",
    "red",
    "orange",
    "amber",
    "yellow",
    "lime",
    "green",
    "emerald",
    "teal",
    "cyan",
    "sky",
    "blue",
    "indigo",
    "violet",
    "purple",
    "fuchsia",
    "pink",
    "rose",
)


def palette_colour(value):
    """The value when it is one of the gang colours, otherwise empty."""
    return value if value in GANG_COLOURS else ""
