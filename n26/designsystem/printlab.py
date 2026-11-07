"""Build database-free print specimens and parse their URL options. The lab previews the
real sheet in an iframe and exposes the same URL for phones and PDF rendering.

Specimens cover fixed-height cards, multi-page tables, worksheets and overflowing
content.
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

#: Portrait dimensions in millimetres for the geometry readout. Tests compare them with
#: print.css, which supplies the rendered page sizes.
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
    """Parse sheet options from the query string. Use defaults for unrecognised choices,
    failed numeric conversion and NaN; clamp numeric values to their bounds.
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
            # The stylesheet defines end-of-row rules for at most six columns.
            columns=int(_number(get("columns"), 2, low=1, high=6)),
            gutter_mm=_number(get("gutter"), 4.0, low=0.0, high=20.0),
            # Zero omits the height prop, allowing content to determine card height.
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
        """Card width using the same gutter calculation as print.css."""
        gutters = (self.columns - 1) * self.gutter_mm
        return (self.content_w_mm - gutters) / self.columns

    @property
    def rows_per_page(self) -> int | None:
        """Number of complete card rows per page, or None for auto-height cards."""
        if not self.card_h_mm:
            return None
        # The final row needs no trailing gutter, so add one gutter before dividing by
        # the row pitch.
        pitch = self.card_h_mm + self.gutter_mm
        return max(0, int((self.content_h_mm + self.gutter_mm) // pitch))

    @property
    def per_page(self) -> int | None:
        rows = self.rows_per_page
        return None if rows is None else rows * self.columns

    @property
    def query(self) -> str:
        """Serialise sheet options for the preview URL."""
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
    # Reject NaN explicitly because its comparisons do not reliably clamp it.
    if number != number:
        return fallback
    return max(low, min(high, number))


def _trim(number: float) -> str:
    """6.0 -> "6", 5.5 -> "5.5". Keeps hand-edited URLs readable."""
    return f"{number:g}"


# ------------------------------------------------------------------ specimens


# Re-export core printing helpers for lab callers; core printing cannot depend on the
# gallery.


def specimen_cards(count: int) -> list:
    """Build sample cards with varied names, ratings and weapon counts to exercise tiling
    without a database.
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
        # Vary weapon counts to exercise rows of different heights.
        keep = 1 + (index % len(base.weapons))
        cards.append(
            replace(base, name=name, rating=rating, weapons=base.weapons[:keep])
        )
    return cards


def stress_cards(count: int) -> list:
    """Build cards with long names and repeated details to exercise overflow and shrink-to-
    fit.
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


#: Preassign worksheet labels to their display columns.
WORKSHEET_LEFT = ["Type", "Skills", "Gear"]
WORKSHEET_RIGHT = ["Cost", "Weapons", "Rules"]


# -------------------------------------------------------------------- context


#: Keep the table multi-page independently of the card count control so repeated headers
#: remain testable.
TABLE_REPEATS = 4


def table_rows() -> list[dict]:
    """Repeat the flattened sample catalogue to span multiple pages."""
    flat = [
        {
            "name": line.name,
            "category": category.name,
            "price": line.credits,
            # Display exclusive availability as E, matching the catalogue.
            "availability": "E" if line.is_exclusive else line.trade_points,
        }
        for section in sampledata.trading_post().sections
        for category in section.categories
        for line in category.lines
    ]
    return flat * TABLE_REPEATS


def sheet_context(options: Options) -> dict:
    """Prepare specimen data, detail columns and CSS lengths for the sheet template.
    Represent zero card height as an empty prop so the component uses auto height.
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
        "blanks": range(options.count),
        "table_rows": table_rows(),
        "specimen_template": f"designsystem/print/_{options.specimen}.html",
        "margin_css": f"{_trim(options.margin_mm)}mm",
        "gutter_css": f"{_trim(options.gutter_mm)}mm",
        "card_height_css": (
            f"{_trim(options.card_h_mm)}mm" if options.card_h_mm else ""
        ),
    }
