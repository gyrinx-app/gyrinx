"""Classic-mode print card data (#1726).

Maps Gyrinx's rich fighter data onto the *fixed* set of regions on a grimdark
"classic mode" card (100mm x 110mm). Shared by the real print flow
(:class:`~gyrinx.core.views.list.ListPrintView`) and the staff/dev Print Lab
(:mod:`gyrinx.core.views.print_lab`), so the card builder lives here rather than
in a debug view.

## Region -> data mapping

    NAME      <- fighter.name, fighter type, cost
    STATLINE  <- fighter.statline  (dynamic columns; every statline type supported)
    SAVE      <- fighter.save_roll if set, else the statline "save" column (else blank)
    WEAPONS   <- fighter.weapons_cached, flattened to rows (name, ranges, str/ap/d/am, traits)
    DETAIL    <- two balanced columns (Skills, Rules, Gear, then "other"):
                   Skills <- skilline_cached
                   Rules  <- ruleline
                   Gear   <- wargear_cached (general gear)
                   Other  <- wyrd / psyker powers + each special gear category
                             (Legendary Names, Status Items, ...), labelled
    XP        <- fighter.xp_current (bold value in the XP / Kills row)
    KILLS     <- blank write-in box (Gyrinx has no per-fighter kill counter)
    NOTES     <- fighter.notes (write-in box)
    INJURIES  <- fighter.injuries (write-in box under notes; blank when none)
    Dead reflects injury_state; long flowing text auto-shrinks to fit (JS).

Deliberately omitted (no region on the classic card): counters, advancement
detail, psyker discipline metadata (see #1726 discussion).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.utils.html import strip_tags

# --- Card dimensions (mm). The reference cards are exactly 100 x 110 mm. -----
CARD_W_MM = 100
CARD_H_MM = 110

# Background/theme options. Value -> label. Shared by the lab's texture switcher
# and the print-config theme picker.
THEMES = [
    ("blank", "Plate (blank)"),
    ("odd", "Plate (corner ornament, left)"),
    ("even", "Plate (corner ornament, right)"),
    ("paper_odd", "Paper 2026 (left)"),
    ("paper_even", "Paper 2026 (right)"),
    ("dark", "Rusted dark plate"),
]
DEFAULT_THEME = "blank"

# Roughly how many characters of value text fit on one line of one detail
# column. Feeds the column-balancing estimate only (see DetailGroup.height).
DETAIL_CHARS_PER_LINE = 28


# ---------------------------------------------------------------------------
# Normalised card data
# ---------------------------------------------------------------------------


@dataclass
class StatCell:
    """One column in the statline grid."""

    name: str
    value: str
    highlight: bool = False
    first_of_group: bool = False
    modded: bool = False


@dataclass
class DetailGroup:
    """One labelled row in the lower detail block (Skills / Rules / Gear / ...)."""

    label: str
    items: list[str] = field(default_factory=list)
    css_class: str = ""

    @property
    def text(self) -> str:
        return ", ".join(self.items)

    @property
    def height(self) -> int:
        """Rough rendered line count, used to balance the two detail columns.

        Only ever compared against other groups' estimates to pick a split
        point, so it needs to rank groups correctly rather than predict the
        real layout. A long label ("Legendary Names") wraps to one word per
        line (see the .cc-label rule), which can outgrow a short value.
        """
        body_lines = -(-len(self.text) // DETAIL_CHARS_PER_LINE)  # ceil
        return max(1, body_lines, len(self.label.split()))


@dataclass
class WeaponRow:
    """One flattened weapon-profile row."""

    name: str
    rng_s: str = ""
    rng_l: str = ""
    acc_s: str = ""
    acc_l: str = ""
    strength: str = ""
    ap: str = ""
    damage: str = ""
    ammo: str = ""
    traits: str = ""
    is_secondary: bool = False  # a named sub-profile of the weapon above


@dataclass
class ClassicCard:
    """Everything the classic card template needs, already resolved."""

    kind: str = "fighter"  # fighter | vehicle | crew | stash | blank
    name: str = ""
    subtitle: str = ""
    cost: str = ""
    stats: list[StatCell] = field(default_factory=list)
    save: str = ""
    weapons: list[WeaponRow] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    powers: list[str] = field(default_factory=list)  # wyrd / psyker powers
    wargear: list[str] = field(default_factory=list)
    # special gear categories (Legendary Names, Status Items, ...) each get
    # their own row: list of (category_label, [item names]).
    gear_categories: list = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    xp: str = ""
    # lasting injuries — shown in the "Injuries" row beneath Notes
    injuries: list[str] = field(default_factory=list)
    notes_lines: list[str] = field(default_factory=list)
    # fighter portrait (bottom-right); empty when the fighter has no image
    image_url: str = ""
    # condition markers (mostly fillable; a couple reflect real state)
    recovery: bool = False
    captured: bool = False
    dead: bool = False
    fighter_id: str = ""

    @property
    def detail_groups(self) -> list[DetailGroup]:
        """The lower detail block's rows, in reading order."""
        groups = [
            DetailGroup("Skills", self.skills, "cc-skills"),
            DetailGroup("Rules", self.rules, "cc-rules-q"),
            DetailGroup("Gear", self.wargear, "cc-wargear"),
        ]
        if self.powers:
            groups.append(DetailGroup("Wyrd Powers", self.powers, "cc-powers"))
        groups += [
            DetailGroup(label, list(items), "cc-gearcat")
            for label, items in self.gear_categories
        ]
        return groups

    @property
    def detail_columns(self) -> list[list[DetailGroup]]:
        """``detail_groups`` split into the card's two detail columns.

        This split is done here rather than by CSS multi-column layout because
        WebKit does not support a multi-column container nested inside another
        fragmentation context: when printing (where the page *is* a
        fragmentation context) iOS Safari collapses the block to a single
        full-width column, so cards printed from an iPhone lost the two-column
        detail layout entirely. Splitting server-side renders identically on
        screen and on paper, in every engine.

        Groups keep their reading order and are cut at one point, exactly as
        column-major flow would: column one takes the first N, column two the
        rest. The cut is the one that minimises the taller column, which is
        what multicol's balancing was doing for us.

        Blank (fillable) cards keep every group in one full-width column so
        their write-in boxes are as wide as possible. An empty column is never
        returned — each column is a flex item, so an empty one would still
        claim half the width.
        """
        groups = self.detail_groups
        if self.kind == "blank" or not groups:
            return [groups] if groups else []

        heights = [g.height for g in groups]
        total = sum(heights)
        best_split, best_tallest = len(groups), total
        run = 0
        # Prefer the largest qualifying left column on a tie, matching how
        # column-major flow fills column one before spilling into column two.
        for split in range(1, len(groups) + 1):
            run += heights[split - 1]
            tallest = max(run, total - run)
            if tallest <= best_tallest:
                best_split, best_tallest = split, tallest
        return [c for c in (groups[:best_split], groups[best_split:]) if c]


