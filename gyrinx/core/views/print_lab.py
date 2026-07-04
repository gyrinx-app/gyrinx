"""Print Lab — a staff/dev sandbox for the grimdark "classic mode" print cards (#1726).

Renders fixed-size (100mm x 110mm) Necromunda-style fighter/vehicle cards using
absolutely-positioned regions over distressed artwork, so we can nail the layout
against real gang data and synthetic edge cases, then print-to-PDF on a real printer.

## Region -> data mapping

The classic card has a *fixed* set of regions (mirroring the reference cards). A
fighter carries more data than the card has room for, so this module maps Gyrinx's
richer data onto the fixed regions and deliberately omits the rest:

    NAME      <- fighter.name, fighter type, cost
    STATLINE  <- fighter.statline  (dynamic columns; every statline type supported)
    SAVE      <- statline "save" column if present, else fighter.save_roll (else blank)
    WEAPONS   <- fighter.weapons_cached, flattened to rows (name, ranges, str/ap/d/am, traits)
    SKILLS    <- fighter.skilline_cached
    POWERS    <- wyrd / psyker powers (own skill-like row, when present)
    WARGEAR   <- wargear_cached (general gear)
    <category> <- each special gear category (Legendary Names, Status Items, ...)
                 keeps its own labelled row rather than being flattened
    RULES     <- fighter.ruleline (own row)
    XP        <- fighter.xp_current
    KILLS     <- blank fillable box (Gyrinx has no per-fighter kill counter)
    NOTES     <- injuries + fighter.notes
    Condition tabs (Serious Injury / Broken / Blaze / Insane) -> blank tick boxes
        (not persisted in Gyrinx). Recovery / Captured / Dead reflect injury_state.

Deliberately omitted (no region on the classic card): counters, advancement detail,
psyker discipline metadata. This is by design (see #1726 discussion) and surfaced in
the lab UI so it is never a silent gap.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.utils.html import strip_tags
from django.views.decorators.clickjacking import xframe_options_sameorigin

from gyrinx.core.models.list import List, ListFighter

logger = logging.getLogger(__name__)

# --- Card dimensions (mm). The reference cards are exactly 100 x 110 mm. -----
CARD_W_MM = 100
CARD_H_MM = 110

# Background/theme options for the lab's texture switcher. Value -> label.
THEMES = [
    ("blank", "Plate (blank)"),
    ("odd", "Plate (corner ornament, left)"),
    ("even", "Plate (corner ornament, right)"),
    ("paper_odd", "Paper 2026 (left)"),
    ("paper_even", "Paper 2026 (right)"),
    ("dark", "Rusted dark plate"),
]
DEFAULT_THEME = "blank"


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
    notes_lines: list[str] = field(default_factory=list)
    # condition markers (mostly fillable; a couple reflect real state)
    recovery: bool = False
    captured: bool = False
    dead: bool = False
    fighter_id: str = ""


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

    notes_lines: list[str] = []
    try:
        injuries = list(fighter.injuries.all()) if hasattr(fighter, "injuries") else []
    except Exception:
        injuries = []
    inj_names = [str(getattr(getattr(i, "injury", None), "name", "")) for i in injuries]
    inj_names = [n for n in inj_names if n]
    if inj_names:
        notes_lines.append("Injuries: " + ", ".join(inj_names))
    # notes is rich text; the card wants compact plain text.
    own_notes = strip_tags(str(getattr(fighter, "notes", "") or "")).strip()
    if own_notes:
        notes_lines.append(own_notes)

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
        notes_lines=notes_lines,
        recovery=bool(_get(fighter, "is_injured", False)),
        captured=bool(_get(fighter, "is_captured", False)),
        dead=bool(_get(fighter, "is_dead", False)),
        fighter_id=str(getattr(fighter, "id", "") or ""),
    )


# ---------------------------------------------------------------------------
# Synthetic presets — edge cases for aesthetic testing, no DB required.
# ---------------------------------------------------------------------------

_HUMANOID_NAMES = ["M", "WS", "BS", "S", "T", "W", "I", "A", "Ld", "Cl", "Wil", "Int"]
_VEHICLE_NAMES = ["M", "Fr", "Sd", "Rr", "HP", "Hnd", "Sv"]
_CREW_NAMES = ["BS", "Ld", "Cl", "Wil", "Int"]


def _humanoid_stats(values) -> list[StatCell]:
    cells = []
    for i, (name, val) in enumerate(zip(_HUMANOID_NAMES, values)):
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


def synthetic_presets() -> "dict[str, ClassicCard]":
    """Ordered map of preset key -> ClassicCard, covering layout edge cases."""
    presets: dict[str, ClassicCard] = {}

    presets["ganger"] = ClassicCard(
        kind="fighter",
        name="Bo 'Two-Guns' Marr",
        subtitle="Ganger · Champion",
        cost="145¢",
        stats=_humanoid_stats(
            ['5"', "4+", "3+", "3", "3", "1", "4+", "1", "7+", "6+", "8+", "7+"]
        ),
        save="5+",
        weapons=[
            WeaponRow(
                "Autopistol",
                '4"',
                '12"',
                "+2",
                "-",
                "3",
                "-",
                "1",
                "4+",
                "Rapid Fire (1)",
            ),
            WeaponRow(
                "Fighting knife", "-", "E", "-", "-", "S", "-", "1", "-", "Melee"
            ),
        ],
        skills=["Nerves of Steel", "Spring Up"],
        wargear=["Mesh armour", "Respirator"],
        rules=["Gang Fighter"],
        xp="6",
        notes_lines=[],
    )

    presets["leader"] = ClassicCard(
        kind="fighter",
        name="Cardinal Kaustus",
        subtitle="Cawdor Leader · Redemptionist Priest",
        cost="245¢",
        stats=_humanoid_stats(
            ['5"', "3+", "4+", "3", "3", "2", "4+", "2", "5+", "6+", "4+", "7+"]
        ),
        save="4+",
        weapons=[
            WeaponRow(
                "Autogun", '8"', '24"', "+1", "-", "3", "-", "1", "4+", "Rapid Fire (1)"
            ),
            WeaponRow(
                "phosphor rounds",
                '8"',
                '24"',
                "+1",
                "-",
                "3",
                "-",
                "1",
                "4+",
                "Flare, Rapid Fire (1), Scarce",
                is_secondary=True,
            ),
            WeaponRow(
                "Chainsword",
                "-",
                "E",
                "+1",
                "-",
                "S",
                "-",
                "1",
                "-",
                "Melee, Parry, Rending",
            ),
        ],
        skills=["Fearsome", "Overseer", "Inspirational"],
        wargear=["Flak armour", "Chem-thrower fuel"],
        rules=[
            "Fanatical",
            "Gang Hierarchy (Leader)",
            "Gang Leader",
            "Group Activation (2)",
            "The Path We Follow",
            "Tools of the Trade",
        ],
        xp="20",
        notes_lines=[],
    )

    presets["vehicle"] = ClassicCard(
        kind="vehicle",
        name="Ridgehauler",
        subtitle="Light Vehicle",
        cost="185¢",
        stats=_vehicle_stats(['7"', "4", "4", "3", "3", "6+", "4+"]),
        save="4+",
        weapons=[
            WeaponRow(
                "Heavy stubber",
                '20"',
                '40"',
                "-",
                "-1",
                "4",
                "-1",
                "1",
                "4+",
                "Rapid Fire (2)",
            ),
            WeaponRow(
                "Twin-linked spud-jacker",
                "-",
                "E",
                "-",
                "-",
                "S",
                "-",
                "2",
                "-",
                "Drive-by, Melee",
            ),
        ],
        skills=[],
        wargear=["Extra armour plating", "Nitro burner"],
        rules=["Jury-rigged", "Locomotion", "Upgrade Slots", "Weapon Hardpoints"],
        xp="3",
        notes_lines=[],
    )

    presets["crew"] = ClassicCard(
        kind="crew",
        name="Grease",
        subtitle="Gearhead · Crew",
        cost="45¢",
        stats=_crew_stats(["4+", "7+", "6+", "5+", "7+"]),
        save="6+",
        weapons=[
            WeaponRow(
                "Stub gun", '6"', '12"', "+2", "-", "3", "-", "1", "4+", "Plentiful"
            )
        ],
        skills=["Mounted", "Combat Master"],
        wargear=["Toolkit"],
        rules=["Mounted", "Exotic Beast"],
        xp="7",
        notes_lines=[],
    )

    presets["overflow"] = ClassicCard(
        kind="fighter",
        name="Maximilian Aurelius Thunderbolt III, the Unrelenting",
        subtitle="Bounty Hunter · Dramatis Personae · Champion",
        cost="410¢",
        stats=_humanoid_stats(
            ['6"', "2+", "2+", "4", "4", "3", "2+", "3", "4+", "5+", "5+", "6+"]
        ),
        save="2+",
        weapons=[
            WeaponRow(
                "Boltgun",
                '12"',
                '24"',
                "+1",
                "-",
                "4",
                "-1",
                "2",
                "6+",
                "Rapid Fire (1)",
            ),
            WeaponRow(
                "Plasma gun", '12"', '24"', "+1", "-", "5", "-1", "2", "5+", "Scarce"
            ),
            WeaponRow(
                "maximal",
                '12"',
                '24"',
                "-",
                "-1",
                "7",
                "-2",
                "3",
                "6+",
                "Scarce, Unstable",
                is_secondary=True,
            ),
            WeaponRow(
                "Power sword",
                "-",
                "E",
                "+1",
                "-",
                "S",
                "-2",
                "2",
                "-",
                "Melee, Parry, Power",
            ),
            WeaponRow(
                "Grenade launcher",
                '6"',
                '24"',
                "-",
                "-",
                "*",
                "*",
                "*",
                "6+",
                'Blast (3")',
            ),
            WeaponRow(
                "Frag",
                '6"',
                '24"',
                "-",
                "-",
                "3",
                "-",
                "1",
                "6+",
                'Blast (3"), Knockback',
                is_secondary=True,
            ),
        ],
        skills=[
            "Nerves of Steel",
            "Spring Up",
            "Combat Master",
            "Parry",
            "Counter-Attack",
            "Berserker",
            "Iron Jaw",
            "True Grit",
        ],
        wargear=[
            "Carapace armour",
            "Photo-goggles",
            "Respirator",
            "Bio-booster",
            "Grapnel launcher",
            "Stimm-slug stash",
        ],
        gear_categories=[
            ("Legendary Names", ["The Unbroken"]),
            ("Status Items", ["Master-crafted trophy rack"]),
        ],
        rules=["Fearsome", "Hardened", "Infiltrate", "Relentless", "Terrifying"],
        xp="52",
        notes_lines=[
            "Injuries: Old Battle Wound, Humiliated",
            "Notorious across the underhive for never leaving a bounty uncollected.",
        ],
        recovery=True,
    )

    presets["psyker"] = ClassicCard(
        kind="fighter",
        name="Esmerelda 'The Voice' Vane",
        subtitle="Wyrd · Champion",
        cost="205¢",
        stats=_humanoid_stats(
            ['5"', "4+", "4+", "3", "3", "2", "3+", "2", "5+", "5+", "4+", "6+"]
        ),
        save="5+",
        weapons=[
            WeaponRow(
                "Autopistol",
                '4"',
                '12"',
                "+2",
                "-",
                "3",
                "-",
                "1",
                "4+",
                "Rapid Fire (1)",
            ),
            WeaponRow(
                "Force sword",
                "-",
                "E",
                "+1",
                "-",
                "S",
                "-1",
                "2",
                "-",
                "Melee, Parry, Psychic",
            ),
        ],
        skills=["Nerves of Steel", "Overseer"],
        powers=["Assail", "Crush", "Levitation", "Mind Lock"],
        wargear=["Mesh armour", "Photo-goggles"],
        gear_categories=[
            ("Legendary Names", ["The Prophet of the Deep"]),
            ("Status Items", ["Gilded psy-focus"]),
        ],
        rules=["Sanctioned Psyker", "Fearsome"],
        xp="18",
        notes_lines=[],
    )

    presets["blank"] = ClassicCard(
        kind="blank",
        name="",
        subtitle="",
        cost="",
        stats=_humanoid_stats([""] * 12),
        save="",
        weapons=[],
        skills=[],
        wargear=[],
        xp="",
        notes_lines=[],
    )

    presets["stash"] = ClassicCard(
        kind="stash",
        name="Stash",
        subtitle="Gang stash",
        cost="0¢",
        stats=_humanoid_stats(["-"] * 12),
        save="",
        weapons=[],
        skills=[],
        wargear=["Frag grenades", "Krak grenades", "Spare autogun"],
        xp="",
        notes_lines=[],
    )

    return presets


PRESET_LABELS = {
    "ganger": "Ganger (typical)",
    "leader": "Leader (rules-heavy)",
    "vehicle": "Vehicle (7-stat line)",
    "crew": "Crew (5-stat line)",
    "psyker": "Psyker (powers + legendary names)",
    "overflow": "Overflow (stress test)",
    "blank": "Blank fighter card",
    "stash": "Stash",
}


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------


def _check_access(request):
    """Print lab is a dev/staff tool: available in DEBUG or to staff anywhere."""
    if settings.DEBUG or request.user.is_staff:
        return
    raise Http404("Print lab is only available in development or to staff.")


def _theme(request) -> str:
    theme = request.GET.get("theme", DEFAULT_THEME)
    valid = {key for key, _ in THEMES}
    return theme if theme in valid else DEFAULT_THEME


def _cards_for_request(request):
    """Resolve the (cards, error) for the current query params."""
    source = request.GET.get("source", "presets")
    presets = synthetic_presets()

    if source == "fighter":
        fid = request.GET.get("fighter", "").strip()
        if not fid:
            return [], "Enter a fighter id."
        try:
            fighter = ListFighter.objects.select_related("content_fighter", "list").get(
                id=fid
            )
        except Exception:
            return [], f"No fighter found for id {fid!r}."
        return [card_from_fighter(fighter, fighter.list)], None

    if source == "list":
        lid = request.GET.get("list", "").strip()
        if not lid:
            return [], "Enter a list id."
        try:
            list_obj = List.objects.get(id=lid)
        except Exception:
            return [], f"No gang found for id {lid!r}."
        fighters = (
            ListFighter.objects.filter(list=list_obj, archived=False)
            .select_related("content_fighter", "list")
            .order_by("name")
        )
        return [card_from_fighter(f, list_obj) for f in fighters], None

    if source == "preset":
        key = request.GET.get("preset", "ganger")
        card = presets.get(key) or presets["ganger"]
        return [card], None

    # default: gallery of all presets
    return list(presets.values()), None


@xframe_options_sameorigin
def print_lab_sheet(request):
    """The printable sheet — the actual print target (iframe / new tab).

    Same-origin framing is allowed so the lab harness can embed it as a live
    preview; the project default is ``X-Frame-Options: DENY``.
    """
    _check_access(request)
    cards, error = _cards_for_request(request)
    return render(
        request,
        "core/debug/print_lab_sheet.html",
        {
            "cards": cards,
            "theme": _theme(request),
            "show_grid": request.GET.get("grid") == "1",
            "paged": request.GET.get("paged") == "1",
            "auto_print": request.GET.get("print") == "1",
            "error": error,
        },
    )


def print_lab(request):
    """The lab harness: controls + live preview iframe."""
    _check_access(request)

    theme = _theme(request)
    source = request.GET.get("source", "presets")
    preset = request.GET.get("preset", "ganger")
    fighter_id = request.GET.get("fighter", "").strip()
    list_id = request.GET.get("list", "").strip()
    show_grid = request.GET.get("grid") == "1"
    paged = request.GET.get("paged") == "1"

    _, error = _cards_for_request(request)

    # Build the sheet URL, mirroring the current selection.
    from django.urls import reverse
    from urllib.parse import urlencode

    params = {"source": source, "theme": theme}
    if source == "preset":
        params["preset"] = preset
    if fighter_id:
        params["fighter"] = fighter_id
    if list_id:
        params["list"] = list_id
    if show_grid:
        params["grid"] = "1"
    if paged:
        params["paged"] = "1"
    sheet_url = reverse("debug_print_lab_sheet") + "?" + urlencode(params)

    # A few real examples for quick access (best-effort; empty in a bare DB).
    from types import SimpleNamespace

    example_fighters = []
    example_lists = []
    try:
        for f in (
            ListFighter.objects.filter(archived=False)
            .select_related("content_fighter", "list")
            .order_by("-updated")[:8]
        ):
            example_fighters.append(
                SimpleNamespace(id=f.id, label=f"{f.name} — {f.list.name}")
            )
        for lst in List.objects.order_by("-updated")[:5]:
            example_lists.append(SimpleNamespace(id=lst.id, label=lst.name))
    except Exception:
        # Quick-example links are best-effort sugar; an empty/unmigrated DB
        # should not break the lab.
        logger.debug("print lab quick examples unavailable", exc_info=True)

    return render(
        request,
        "core/debug/print_lab.html",
        {
            "themes": THEMES,
            "presets": [(k, PRESET_LABELS.get(k, k)) for k in synthetic_presets()],
            "theme": theme,
            "source": source,
            "preset": preset,
            "fighter_id": fighter_id,
            "list_id": list_id,
            "show_grid": show_grid,
            "paged": paged,
            "sheet_url": sheet_url,
            "example_fighters": example_fighters,
            "example_lists": example_lists,
            "error": error,
        },
    )
