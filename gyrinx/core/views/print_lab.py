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
    SAVE      <- fighter.save_roll if set, else the statline "save" column (else blank)
    WEAPONS   <- fighter.weapons_cached, flattened to rows (name, ranges, str/ap/d/am, traits)
    DETAIL    <- a 2-column grid (column-major: Skills, Rules | Gear, Other):
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

Deliberately omitted (no region on the classic card): counters, advancement detail,
psyker discipline metadata. This is by design (see #1726 discussion) and surfaced in
the lab UI so it is never a silent gap.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import Http404
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_sameorigin

from gyrinx.core.models.list import List, ListFighter
from gyrinx.core.utils import (
    get_list_attributes,
    get_list_campaign_resources,
    get_list_held_assets,
)
from gyrinx.core.print_cards import (
    DEFAULT_THEME,
    THEMES,
    ClassicCard,
    ClassicTextCard,
    DetailGroup,
    WeaponRow,
    _crew_stats,
    _humanoid_stats,
    _vehicle_stats,
    card_from_fighter,
    gang_card_from_list,
)

logger = logging.getLogger(__name__)


def synthetic_presets() -> "dict[str, ClassicCard | ClassicTextCard]":
    """Ordered map of preset key -> card, covering layout edge cases."""
    presets: dict[str, ClassicCard | ClassicTextCard] = {}

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
        injuries=["Humiliated"],
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
        injuries=["Old Battle Wound", "Humiliated"],
        notes_lines=[
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

    # Text plates (#1816) — same 100x110mm shape, flowing sections instead of
    # the fixed fighter regions.
    presets["gang"] = ClassicTextCard(
        kind="gang",
        name="The Ashen Choir",
        subtitle="House Cawdor",
        cost="1,245¢",
        meta=[("Credits", "180¢")],
        sections=[
            DetailGroup("Resources", ["Reputation: 7", "Meat: 3"], "cc-gangsec"),
            DetailGroup(
                "Assets",
                ["Old Factory (Territory)", "Slag Refinery (Territory)"],
                "cc-gangsec",
            ),
            DetailGroup("Alignment", ["Outlaw"], "cc-gangsec"),
            DetailGroup(
                "Stash",
                ["Autogun", "Mesh armour", "Respirator", "Frag grenade"],
                "cc-gangsec",
            ),
        ],
    )

    presets["lore"] = ClassicTextCard(
        kind="lore",
        name="Cardinal Kaustus",
        subtitle="Leader",
        columns=1,
        sections=[
            DetailGroup(
                "Lore",
                [
                    "Kaustus came up through the Redemption in Hive Primus, preaching "
                    "over the sump-fires until enough of the faithful followed him out "
                    "into the ash wastes. He does not speak of what he heard there, "
                    "only that it told him to gather a gang and go back."
                ],
                "cc-gangsec",
            ),
            DetailGroup(
                "Notes",
                ["Wounded turn 3 against the Iron Skulls. Watch the leg."],
                "cc-gangsec",
            ),
        ],
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
    "gang": "Gang plate (resources / assets / stash)",
    "lore": "Lore & notes plate",
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
        # Match the common case of the real classic print path (ListPrintView):
        # skip the stash and exclude dead fighters. The lab has no print-config
        # selector, so it always uses the default (dead excluded) rather than
        # honouring a config's include_dead_fighters.
        fighters = (
            ListFighter.objects.filter(list=list_obj, archived=False)
            .exclude(injury_state=ListFighter.DEAD)
            .select_related("content_fighter", "list")
            .order_by("name")
        )
        cards = []
        stash_fighter = None
        for f in fighters:
            card = card_from_fighter(f, list_obj)
            if card.kind == "stash":
                stash_fighter = f
                continue
            cards.append(card)

        # Gang plate, as the real classic sheet builds it (#1816).
        gang_card = gang_card_from_list(
            list_obj,
            resources=get_list_campaign_resources(list_obj),
            held_assets=get_list_held_assets(list_obj),
            attributes=get_list_attributes(list_obj),
            stash_fighter=stash_fighter,
        )
        if gang_card.has_content:
            cards.insert(0, gang_card)
        return cards, None

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