def _get(obj, name, default=""):
    """Fetch ``obj.name`` and call it if it's a zero-arg method.

    Several fighter/assignment accessors (``cost_display``, ``base_name``,
    ``statline`` on raw weapon profiles) are methods that Django templates
    auto-call. In Python we must call them ourselves.
    """
    value = getattr(obj, name, default)
    if callable(value):
        try:
            return value()
        except TypeError:
            return default
    return value if value is not None else default


def _weapon_rows(fighter) -> list[WeaponRow]:
    rows: list[WeaponRow] = []
    for assign in _get(fighter, "weapons_cached", []) or []:
        base_name = str(_get(assign, "base_name", "")).strip()
        profiles = _get(assign, "all_profiles_cached", []) or []
        for idx, profile in enumerate(profiles):
            stats = _get(profile, "statline", []) or []
            vals = [str(_get(s, "value", "")) for s in stats]
            vals = (vals + [""] * 8)[:8]
            traits = ", ".join(
                str(t) for t in (_get(profile, "traitline_cached", []) or [])
            )
            pname = str(_get(profile, "name", "") or "").strip()
            secondary = idx > 0 and bool(pname) and pname.lower() != "standard"
            if secondary:
                label = pname
            else:
                label = base_name or pname
            rows.append(
                WeaponRow(
                    name=label,
                    rng_s=vals[0],
                    rng_l=vals[1],
                    acc_s=vals[2],
                    acc_l=vals[3],
                    strength=vals[4],
                    ap=vals[5],
                    damage=vals[6],
                    ammo=vals[7],
                    traits=traits,
                    is_secondary=secondary,
                )
            )
    return rows


