"""The theme token reference.

Names and intent are listed here; *values* are deliberately not. The page reads
each token's real value out of the browser with ``getComputedStyle``, so the
table shows what is actually in effect — including whatever you have just changed
in the playground, and correctly per light/dark mode.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Token:
    name: str
    purpose: str
    kind: str = "color"
    """color renders a swatch, font a specimen; length and shadow show the value."""


@dataclass(frozen=True)
class Bucket:
    name: str
    blurb: str
    tokens: tuple[Token, ...]


BUCKETS: tuple[Bucket, ...] = (
    Bucket(
        "Typography",
        (
            "Mynor, served by Typekit and loaded in the base template. It is set as "
            "--font-sans rather than as a font-family on body, because that is the "
            "token Tailwind's own --default-font-family points at — so one override "
            "moves the page default, every font-sans utility and everything the kit "
            "renders. No component names a typeface; they all inherit."
        ),
        (
            Token("--font-sans", "Everything, unless it is code.", kind="font"),
            Token(
                "--font-mono", "Code blocks, token names, class strings.", kind="font"
            ),
        ),
    ),
    Bucket(
        "Accent",
        "Your brand colour and the text that sits on it. Usually the only thing you "
        "must set.",
        (
            Token(
                "--color-accent",
                "Primary fills: solid buttons, active states, the progress bar.",
            ),
            Token(
                "--color-accent-content",
                "The hover step: a solid button's fill under the pointer.",
            ),
            Token(
                "--color-accent-foreground",
                "Text and icons drawn on top of an accent fill.",
            ),
            Token(
                "--color-accent-text",
                "The accent as words on the page — links, text buttons, a changed "
                "characteristic. A different shade from the fill, because a light "
                "accent that works as a surface is unreadable as text.",
            ),
            Token(
                "--color-accent-muted",
                'The off-accent fill used by controls set to :accent="False".',
            ),
        ),
    ),
    Bucket(
        "Ink",
        (
            "The neutral scale the whole kit is built from. It defaults to Tailwind's "
            "zinc, and is indirected precisely so you can retone every component "
            "without touching your own zinc-* usage."
        ),
        tuple(
            Token(f"--color-ink-{step}", f"Neutral step {step}.")
            for step in (50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950)
        ),
    ),
    Bucket(
        "Surfaces",
        (
            "Depth. --color-surface is derived, not set: it mixes --color-bg with "
            "white by --surface-level, so one percentage controls how far raised "
            "surfaces lift off the page in each mode."
        ),
        (
            Token("--color-bg", "The page behind everything."),
            Token(
                "--color-surface",
                "Raised fills: cards, dialogs, menus. Derived from bg + surface-level.",
            ),
            Token(
                "--surface-level",
                "How far surface lifts off bg. 100% in light, ~6% in dark.",
                kind="length",
            ),
            Token("--color-box-border", "The hairline on box-role surfaces."),
            Token(
                "--color-input-bg",
                "Form field fill. Transparent in light; lifted in dark.",
            ),
            Token(
                "--color-muted", "Secondary text: descriptions, meta lines, timestamps."
            ),
        ),
    ),
    Bucket(
        "Radius",
        (
            "Split by role rather than by size, and namespaced so it never collides "
            "with Tailwind's own --radius-md / --radius-lg or your rounded-* classes."
        ),
        (
            Token(
                "--radius-control",
                "Form controls: inputs, selects, segments.",
                kind="length",
            ),
            Token(
                "--radius-box",
                "Structural surfaces: cards, dialogs, menus.",
                kind="length",
            ),
            Token(
                "--radius-button",
                "Buttons. Follows control by default; raise it for pills.",
                kind="length",
            ),
        ),
    ),
    Bucket(
        "Elevation and focus",
        "Shadows, and the keyboard focus ring every interactive component shares.",
        (
            Token("--shadow-input", "Form field elevation.", kind="shadow"),
            Token("--shadow-box", "Card and dialog elevation.", kind="shadow"),
            Token("--focus-ring-width", "Ring thickness.", kind="length"),
            Token(
                "--focus-ring-offset",
                "Gap between the control and its ring.",
                kind="length",
            ),
            Token(
                "--focus-ring-color",
                "Ring colour. Follows the accent unless overridden.",
            ),
        ),
    ),
)


# One-click starting points. These are not a second theming engine: each is a set
# of values for the kit's own theme-builder widget, which the playground reaches
# into and drives. That way presets, the widget's own dials, its localStorage
# persistence and its CSS export all stay in agreement — one thing holds the
# current theme, and it is the widget.
#
# Keys and value formats therefore have to match the widget's Alpine state
# exactly: radii are CSS lengths, buttonRadius is "default" or "full", and
# darkDepth is the ink shade that drives --color-bg in dark mode.
PRESETS = (
    {
        "name": "Cotton",
        "note": "The kit's own look: teal on zinc, modest rounding.",
        "accent": "teal",
        "gray": "zinc",
        "radius": "0.375rem",
        "radiusBox": "0.5rem",
        "buttonRadius": "default",
        "focusRing": "3px",
        "surfaceDark": 6,
        "darkDepth": "950",
    },
    {
        "name": "Ledger",
        "note": "Indigo on cool slate with tight corners. Dense and businesslike.",
        "accent": "indigo",
        "gray": "slate",
        "radius": "0.25rem",
        "radiusBox": "0.375rem",
        "buttonRadius": "default",
        "focusRing": "3px",
        "surfaceDark": 5,
        "darkDepth": "900",
    },
    {
        "name": "Necromunda",
        "note": "Rust on warm taupe, square edges. For the rulebook side of this repo.",
        "accent": "orange",
        "gray": "taupe",
        "radius": "0",
        "radiusBox": "0",
        "buttonRadius": "default",
        "focusRing": "2px",
        "surfaceDark": 8,
        "darkDepth": "950",
    },
    {
        "name": "Meadow",
        "note": "Emerald on olive, generous rounding and pill buttons.",
        "accent": "emerald",
        "gray": "olive",
        "radius": "0.75rem",
        "radiusBox": "1.5rem",
        "buttonRadius": "full",
        "focusRing": "3px",
        "surfaceDark": 7,
        "darkDepth": "900",
    },
    {
        "name": "Orchid",
        "note": "Fuchsia on mauve, soft corners, surfaces well lifted in dark.",
        "accent": "fuchsia",
        "gray": "mauve",
        "radius": "0.5rem",
        "radiusBox": "1rem",
        "buttonRadius": "default",
        "focusRing": "4px",
        "surfaceDark": 12,
        "darkDepth": "950",
    },
    {
        "name": "Blueprint",
        "note": "Sky on mist with a loud focus ring, for auditing keyboard focus.",
        "accent": "sky",
        "gray": "mist",
        "radius": "0.375rem",
        "radiusBox": "0.5rem",
        "buttonRadius": "default",
        "focusRing": "4px",
        "surfaceDark": 6,
        "darkDepth": "800",
    },
)


# The specimen on the token page. Mynor is one variable face across this range, so
# these are weights of the same file rather than separate downloads.
WEIGHTS = (
    (300, "Light"),
    (400, "Regular"),
    (500, "Medium"),
    (600, "Semibold"),
    (700, "Bold"),
    (800, "Extrabold"),
    (900, "Black"),
)

SIZES = (
    ("text-xs", "The quick brown fox jumps over the lazy dog"),
    ("text-sm", "The quick brown fox jumps over the lazy dog"),
    ("text-base", "The quick brown fox jumps over the lazy dog"),
    ("text-lg", "The quick brown fox jumps"),
    ("text-2xl", "The quick brown fox"),
    ("text-4xl", "Underhive"),
)
