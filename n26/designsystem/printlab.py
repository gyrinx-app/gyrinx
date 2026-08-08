"""The print lab: a harness for finding out what a page actually does.

Print is the one part of the system you cannot check by looking at it. The
failures are specific to a medium the browser only enters when asked, and the
worst of them — a card sliced across the fold, a two-column block collapsed to
one — happen on engines that are not the one you are developing in. v1 found
every one of its print bugs through a lab like this and none of them by reading
the CSS, which is the argument for building it before needing it.

So: a page of controls, a live preview of the real sheet in an iframe, and a
direct URL for the sheet on its own. The direct URL is the load-bearing part.
It is what you open on a phone, what you hand to headless Chrome to make a PDF,
and what a simulator loads — every control is a query parameter precisely so
that the thing under test can be addressed from outside the browser you are
sitting in.

The specimens are chosen to break things rather than to look good: a fixed-size
card that content can overflow, a table long enough to cross pages, a worksheet
of write-in boxes, and a stress case with the longest content the components
will ever be handed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from n26.core.printing import (  # noqa: F401 — re-exported for the lab's callers
    DetailGroup,
    balance_columns,
    detail_columns,
    detail_groups,
    estimate_lines,
)

from . import sampledata

# ---------------------------------------------------------------------- paper

#: Page sizes in millimetres, portrait.
#:
#: These same numbers are in print.css, keyed off data-page, and that is where
#: rendering reads them — a component has to work without a view behind it. This
#: copy exists for the readout, which needs arithmetic a stylesheet cannot do.
#: Two copies of one fact is a drift risk, so a test parses the stylesheet and
#: asserts they still agree.
PAGE_SIZES = {
    "a4": (210.0, 297.0),
    "a5": (148.0, 210.0),
    "letter": (215.9, 279.4),
}

PAGES = [("a4", "A4"), ("a5", "A5"), ("letter", "Letter")]
ORIENTATIONS = [("portrait", "Portrait"), ("landscape", "Landscape")]

SPECIMENS = [
    ("cards", "Fighter cards — fixed size, tiled"),
    ("worksheet", "Blank worksheet — write-in fields"),
    ("table", "Long table — crosses pages"),
    ("mixed", "Mixed — cards, a forced break, then a table"),
    ("stress", "Stress — overlong content in fixed boxes"),
]

_SPECIMEN_KEYS = {key for key, _ in SPECIMENS}


# ------------------------------------------------------------------- controls


@dataclass(frozen=True)
class Options:
    """Everything the sheet renders from, parsed and clamped.

    Every field comes off the query string, so every field has to survive
    whatever is in the query string. Clamped rather than rejected: a lab that
    404s on a typo in a URL you are hand-editing on a phone is a lab you stop
    using.
    """

    specimen: str = "cards"
    page: str = "a4"
    orientation: str = "portrait"
    margin_mm: float = 6.0
    columns: int = 2
    gutter_mm: float = 4.0
    card_h_mm: float = 110.0
    count: int = 8
    paged: bool = False
    grid: bool = False
    fit: bool = True
    auto_print: bool = False

    @classmethod
    def from_request(cls, request) -> Options:
        get = request.GET.get
        return cls(
            specimen=_one_of(get("specimen"), _SPECIMEN_KEYS, "cards"),
            page=_one_of(get("page"), PAGE_SIZES, "a4"),
            orientation=_one_of(
                get("orientation"), {"portrait", "landscape"}, "portrait"
            ),
            margin_mm=_number(get("margin"), 6.0, low=0.0, high=40.0),
            # Six is where the CSS stops, because the end-of-row rule is written
            # out per column count. Clamping here means the two agree.
            columns=int(_number(get("columns"), 2, low=1, high=6)),
            gutter_mm=_number(get("gutter"), 4.0, low=0.0, high=20.0),
            # Zero is not a small card, it is the auto-height card — the prop is
            # simply left off, and the card is as tall as its content.
            card_h_mm=_number(get("cardh"), 110.0, low=0.0, high=400.0),
            count=int(_number(get("count"), 8, low=1, high=60)),
            paged=get("paged") == "1",
            grid=get("grid") == "1",
            fit=get("fit", "1") == "1",
            auto_print=get("print") == "1",
        )

    # --- derived geometry, for the readout -------------------------------

    @property
    def page_mm(self) -> tuple[float, float]:
        width, height = PAGE_SIZES[self.page]
        return (height, width) if self.orientation == "landscape" else (width, height)

    @property
    def content_w_mm(self) -> float:
        return self.page_mm[0] - 2 * self.margin_mm

    @property
    def content_h_mm(self) -> float:
        return self.page_mm[1] - 2 * self.margin_mm

    @property
    def cell_w_mm(self) -> float:
        """What one card comes out as. The same sum print.css does in calc()."""
        gutters = (self.columns - 1) * self.gutter_mm
        return (self.content_w_mm - gutters) / self.columns

    @property
    def rows_per_page(self) -> int | None:
        """How many rows of cards fit before the fold. None if they are not
        a fixed height, in which case nobody can say."""
        if not self.card_h_mm:
            return None
        # The last row on a page needs no gutter under it, so the space to
        # divide is one gutter more than the page.
        pitch = self.card_h_mm + self.gutter_mm
        return max(0, int((self.content_h_mm + self.gutter_mm) // pitch))

    @property
    def per_page(self) -> int | None:
        rows = self.rows_per_page
        return None if rows is None else rows * self.columns

    @property
    def query(self) -> str:
        """The options as a query string, so the sheet URL mirrors the form."""
        pairs = {
            "specimen": self.specimen,
            "page": self.page,
            "orientation": self.orientation,
            "margin": _trim(self.margin_mm),
            "columns": self.columns,
            "gutter": _trim(self.gutter_mm),
            "cardh": _trim(self.card_h_mm),
            "count": self.count,
            "paged": "1" if self.paged else "0",
            "grid": "1" if self.grid else "0",
            "fit": "1" if self.fit else "0",
        }
        return "&".join(f"{key}={value}" for key, value in pairs.items())


def _one_of(value, allowed, fallback):
    return value if value in allowed else fallback


def _number(value, fallback, low, high):
    try:
        number = float(value)
    except TypeError, ValueError:
        return fallback
    # NaN fails every comparison, so it would sail through a min/max clamp.
    if number != number:
        return fallback
    return max(low, min(high, number))


def _trim(number: float) -> str:
    """6.0 -> "6", 5.5 -> "5.5". Keeps hand-edited URLs readable."""
    return f"{number:g}"


# ------------------------------------------------------------------ specimens


# DetailGroup, detail_groups and detail_columns live in n26.core.printing —
# the real print pages need them, and core cannot import the gallery. The
# names are re-exported here so the lab's templates and context read the
# same either way.


def specimen_cards(count: int) -> list:
    """``count`` fighter cards, varied enough to be worth tiling.

    One real card from the sample data, then variations on it: different names
    and costs so a page of them does not read as a printing error, and different
    weapon counts so the cards are not all the same height. Nothing here needs a
    database — a gallery has to render on an empty one.
    """
    base = sampledata.model_card()
    names = [
        ("Escher Gang Queen", 135),
        ("Vesna Krail", 95),
        ("Dust", 60),
        ("Mireille 'Sparks' Ott", 110),
        ("Ninefingers", 75),
        ("Sable", 120),
        ("Corva Ilse", 88),
        ("The Quiet One", 145),
    ]
    cards = []
    for index in range(count):
        name, rating = names[index % len(names)]
        # Vary the weapon count so rows differ in height on an auto-height card,
        # which is where a tiling bug shows itself.
        keep = 1 + (index % len(base.weapons))
        cards.append(
            replace(base, name=name, rating=rating, weapons=base.weapons[:keep])
        )
    return cards


def stress_cards(count: int) -> list:
    """The same cards, loaded with everything at once.

    A name that cannot fit on one line, every weapon, and enough skills and gear
    to overflow a fixed-height card — which is the case the shrink-to-fit script
    exists for, and the case that clips visibly when it is switched off.
    """
    base = sampledata.model_card()
    long_name = "Maximilian Aurelius Thunderbolt III, the Unrelenting"
    padded = replace(
        base,
        name=long_name,
        skills=base.skills * 4,
        equipment=base.equipment * 4,
    )
    return [padded for _ in range(count)]


#: The labels on a blank card, already dealt into the two columns.
#:
#: Dealt here rather than in the template because a template can only split a
#: list by testing forloop.counter against divisibleby, which reads as
#: arithmetic and hides what is actually a layout decision.
WORKSHEET_LEFT = ["Type", "Skills", "Gear"]
WORKSHEET_RIGHT = ["Cost", "Weapons", "Rules"]


# -------------------------------------------------------------------- context


#: How many times the sample catalogue is repeated for the table specimen.
#:
#: Fixed rather than driven by the count control, because "crosses several
#: pages" is what this specimen is *for* — a header that repeats correctly is
#: not something you can observe on a table that fits on one page, so the
#: specimen has to guarantee it does not.
TABLE_REPEATS = 4


def table_rows() -> list[dict]:
    """The sample catalogue, flattened and repeated until it needs pages."""
    flat = [
        {
            "name": line.name,
            "category": category.name,
            "cost": line.credits,
            # Exclusive prints "E", not a number, because it is not one — see
            # <c-n26.collection-picker.item> and n26.browse.narrow.
            "availability": "E" if line.is_exclusive else line.trade_points,
        }
        for section in sampledata.trading_post().sections
        for category in section.categories
        for line in category.lines
    ]
    return flat * TABLE_REPEATS


def sheet_context(options: Options) -> dict:
    """Everything the sheet template renders from.

    Each card arrives with its detail columns already worked out, because the
    split is a Python decision (see n26.printing) and a template cannot call a
    function with an argument to ask for it.

    The lengths are pre-formatted as CSS strings rather than passed as numbers
    with the unit appended in the template. A card height of zero has to reach
    the component as an *absent* prop — the auto-height card is the one with no
    height at all, not the one with a height of 0mm — and "" is how a Cotton
    prop is absent.
    """
    if options.specimen == "stress":
        cards = stress_cards(options.count)
    elif options.specimen in {"cards", "mixed"}:
        cards = specimen_cards(options.count)
    else:
        cards = []

    return {
        "options": options,
        "rows": [{"card": card, "columns": detail_columns(card)} for card in cards],
        "worksheet_left": WORKSHEET_LEFT,
        "worksheet_right": WORKSHEET_RIGHT,
        # The blank cards have no data behind them, so the only thing that says
        # how many to draw is the count.
        "blanks": range(options.count),
        "table_rows": table_rows(),
        "specimen_template": f"designsystem/print/_{options.specimen}.html",
        # CSS lengths, ready to hand to a component.
        "margin_css": f"{_trim(options.margin_mm)}mm",
        "gutter_css": f"{_trim(options.gutter_mm)}mm",
        "card_height_css": (
            f"{_trim(options.card_h_mm)}mm" if options.card_h_mm else ""
        ),
    }