def _assign_name(assign) -> str:
    eq = getattr(assign, "equipment", None)
    base = _get(assign, "base_name", "") or (getattr(eq, "name", "") if eq else "")
    return str(base).strip()


def _wargear_names(fighter) -> list[str]:
    """General wargear (the plain 'Wargear' row) — de-duped display names."""
    seen: set[str] = set()
    out: list[str] = []
    for assign in _get(fighter, "wargear_cached", []) or []:
        n = _assign_name(assign)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _gear_categories(fighter):
    """Special gear categories, each as its own row.

    House-additional and category-restricted gear (e.g. Legendary Names, Status
    Items) come grouped by category. Rather than flatten them into the general
    Wargear row, keep each category as a labelled row: (category, [names]).
    """
    rows: list = []
    for source in (
        "house_additional_gearline_display",
        "category_restricted_gearline_display",
    ):
        try:
            lines = getattr(fighter, source, None) or []
        except Exception:
            lines = []
        for line in lines:
            if not isinstance(line, dict):
                continue
            names = [
                n for n in (_assign_name(a) for a in line.get("assignments", [])) if n
            ]
            if names:
                rows.append((str(line.get("category", "")).strip(), names))
    return rows


def _card_kind(fighter) -> str:
    if _get(fighter, "is_stash", False):
        return "stash"
    if _get(fighter, "is_vehicle", False):
        return "vehicle"
    cat = str(
        getattr(getattr(fighter, "content_fighter_cached", None), "category", "") or ""
    )
    if cat == "CREW":
        return "crew"
    return "fighter"


def card_from_fighter(fighter, list_obj=None) -> ClassicCard:
    """Build a :class:`ClassicCard` from a real :class:`ListFighter`."""
    cf = getattr(fighter, "content_fighter_cached", None) or getattr(
        fighter, "content_fighter", None
    )

    stats: list[StatCell] = []
    save_from_grid = ""
    for s in _get(fighter, "statline", []) or []:
        classes = str(getattr(s, "classes", "") or "")
        cell = StatCell(
            name=str(getattr(s, "name", "")),
            value=str(getattr(s, "value", "")),
            highlight=bool(getattr(s, "highlight", False)),
            first_of_group="border-start" in classes,
            modded=bool(getattr(s, "modded", False)),
        )
        stats.append(cell)
        if str(getattr(s, "field_name", "")) == "save":
            save_from_grid = cell.value

    # Save box: prefer the free-text save_roll; fall back to a "save" stat column.
    save = str(_get(fighter, "save_roll", "") or "") or save_from_grid

    # Skills and wyrd/psyker powers each get their own (skill-like) row.
    skills = [str(x) for x in (_get(fighter, "skilline_cached", []) or [])]
    powers: list[str] = []
    if _get(fighter, "is_psyker", False):
        for power in _get(fighter, "powers_cached", []) or []:
            pname = str(_get(power, "name", "") or "").strip()
            if pname:
                powers.append(pname)

    # Special rules go in their own row; notes catches injuries + own notes.
    rules = [str(_get(r, "value", r)) for r in (_get(fighter, "ruleline", []) or [])]
    rules = [r for r in rules if r]

    # Lasting injuries get their own write-in strip at the top of the card.
    try:
        injury_rows = (
            list(fighter.injuries.all()) if hasattr(fighter, "injuries") else []
        )
    except Exception:
        injury_rows = []
    injuries = [
        str(getattr(getattr(i, "injury", None), "name", "")) for i in injury_rows
    ]
    injuries = [n for n in injuries if n]

    # notes is rich text; the card wants compact plain text.
    notes_lines: list[str] = []
    own_notes = strip_tags(str(getattr(fighter, "notes", "") or "")).strip()
    if own_notes:
        notes_lines.append(own_notes)

    # fighter portrait, if one is set
    image_url = ""
    img = getattr(fighter, "image", None)
    if img:
        try:
            image_url = img.url
        except (ValueError, AttributeError):
            image_url = ""

    subtitle_bits = []
    if cf is not None:
        t = str(getattr(cf, "type", "") or "").strip()
        if t:
            subtitle_bits.append(t)
    cat_label = str(_get(fighter, "get_category_label", "") or "").strip()
    if cat_label and cat_label not in subtitle_bits:
        subtitle_bits.append(cat_label)

    return ClassicCard(
        kind=_card_kind(fighter),
        name=str(getattr(fighter, "name", "") or ""),
        subtitle=" · ".join(subtitle_bits),
        cost=str(_get(fighter, "cost_display", "") or ""),
        stats=stats,
        save=save,
        weapons=_weapon_rows(fighter),
        skills=skills,
        powers=powers,
        wargear=_wargear_names(fighter),
        gear_categories=_gear_categories(fighter),
        rules=rules,
        xp=str(_get(fighter, "xp_current", "") or ""),
        injuries=injuries,
        notes_lines=notes_lines,
        image_url=image_url,
        recovery=bool(_get(fighter, "is_injured", False)),
        captured=bool(_get(fighter, "is_captured", False)),
        dead=bool(_get(fighter, "is_dead", False)),
        fighter_id=str(getattr(fighter, "id", "") or ""),
    )


# ---------------------------------------------------------------------------
# Statline headers + blank cards
# ---------------------------------------------------------------------------

_HUMANOID_NAMES = ["M", "WS", "BS", "S", "T", "W", "I", "A", "Ld", "Cl", "Wil", "Int"]
_VEHICLE_NAMES = ["M", "Fr", "Sd", "Rr", "HP", "Hnd", "Sv"]
_CREW_NAMES = ["BS", "Ld", "Cl", "Wil", "Int"]


def _humanoid_stats(values) -> list[StatCell]:
    cells = []
    for name, val in zip(_HUMANOID_NAMES, values):
        cells.append(
            StatCell(
                name=name,
                value=val,
                highlight=name in ("Ld", "Cl", "Wil", "Int"),
                first_of_group=(name in ("M", "Ld")),
            )
        )
    return cells


def _vehicle_stats(values) -> list[StatCell]:
    cells = []
    for name, val in zip(_VEHICLE_NAMES, values):
        cells.append(
            StatCell(name=name, value=val, first_of_group=(name in ("M", "HP")))
        )
    return cells


def _crew_stats(values) -> list[StatCell]:
    return [
        StatCell(name=n, value=v, highlight=True, first_of_group=(n == "BS"))
        for n, v in zip(_CREW_NAMES, values)
    ]


def blank_classic_card(shape: str = "fighter") -> ClassicCard:
    """An empty, fillable classic card.

    ``shape`` picks the statline headers: ``"vehicle"`` gets the 7-column
    vehicle line, everything else the 12-column humanoid line. ``kind`` is
    always ``"blank"`` so the template suppresses "No weapons." and the dead
    overlay.
    """
    if shape == "vehicle":
        stats = _vehicle_stats([""] * len(_VEHICLE_NAMES))
    else:
        stats = _humanoid_stats([""] * len(_HUMANOID_NAMES))
    return ClassicCard(kind="blank", stats=stats)
