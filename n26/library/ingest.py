"""Ingest — pre-ingest spreadsheets in, library rows out, preview between.

The pipeline (design/ingest.md §8) is three stages, and the middle one
is the interface:

* **read**: CSV text → rows (plain dicts, one per sheet line).
* **plan**: rows → :class:`IngestPlan` — a list of :class:`Planned`
  objects saying exactly which library row each sheet line becomes,
  plus :class:`Problem` rows for everything that doesn't resolve.
  Planning reads the database (to mark what already exists) but never
  writes. ``plan.preview()`` derives the upload-preview payload:
  counts by kind, worked examples (sheet row → planned objects), and
  the problem list — plain data, JSON-able, per the
  structures-before-renderers convention (CLAUDE.md).
* **perform**: plan → rows, through the ``n26.library.authoring`` verbs,
  in dependency order, in one transaction. Perform never invents
  anything the plan didn't say: the preview *is* the contract.

Three standing rules are load-bearing here:

* **Resolve, never create, across sheets.** An equipment-list line or a
  built-in names a weapon; if no weapon of that name is planned or
  already in the pack, that is a Problem, not a new weapon. Complex
  weapons are hand-authored first and resolved by name (§7b).
* **Built-ins are free.** Items named in a profile's default assignment
  attach at price 0 and never take a price from an equipment list,
  even on an exact name match (§5a — the Techmite's power fist is not
  the one on the Ironhead list).
* **Ingest stands on standard content.** The statline shapes, profile
  types, XP counter and skill tiers a plan resolves against come from
  ``n26.library.standard_content`` — sown from the foundations page, never
  re-declared here. Perform says which seed is missing rather than
  quietly planting its own.

**The sheets, and how they join.** Four of them, each with one job:

* **Equipment** — the catalogue. One row per thing the game sells,
  typed by an ``Assignable`` column (a weapon, wargear, or one of a
  weapon's priced firing lines), carrying its category and its price.
  The only place a reference price lives.
* **Weapon profiles** — the statlines, and nothing else. A blank
  ``Profile`` is the weapon's own firing line; a named one is an ammo
  type or a mode.
* **Equipment lists** — a named collection per ``Title``, one entry per
  line, at this list's price where it differs from the catalogue's.
* **Gang list profiles** — the fighters.

They join on an ``ID`` column printing ``Name (Profile) (Category ←
Section)``, which :class:`ItemId` parses. Resolution goes through that,
never through the name alone: eight weapons share a printed name across
categories, so a name is not an identity. Where two catalogue rows do
share one, both are kept and told apart by the author-facing
``qualifier`` (§6a) — renaming would put a word on a player's card that
the books do not print.

**Nothing here builds a Trading Post.** Membership there is *having a
trade point price* — the post is two sweeps sown as standard content —
so ingest's whole part in it is setting ``trade_point_price`` and
``is_exclusive`` from the sheet's ``TP`` column. The sheets keep those
as one fact: ``Cost`` ``-`` and ``TP`` ``E`` always appear together,
meaning "equipment-list only, priced by the list".
"""

import csv
import io
import random
import re
from collections import Counter as TallyCounter
from dataclasses import dataclass, field

from django.db import transaction

from n26.library.models.profile import TYPE_NAMES
from n26.library.standard_content import (
    MODEL_CHARACTERISTICS,
    SKILLS_COLLECTION,
    WEAPON_CHARACTERISTICS,
    WEAPON_STATLINE,
    XP_COUNTER,
)

# --- Sheet columns: the short names standard content fixes ------------------

#: ``(sheet column, characteristic full name)`` for a fighter row and a
#: weapon row. The columns are the characteristics' short names, which
#: is exactly how the pre-ingest sheets are headed. Values are kept
#: sheet-shaped in the plan (keyed by column); perform maps them onto
#: the stat definitions via the full name, because the *stat rows* are
#: shared — a weapon's Strength is the fighter's Strength, whatever
#: abbreviation either table prints.
MODEL_COLUMNS = [(short, full) for short, full, _, _ in MODEL_CHARACTERISTICS]
WEAPON_COLUMNS = [(short, full) for short, full, _ in WEAPON_CHARACTERISTICS]


# --- The plan: what each sheet line becomes ---------------------------------


@dataclass(frozen=True)
class Source:
    """Where a planned object came from: sheet name, 1-based data line."""

    sheet: str
    line: int

    def as_dict(self):
        return {"sheet": self.sheet, "line": self.line}


@dataclass(frozen=True)
class Planned:
    """One library row the plan intends.

    ``key`` names it within the plan (``"Weapon:autogun"``); other
    planned objects refer to it by that key in their ``fields``, so the
    whole plan is plain, printable data. ``action`` is ``"create"`` or
    ``"exists"`` — planning checks the pack and never plans a duplicate.
    """

    kind: str
    key: str
    name: str
    fields: dict
    action: str
    source: Source

    def as_dict(self):
        return {
            "kind": self.kind,
            "key": self.key,
            "name": self.name,
            "fields": self.fields,
            "action": self.action,
            "source": self.source.as_dict(),
        }


@dataclass(frozen=True)
class Problem:
    """One thing the plan cannot do. ``severity`` "error" blocks perform;
    "note" is said in the preview and carried past."""

    sheet: str
    line: int
    message: str
    severity: str = "error"

    def as_dict(self):
        return {
            "sheet": self.sheet,
            "line": self.line,
            "message": self.message,
            "severity": self.severity,
        }


_SMART = {"“": '"', "”": '"', "’": "'", "‘": "'"}


def _unsmart(value):
    for smart, plain in _SMART.items():
        value = value.replace(smart, plain)
    return value


def _norm(name):
    """The resolution key for a printed name: case, spacing, asterisks —
    and quote glyphs, because ``Butcher's`` and ``Butcher’s`` are the
    same name typed by different hands."""
    return _unsmart(re.sub(r"\s+", " ", name.strip().rstrip("*").strip())).lower()


def _clean(name):
    """The stored form: trimmed, asterisks (slot marks) off. Quote glyphs
    are kept as the sheet wrote them — only resolution folds them."""
    return re.sub(r"\s+", " ", name.strip().rstrip("*").strip())


@dataclass(frozen=True)
class ItemId:
    """The sheets' own join key, parsed into its four parts.

    Every catalogue sheet carries an ``ID`` column printing
    ``Name (Profile) (Category ← Section)``, and it reproduces exactly
    from those four columns — which is what makes the sheets joinable
    without guessing at names. Resolution goes through this, never
    through the name alone: eight weapons share a printed name across
    categories (a power fist is Exo kit *and* a Power weapon), so a
    name is not an identity.

    ``key`` is the resolution form — case, spacing and quote glyphs
    folded. The parts keep whatever the sheet wrote, for storing.
    """

    name: str
    profile: str
    category: str
    section: str

    @classmethod
    def of(cls, row):
        """The ID a row *means*, read off its four columns."""
        return cls(
            name=_clean(row.get("Name") or ""),
            profile=_clean(row.get("Profile") or ""),
            category=_clean(row.get("Category") or ""),
            section=_clean(row.get("Section") or ""),
        )

    @property
    def printed(self):
        """The ID as the sheet prints it — for saying so in a problem."""
        return f"{self.name} ({self.profile}) ({self.category} ← {self.section})"

    @property
    def key(self):
        return (
            f"{_norm(self.name)}|{_norm(self.profile)}"
            f"|{_norm(self.category)}|{_norm(self.section)}"
        )

    @property
    def parent(self):
        """The weapon a named profile hangs on: the same row, unnamed."""
        return ItemId(
            name=self.name, profile="", category=self.category, section=self.section
        )


def _name_and_annotation(token):
    """``"Ammo (5+)"`` → ``("Ammo", "5+")``; ``"Melee"`` → ``("Melee", "")``."""
    token = _unsmart(re.sub(r"\s*\(", " (", token.strip()))
    match = re.match(r"^(.*?)\s*\((.*)\)$", token)
    if match:
        return match.group(1), match.group(2)
    return token, ""


def _split_list(cell):
    return [part.strip() for part in cell.split(",") if part.strip()]


def _is_dash_row(name):
    return name.strip().startswith("- ") or name.strip() == "-"


def _dash_name(name):
    return name.strip().lstrip("-").strip()


def _price(cell):
    """Credits column: a number is a price; ``-`` and blank are 0 —
    ``-`` means "look to the equipment list" (§5b), tracked separately."""
    cell = cell.strip()
    return int(cell) if cell.isdigit() else 0


class IngestPlan:
    """Everything the upload would do, as data. The preview derives from
    this; perform executes exactly this."""

    def __init__(self, pack):
        self.pack = pack
        self.planned = []  # ordered Planned rows
        self.problems = []
        self._by_key = {}
        self._rows = {}  # (sheet, line) -> the raw csv row

    @property
    def ok(self):
        return not any(p.severity == "error" for p in self.problems)

    def get(self, key):
        return self._by_key.get(key)

    def add(self, kind, name, fields, source, key=None, action="create"):
        key = key or f"{kind}:{_norm(name)}"
        if key in self._by_key:
            return self._by_key[key]
        row = Planned(
            kind=kind,
            key=key,
            name=name,
            fields=fields,
            action=action,
            source=source,
        )
        self.planned.append(row)
        self._by_key[key] = row
        return row

    def problem(self, source, message, severity="error"):
        self.problems.append(
            Problem(
                sheet=source.sheet, line=source.line, message=message, severity=severity
            )
        )

    def remember_row(self, source, row):
        self._rows[(source.sheet, source.line)] = dict(row)

    def _replace(self, key, **field_changes):
        """Planning is two passes for prices (§5b); this is the second."""
        old = self._by_key[key]
        new = Planned(
            kind=old.kind,
            key=old.key,
            name=old.name,
            fields={**old.fields, **field_changes},
            action=old.action,
            source=old.source,
        )
        self._by_key[key] = new
        self.planned[self.planned.index(old)] = new
        return new

    # -- preview ------------------------------------------------------------

    def preview(self, examples=3, sample=False, seed=None):
        """The upload preview: plain data, JSON-able.

        ``examples`` worked rows per sheet — the top few, or a random
        sample with ``sample=True`` — each pairing the raw sheet row
        with every object it plans.
        """
        counts = TallyCounter()
        actions = TallyCounter()
        for row in self.planned:
            counts[row.kind] += 1
            actions[row.action] += 1

        by_source = {}
        for row in self.planned:
            by_source.setdefault((row.source.sheet, row.source.line), []).append(row)

        picked = []
        for sheet in sorted({sheet for sheet, _ in by_source}):
            lines = sorted(line for s, line in by_source if s == sheet)
            if sample:
                rng = random.Random(seed)  # nosec B311 - a stable preview sample, not crypto
                lines = sorted(rng.sample(lines, min(examples, len(lines))))
            else:
                lines = lines[:examples]
            picked.extend((sheet, line) for line in lines)

        return {
            "ok": self.ok,
            "counts": dict(counts),
            "actions": dict(actions),
            "problems": [p.as_dict() for p in self.problems],
            "examples": [
                {
                    "source": {"sheet": sheet, "line": line},
                    "row": self._rows.get((sheet, line), {}),
                    "creates": [r.as_dict() for r in by_source[(sheet, line)]],
                }
                for sheet, line in picked
            ],
        }


# --- Reading -----------------------------------------------------------------


def read_csv(text):
    """CSV text → rows. The file interface: everything after this is rows."""
    return list(csv.DictReader(io.StringIO(text.strip())))


# --- Planning ----------------------------------------------------------------


def plan_ingest(
    equipment=(),
    weapon_profiles=(),
    equipment_lists=(),
    profiles=(),
    pack=None,
):
    """Rows from up to four sheets → one :class:`IngestPlan`.

    The order is forced, and it is circular if done naively: statlines
    hang on catalogue rows, lists resolve against the catalogue, a
    fighter's built-in kit names things the catalogue defines, and a
    list's restrictions name fighters. So:

    1. the **equipment** sheet — the catalogue: what exists, and its price;
    2. the **weapon profiles** sheet — the statlines, onto those rows;
    3. the **equipment lists** — collections and entries, restrictions deferred;
    4. the **gang list profiles** — the fighters;
    5. those deferred restrictions, which needed the fighters.

    Resolve, never create, at every step.
    """
    from n26.library.models import get_default_pack

    plan = IngestPlan(pack or get_default_pack())
    # The catalogue pass needs to know which things have a firing line,
    # because that is what decides whether a "Wargear" row is really a
    # weapon (see _plan_equipment). The statlines themselves are planned
    # after, once there is something for them to hang on.
    statlined = {ItemId.of(row).key for row in weapon_profiles}
    profile_prices = _plan_equipment(plan, equipment, statlined)
    _plan_weapon_profiles(plan, weapon_profiles, profile_prices)
    pending_restrictions = _plan_equipment_lists(plan, equipment_lists)
    _plan_profiles(plan, profiles)
    _plan_restrictions(plan, pending_restrictions)
    return plan


def _exists(plan, model, **filters):
    return model.objects.filter(pack=plan.pack, **filters).first()


def _plan_category(plan, section, name, source):
    from n26.library.models import Category

    key = f"Category:{_norm(section)}:{_norm(name)}"
    if plan.get(key):
        return key
    action = (
        "exists"
        if _exists(
            plan,
            Category,
            section__name__iexact=section.strip(),
            name__iexact=name.strip(),
        )
        else "create"
    )
    plan.add(
        "Category",
        _clean(name),
        {"section": section.strip()},
        source,
        key=key,
        action=action,
    )
    return key


def _plan_trait(plan, token, source):
    from n26.library.models import Trait

    name, annotation = _name_and_annotation(token)
    key = f"Trait:{_norm(name)}:{annotation.lower()}"
    if plan.get(key):
        return key
    action = (
        "exists"
        if _exists(plan, Trait, name__iexact=name, annotation__iexact=annotation)
        else "create"
    )
    plan.add("Trait", name, {"annotation": annotation}, source, key=key, action=action)
    return key


#: The ``Assignable`` column's words → the kinds a plan speaks in.
EQUIPMENT_KINDS = {
    "weapon": "Weapon",
    "wargear": "Wargear",
    "weapon profile": "WeaponProfile",
}


def _prices(row):
    """``Cost`` and ``TP`` → the three priced fields.

    The sheets keep one rule and it is worth stating plainly: a thing is
    either sold at the Trading Post at a printed price, or it is
    equipment-list only. ``Cost`` ``-`` and ``TP`` ``E`` always appear
    together, and the database refuses exclusive-with-a-TP-price, so the
    pair is written as the single fact it is.

    ``0`` is a real Trade Point price, not a blank — an item free at the
    post is still offered there.
    """
    cost = (row.get("Cost") or "").strip()
    trade = (row.get("TP") or "").strip().upper()
    exclusive = trade == "E"
    return {
        "price": int(cost) if cost.isdigit() else 0,
        # No printed price of its own: whatever list sells it says so.
        "unpriced": not cost.isdigit(),
        "trade_point_price": None if exclusive or not trade.isdigit() else int(trade),
        "is_exclusive": exclusive,
    }


def _plan_equipment(plan, rows, statlined=frozenset()):
    """The equipment sheet: the catalogue, and the only place a price lives.

    One row per thing the game sells, typed by its ``Assignable``
    column — a weapon, a piece of wargear, or one of a weapon's priced
    firing lines. Statlines arrive on the weapon profiles sheet; this
    pass fixes identity, home and price.

    **Grenades.** The sheet types them Wargear, and the game calls them
    that for one reason: they do not count against the weapons a fighter
    is holding. But a thing with a firing line is a weapon — it has a
    range, a strength, traits — so a Wargear row that ``statlined``
    knows becomes a Weapon taking **no slots**, which is precisely the
    fact "wargear" was standing in for. Its category is untouched, so it
    still homes under Grenades where the lists expect it.

    Nothing here builds a Trading Post. Membership there is *having a
    trade point price* — the post is two sweeps sown as standard content
    — so setting the field is the whole job.

    Returns the prices found for named weapon profiles, keyed by ID: the
    profiles themselves are defined by their statlines, and this sheet
    only says what they cost.
    """
    from n26.library.models import Wargear, Weapon

    # Pass 1: which printed names does more than one item claim? Those
    # want the author-facing qualifier (§6a) — a power fist is Exo kit
    # and a Power weapon, two weapons wearing one name. The category is
    # how the sheet tells them apart, so it is what qualifies them.
    claims = {}
    for row in rows:
        kind = EQUIPMENT_KINDS.get(_norm(row.get("Assignable") or ""))
        if kind is None:
            continue
        ident = ItemId.of(row)
        claims.setdefault((kind, _norm(ident.name), _norm(ident.profile)), set()).add(
            ident.key
        )
    contested = {claim for claim, ids in claims.items() if len(ids) > 1}

    profile_prices = {}
    seen = {}
    for line, row in enumerate(rows, start=1):
        source = Source("equipment", line)
        plan.remember_row(source, row)

        said = _clean(row.get("Assignable") or "")
        kind = EQUIPMENT_KINDS.get(_norm(said))
        if kind is None:
            plan.problem(
                source,
                f"Assignable {said!r} is not a kind — the sheet's kinds are "
                f"{', '.join(sorted(set(EQUIPMENT_KINDS.values())))}",
            )
            continue

        ident = ItemId.of(row)
        if not ident.name:
            plan.problem(source, "row names nothing")
            continue

        key = f"{kind}:{ident.key}"
        if key in seen:
            plan.problem(
                source,
                f"{ident.printed!r} is in the sheet twice "
                f"(already at equipment:{seen[key]}) — the first is used",
                severity="note",
            )
            continue
        seen[key] = line

        priced = _prices(row)
        qualifier = (
            ident.category
            if (kind, _norm(ident.name), _norm(ident.profile)) in contested
            else ""
        )

        if kind == "WeaponProfile":
            # This sheet prices a firing line; the statline sheet is what
            # says the line exists at all. Hold the price for that pass.
            if not ident.profile:
                plan.problem(
                    source,
                    f"{ident.name!r} is typed 'Weapon Profile' but names no "
                    f"Profile — a weapon's own line is priced on the weapon",
                )
                continue
            profile_prices[ident.key] = priced
            continue

        category = _plan_category(plan, ident.section, ident.category, source)

        # A grenade: typed Wargear because it does not count against the
        # weapons held, but it has a firing line, so it is a weapon that
        # takes no slots. Slots carry the fact the typing was standing in
        # for; the category is left alone, so it still homes as Wargear.
        holds_no_slot = kind == "Wargear" and ident.key in statlined
        if holds_no_slot:
            kind = "Weapon"
            key = f"Weapon:{ident.key}"

        if kind == "Wargear":
            plan.add(
                "Wargear",
                ident.name,
                {
                    "category": category,
                    "qualifier": qualifier,
                    "price": priced["price"],
                    "unpriced": priced["unpriced"],
                    "trade_point_price": priced["trade_point_price"],
                    "is_exclusive": priced["is_exclusive"],
                },
                source,
                key=key,
                action="exists"
                if _exists(
                    plan, Wargear, name__iexact=ident.name, qualifier__iexact=qualifier
                )
                else "create",
            )
            continue

        plan.add(
            "Weapon",
            ident.name,
            {
                "category": category,
                "qualifier": qualifier,
                "price": priced["price"],
                "unpriced": priced["unpriced"],
                "trade_point_price": priced["trade_point_price"],
                "is_exclusive": priced["is_exclusive"],
                # No slot at all for a grenade; two hands for an
                # asterisked weapon; one for everything else.
                "slots": 0
                if holds_no_slot
                else (2 if "*" in (row.get("Name") or "") else 1),
                "statline_type": WEAPON_STATLINE,  # standard content's name
            },
            source,
            key=key,
            action="exists"
            if _exists(
                plan, Weapon, name__iexact=ident.name, qualifier__iexact=qualifier
            )
            else "create",
        )

    return profile_prices


def _plan_weapon_profiles(plan, rows, prices):
    """The weapon profiles sheet: the statlines, and nothing else.

    A row with a blank ``Profile`` is the weapon's own firing line — the
    card prints it as the weapon itself, so it is stored unnamed, free
    and first. A named row is a further line: an ammo type or a firing
    mode, costing whatever the equipment sheet priced it at, and free
    when that sheet does not list it.

    Resolve, never create: a statline whose weapon the catalogue does
    not define is a problem, not a new weapon.

    The rows are grouped by weapon before anything is planned, because
    the sheet is *sorted* rather than ordered: a weapon's ammo line can
    sit far from the weapon's own line, and a weapon may have no own
    line at all. Grouping is what lets the first line always be first.
    """
    groups = {}
    seen = {}
    for line, row in enumerate(rows, start=1):
        source = Source("weapon_profiles", line)
        plan.remember_row(source, row)

        if (row.get("Sub-profile") or "").strip():
            plan.problem(
                source,
                f"{ItemId.of(row).printed!r} has a Sub-profile — a weapon "
                f"within a weapon is hand-authored, not imported (§7b)",
            )
            continue

        ident = ItemId.of(row)
        if not ident.name:
            plan.problem(source, "row names no weapon")
            continue

        weapon_key = f"Weapon:{ident.parent.key}"
        weapon = plan.get(weapon_key)
        if weapon is None:
            # Nothing is created either way, so this is said and carried
            # past rather than blocking an otherwise good upload. (A row
            # the catalogue types Wargear cannot land here: having a
            # statline is what makes it a weapon — see _plan_equipment.)
            plan.problem(
                source,
                f"{ident.printed!r} has a statline, but the equipment "
                f"sheet sells no such thing — ignored (resolve, never "
                f"create, §7b)",
                severity="note",
            )
            continue

        key = f"WeaponProfile:{ident.key}"
        if key in seen:
            plan.problem(
                source,
                f"{ident.printed!r} has more than one statline "
                f"(already at weapon_profiles:{seen[key]}) — the sheet must "
                f"say which is right; the first is used",
                severity="note",
            )
            continue
        seen[key] = line
        groups.setdefault(weapon_key, []).append((source, row, ident))

    for weapon_key, members in groups.items():
        # The weapon's own line leads, whatever order the sheet found it
        # in; the named lines follow as the sheet has them. A weapon with
        # no own line simply starts at its first named one — no hole.
        own = [member for member in members if not member[2].profile]
        named = [member for member in members if member[2].profile]
        for position, (source, row, ident) in enumerate(own[:1] + named):
            priced = prices.get(ident.key)
            if priced is None or not ident.profile:
                # The weapon's own line is always free — the weapon's
                # price buys it — and so is a named line the equipment
                # sheet never priced (a lance's two ends).
                priced = {
                    "price": 0,
                    "trade_point_price": None,
                    "is_exclusive": False,
                }
            _plan_weapon_profile_row(
                plan, weapon_key, ident, priced, position, source, row
            )


def _plan_weapon_profile_row(plan, weapon_key, ident, priced, position, source, row):
    """One statline row → one planned profile, at its place in the order."""
    from n26.library.models import WeaponProfile

    plan.add(
        "WeaponProfile",
        ident.profile,
        {
            "weapon": weapon_key,
            "price": priced["price"],
            "trade_point_price": priced["trade_point_price"],
            "is_exclusive": priced["is_exclusive"],
            "stats": _statline_values(row, WEAPON_COLUMNS),
            "traits": [
                _plan_trait(plan, trait, source)
                for trait in _split_list(row.get("Traits", ""))
                if trait != "-"
            ],
            "position": position,
        },
        source,
        key=f"WeaponProfile:{ident.key}",
        action="exists"
        if _exists(
            plan,
            WeaponProfile,
            weapon__name__iexact=ident.name,
            name__iexact=ident.profile,
        )
        else "create",
    )


def _statline_values(row, columns):
    """The stat cells of one sheet row, keyed by sheet column. Blank
    cells stay unwritten; a printed ``-`` is stored as the dash it is."""
    values = {}
    for column, _full in columns:
        cell = _unsmart(row.get(column, "") or "").strip()
        if cell:
            values[column] = cell
    return values


def _plan_profiles(plan, rows):
    """The gang list profiles sheet. Rating **is** the price (§5a); the
    grid columns become placement modifiers on the profile itself."""
    from n26.library.models import GangType, Profile, Rule, Skill, Subtype

    for line, row in enumerate(rows, start=1):
        source = Source("profiles", line)
        plan.remember_row(source, row)
        name = _clean(row.get("Name", ""))
        if not name:
            plan.problem(source, "row names no profile")
            continue

        profile_type = (row.get("Type") or "").strip()
        if profile_type not in TYPE_NAMES:
            plan.problem(
                source,
                f"{name!r} has no Type — a rolled-statline or supplementary "
                f"row that belongs on another sheet (§6b)",
            )
            continue

        gang_name = _clean(row.get("Gang", ""))
        gang_key = f"GangType:{_norm(gang_name)}"
        if not plan.get(gang_key):
            plan.add(
                "GangType",
                gang_name,
                {},
                source,
                key=gang_key,
                action="exists"
                if _exists(plan, GangType, name__iexact=gang_name)
                else "create",
            )

        members = []  # (key, extras) pairs for the built-ins set

        for subtype in _split_list(row.get("Subtype(s)", "")):
            key = f"Subtype:{_norm(subtype)}"
            if not plan.get(key):
                plan.add(
                    "Subtype",
                    _clean(subtype),
                    {},
                    source,
                    key=key,
                    action="exists"
                    if _exists(plan, Subtype, name__iexact=subtype)
                    else "create",
                )
            members.append((key, {}))

        xp = (row.get("Starting XP") or "").strip()
        if xp.isdigit() and int(xp):
            members.append(("Counter:xp", {"amount": int(xp)}))

        for token in _split_list(row.get("Special Rules", "")):
            # A rule's annotation is part of its identity, as a trait's
            # is: Leash (3") and Leash (9") are two rules sharing a
            # printed name, and both must exist.
            rule_name, annotation = _name_and_annotation(token)
            key = f"Rule:{_norm(rule_name)}:{annotation.lower()}"
            if not plan.get(key):
                plan.add(
                    "Rule",
                    rule_name,
                    {"annotation": annotation},
                    source,
                    key=key,
                    action="exists"
                    if _exists(
                        plan,
                        Rule,
                        name__iexact=rule_name,
                        annotation__iexact=annotation,
                    )
                    else "create",
                )
            members.append((key, {}))

        skills_column = next(
            (column for column in row if column.startswith("Default skills")), None
        )
        for skill in _split_list(row.get(skills_column, "") if skills_column else ""):
            key = f"Skill:{_norm(skill)}"
            if not plan.get(key):
                plan.add(
                    "Skill",
                    _clean(skill),
                    {},
                    source,
                    key=key,
                    action="exists"
                    if _exists(plan, Skill, name__iexact=skill)
                    else "create",
                )
            members.append((key, {}))

        for item in _split_list(row.get("Default assignment", "")):
            resolved = _resolve_item(plan, item)
            if resolved is None:
                # Built-in-only kit — hunting rigs, exo-suits, natural
                # weapons — is never sold, so no sheet defines it. The
                # fighter is still worth having, so this is said and
                # carried past; the fighter simply arrives without it.
                plan.problem(
                    source,
                    f"{name!r} comes with {item!r}, which no sheet defines "
                    f"and the pack does not hold — imported without it "
                    f"(built-ins resolve, never create)",
                    severity="note",
                )
                continue
            members.append((resolved, {}))

        # Two gangs printing the same fighter name is normal, and the
        # qualifier (§6a) is how the library holds both — author-facing
        # only, the card prints the name alone. The sheet may name the
        # qualifier itself; where it doesn't, the first row keeps the
        # bare name and a second gang's is qualified with its gang.
        plain_key = f"Profile:{_norm(name)}"
        planned_plain = plan.get(plain_key)
        existing_plain = _exists(plan, Profile, name__iexact=name, qualifier__iexact="")
        if planned_plain is not None:
            name_holder = planned_plain.fields["gang_type"]
        elif existing_plain is not None:
            name_holder = f"GangType:{_norm(existing_plain.gang_type.name)}"
        else:
            name_holder = None

        qualifier = _clean(row.get("Qualifier") or "")
        if not qualifier and name_holder is not None and name_holder != gang_key:
            qualifier = gang_name
            plan.problem(
                source,
                f"profile {name!r} is also another gang's — this one is "
                f"qualified {qualifier!r} (§6a); authors see the qualifier, "
                f"players never do",
                severity="note",
            )

        profile_key = plain_key if not qualifier else f"{plain_key}:{_norm(qualifier)}"
        # Name and qualifier together are the identity, so two rows
        # claiming both are one row as far as the library is concerned —
        # and the second would vanish into the first. Say so instead.
        if (clash := plan.get(profile_key)) is not None:
            said = f"{name!r} qualified {qualifier!r}" if qualifier else repr(name)
            plan.problem(
                source,
                f"{said} is already taken by "
                f"{clash.source.sheet}:{clash.source.line} — a name and its "
                f"qualifier are one identity, so these two fighters need "
                f"different qualifiers",
            )
            continue
        label = name if not qualifier else f"{name} ({qualifier})"
        existing = (
            existing_plain
            if not qualifier
            else _exists(plan, Profile, name__iexact=name, qualifier__iexact=qualifier)
        )

        from n26.library.models import DefaultAssignmentSet

        built_ins_key = None
        if members:
            set_name = f"{label} built-ins"
            built_ins_key = f"DefaultAssignmentSet:{_norm(set_name)}"
            plan.add(
                "DefaultAssignmentSet",
                set_name,
                {"members": [{"item": key, **extras} for key, extras in members]},
                source,
                key=built_ins_key,
                action="exists"
                if _exists(plan, DefaultAssignmentSet, name__iexact=set_name)
                else "create",
            )

        rating = (row.get("Rating") or "").strip()
        plan.add(
            "Profile",
            name,
            {
                "gang_type": gang_key,
                "profile_type": profile_type,
                "qualifier": qualifier,
                "price": int(rating) if rating.isdigit() else 0,
                "stats": _statline_values(row, MODEL_COLUMNS),
                "built_ins": built_ins_key,
            },
            source,
            key=profile_key,
            action="exists" if existing else "create",
        )

        from n26.library.models import Modifier

        for column, section in (
            ("Primary Skill Sets", "Primary"),
            ("Secondary Skill Sets", "Secondary"),
        ):
            for skill_set in _split_list(row.get(column, "")):
                category = _plan_category(plan, "Skills", skill_set, source)
                modifier_name = f"{label}: {skill_set} is {section}"
                plan.add(
                    "Modifier",
                    modifier_name,
                    {
                        "attach_to": profile_key,
                        "places": {"category": category, "section": section},
                    },
                    source,
                    key=f"Modifier:{profile_key}:{_norm(skill_set)}:{section.lower()}",
                    action="exists"
                    if _exists(plan, Modifier, name__iexact=modifier_name)
                    else "create",
                )


def _resolve_item(plan, name):
    """A name that must already mean something: a planned weapon or
    wargear, or one in the pack. Returns its key, or None.

    The catalogue is keyed by ID, which carries the category — but a
    fighter's built-in kit prints a bare name and no category, so this
    is the one place resolution goes by name alone. A name two catalogue
    rows share cannot be resolved that way and is refused rather than
    guessed at.
    """
    from n26.library.models import Wargear, Weapon

    wanted = _norm(name)
    hits = [
        planned
        for planned in plan.planned
        if planned.kind in ("Weapon", "Wargear") and _norm(planned.name) == wanted
    ]
    if len(hits) == 1:
        return hits[0].key
    if len(hits) > 1:
        return None  # ambiguous by name; the ID is what tells them apart

    for kind, model in (("Weapon", Weapon), ("Wargear", Wargear)):
        if existing := _exists(plan, model, name__iexact=_clean(name)):
            return plan.add(
                kind,
                existing.name,
                {"price": existing.price, "unpriced": False},
                Source("resolution", 0),
                key=f"{kind}:resolved|{wanted}",
                action="exists",
            ).key
    return None


#: What the ``Collection`` column says these rows build. One kind today;
#: the column exists so the sheet can grow others without a new file.
EQUIPMENT_LIST_COLLECTION = "Equipment List"


def _collection_name(title):
    """The collection a ``Title`` names — "Ash Waste Nomads Equipment List".

    The sheet splits the kind (``Collection``) from the name (``Title``);
    the library holds one row, so the two are put back together. Saying
    the kind matters: a gang type and its list would otherwise be one
    word apart in every dropdown.
    """
    return f"{_clean(title)} {EQUIPMENT_LIST_COLLECTION}"


def _plan_equipment_lists(plan, rows):
    """The equipment lists sheet: one named collection per ``Title``.

    An entry per line, resolved against the catalogue **by ID** — never
    created here. The ID carries the category, which is what tells two
    weapons sharing a printed name apart, so resolution is exact and a
    miss is a real miss.

    A price override is written only where the list disagrees with the
    catalogue. An item the catalogue prices ``-`` has no reference price
    at all, so the list price is the only price it has ever had and is
    always written; an item whose list price matches its reference
    carries nothing, which is what "at catalogue price" looks like.

    Returns the restrictions found, deferred: they name fighters, and
    fighter profiles plan after this pass.
    """
    from n26.library.models.collection import Collection

    pending_restrictions = []
    positions = TallyCounter()
    for line, row in enumerate(rows, start=1):
        source = Source("equipment_lists", line)
        plan.remember_row(source, row)

        title = _clean(row.get("Title") or row.get("Gang") or "")
        if not title:
            plan.problem(source, "row names no list")
            continue

        name = _collection_name(title)
        collection_key = f"Collection:{_norm(name)}"
        if not plan.get(collection_key):
            plan.add(
                "Collection",
                name,
                {},
                source,
                key=collection_key,
                action="exists"
                if _exists(plan, Collection, name__iexact=name)
                else "create",
            )

        ident = ItemId.of(row)
        if not ident.name:
            plan.problem(source, "row names nothing")
            continue

        item_key = _resolve_by_id(plan, ident)
        if item_key is None:
            plan.problem(
                source,
                f"{title} sells {ident.printed!r}, which the equipment sheet "
                f"does not define and the pack does not hold — resolve, "
                f"never create (§7b)",
            )
            continue

        entry_key = f"CollectionEntry:{_norm(name)}:{item_key}"
        if plan.get(entry_key):
            plan.problem(
                source,
                f"{title} lists {ident.printed!r} twice — the second is ignored",
                severity="note",
            )
            continue

        item = plan.get(item_key)
        credits = (row.get("Credits") or "").strip()
        list_price = int(credits) if credits.isdigit() else None
        entry = plan.add(
            "CollectionEntry",
            f"{item.name} in {name}",
            {
                "collection": collection_key,
                "item": item_key,
                "position": positions[collection_key],
                "price_override": _override(item, list_price),
            },
            source,
            key=entry_key,
            action="exists" if _entry_exists(plan, name, item_key) else "create",
        )
        positions[collection_key] += 1

        restriction = (row.get("Restrictions") or "").strip()
        if restriction:
            pending_restrictions.append(
                (source, restriction, item_key, title, entry.key, entry.action)
            )

    return pending_restrictions


def _override(item, list_price):
    """What this entry must say about price, beyond the catalogue.

    ``None`` means "at catalogue price" — the entry stores nothing and a
    later correction to the item flows through. A number is this list's
    own price, which the catalogue does not know.
    """
    if list_price is None:
        return None
    # No reference price to agree with: the list is the only price.
    if item.fields.get("unpriced"):
        return list_price
    if list_price != item.fields.get("price"):
        return list_price
    return None


def _resolve_by_id(plan, ident):
    """The catalogue row an ID names: planned, or already in the pack.

    Weapons and wargear are named directly; a listing that carries a
    ``Profile`` is selling one firing line of a weapon (a grenade type,
    an ammo), which is its own listable thing.
    """
    from n26.library.models import Wargear, Weapon, WeaponProfile

    if ident.profile:
        candidates = [
            (
                "WeaponProfile",
                WeaponProfile,
                {"weapon__name__iexact": ident.name, "name__iexact": ident.profile},
            )
        ]
    else:
        candidates = [
            ("Weapon", Weapon, {"name__iexact": ident.name}),
            ("Wargear", Wargear, {"name__iexact": ident.name}),
        ]

    for kind, _model, _filters in candidates:
        key = f"{kind}:{ident.key}"
        if plan.get(key):
            return key

    # Not planned this run — the pack may already hold it, which is what
    # a second upload and the hand-authored items both look like.
    for kind, model, filters in candidates:
        if existing := _exists(plan, model, **filters):
            return plan.add(
                kind,
                existing.name,
                {"price": existing.price, "unpriced": False},
                Source("resolution", 0),
                key=f"{kind}:{ident.key}",
                action="exists",
            ).key
    return None


def _plan_restrictions(plan, pending):
    """The deferred restrictions pass: fighter profiles exist by now.

    Three shapes turn up and only one has a home. "<Fighter> only"
    narrows an item to a profile, which ``UsableBy`` holds. A
    specialisation ("Gunner specialist only") names something
    ``UsableBy`` has no arm for, and a gang-wide cap ("Max one per
    gang") is not a restriction on *use* at all. Both are said and
    carried past rather than quietly dropped or bent into the wrong
    mechanism.
    """
    for source, restriction, item_key, gang, entry_key, entry_action in pending:
        match = re.match(r"^(.*?)\s+only$", restriction, flags=re.IGNORECASE)
        profile_ref = match and _profile_ref(plan, match.group(1), gang)
        if profile_ref:
            plan.add(
                "Restriction",
                f"{plan.get(item_key).name} ({restriction})",
                {"item": item_key, "profile": profile_ref},
                source,
                key=f"Restriction:{entry_key}",
                action=entry_action,
            )
        elif match and re.search(r"specialist$", match.group(1), flags=re.IGNORECASE):
            plan.problem(
                source,
                f"restriction {restriction!r} names a specialisation, which "
                f"usable-by cannot express yet — imported without it",
                severity="note",
            )
        elif match:
            plan.problem(
                source,
                f"restriction {restriction!r} names a fighter no sheet "
                f"defines and the pack does not hold — imported without it",
                severity="note",
            )
        else:
            plan.problem(
                source,
                f"restriction {restriction!r} is not a restriction on use — "
                f"imported without it (§5c)",
                severity="note",
            )


def _profile_ref(plan, name, gang):
    """The profile a restriction names — preferring the naming gang's own
    qualified row (§6a) over another gang's bare one. Planned or already
    in the pack; None otherwise."""
    from n26.library.models import Profile

    for key in (f"Profile:{_norm(name)}:{_norm(gang)}", f"Profile:{_norm(name)}"):
        if plan.get(key):
            return key
    for qualifier in (gang, ""):
        existing = _exists(
            plan, Profile, name__iexact=_clean(name), qualifier__iexact=qualifier
        )
        if existing:
            suffix = f":{_norm(qualifier)}" if qualifier else ""
            return plan.add(
                "Profile",
                existing.name,
                {"qualifier": existing.qualifier},
                Source("resolution", 0),
                key=f"Profile:{_norm(name)}{suffix}",
                action="exists",
            ).key
    return None


def _entry_exists(plan, collection_name, item_key):
    """Is this line already an entry of this collection in the pack?"""
    from n26.library.models import CollectionEntry

    kind = item_key.split(":", 1)[0]
    column = {
        "Weapon": "weapon",
        "WeaponProfile": "weapon_profile",
        "Wargear": "wargear",
    }[kind]
    planned = plan.get(item_key)
    filters = {f"{column}__name__iexact": planned.name}
    if kind == "WeaponProfile":
        # A profile's name is only unique under its weapon.
        weapon = plan.get(planned.fields["weapon"])
        if weapon is not None:
            filters["weapon_profile__weapon__name__iexact"] = weapon.name
    else:
        filters[f"{column}__qualifier__iexact"] = planned.fields.get("qualifier", "")
    return CollectionEntry.objects.filter(
        pack=plan.pack,
        collection__name__iexact=collection_name,
        **filters,
    ).exists()


# --- Performing ----------------------------------------------------------------


@dataclass
class IngestResult:
    """What perform did: rows created, rows found already there."""

    created: dict = field(default_factory=dict)  # key -> model instance
    existing: dict = field(default_factory=dict)

    def counts(self):
        tally = TallyCounter(key.split(":", 1)[0] for key in self.created)
        return dict(tally)


#: Creation order — PROTECT relations point up this list.
PERFORM_ORDER = [
    "Category",
    "Trait",
    "GangType",
    "Subtype",
    "Skill",
    "Rule",
    "Weapon",
    "WeaponProfile",
    "Wargear",
    "DefaultAssignmentSet",
    "Profile",
    "Collection",
    "CollectionEntry",
    "Restriction",
    "Modifier",
]


def perform(plan):
    """Execute the plan through the authoring verbs, in one transaction.

    Refuses a plan with error problems: the preview said no. Returns an
    :class:`IngestResult` whose counts match the preview's ``create``
    tallies — the preview is the contract.

    Standard content must already be sown (the foundations page): the
    statline shapes, profile types, XP counter and skill tiers are
    resolved by their standard names and a missing one is a loud
    LookupError, never quietly re-planted.
    """
    if not plan.ok:
        errors = [p for p in plan.problems if p.severity == "error"]
        raise ValueError(
            f"plan has {len(errors)} unresolved problem(s); first: {errors[0].message}"
        )
    result = IngestResult()
    with transaction.atomic():
        performer = _Performer(plan, result)
        for kind in PERFORM_ORDER:
            for planned in plan.planned:
                if planned.kind == kind:
                    performer.perform_one(planned)
    return result


class _Performer:
    def __init__(self, plan, result):
        self.plan = plan
        self.result = result
        self.shared = {"pack": plan.pack}

    def _standard(self, model, what, **filters):
        """A standard-content row, by its fixed name. Missing means the
        seed hasn't been sown — say which, don't plant it here."""
        row = model.objects.filter(**filters).first()
        if row is None:
            raise LookupError(
                f"{what} is not there — sow standard content first "
                f"(the foundations page; library/standard_content.py)"
            )
        return row

    def resolve(self, key):
        """A planned key → the model row it now names."""
        if key in self.result.created:
            return self.result.created[key]
        if key in self.result.existing:
            return self.result.existing[key]
        if key == "Counter:xp":
            from n26.library.models import Counter

            return self._standard(
                Counter, f"the {XP_COUNTER} counter", name__iexact=XP_COUNTER
            )
        row = self._find_existing(self.plan.get(key) or _missing(key), key)
        if row is None:
            raise LookupError(f"nothing performs or holds {key}")
        self.result.existing[key] = row
        return row

    def _find_existing(self, planned, key):
        from n26.library.models import (
            Category,
            GangType,
            Profile,
            Rule,
            Skill,
            Subtype,
            Trait,
            Wargear,
            Weapon,
            WeaponProfile,
        )
        from n26.library.models.collection import Collection

        kind, *rest = key.split(":")
        simple = {
            "GangType": GangType,
            "Subtype": Subtype,
            "Skill": Skill,
            "Collection": Collection,
        }
        if kind in simple:
            return (
                simple[kind]
                .objects.filter(name__iexact=planned.name, **self.shared)
                .first()
            )
        if kind in ("Weapon", "Wargear"):
            # Qualified: two catalogue rows may print one name, and the
            # qualifier is the only thing telling them apart.
            model = Weapon if kind == "Weapon" else Wargear
            return model.objects.filter(
                name__iexact=planned.name,
                qualifier__iexact=planned.fields.get("qualifier", ""),
                **self.shared,
            ).first()
        if kind == "Profile":
            return Profile.objects.filter(
                name__iexact=planned.name,
                qualifier__iexact=planned.fields.get("qualifier", ""),
                **self.shared,
            ).first()
        if kind == "Trait":
            return Trait.objects.filter(
                name__iexact=planned.name,
                annotation__iexact=planned.fields["annotation"],
                **self.shared,
            ).first()
        if kind == "Rule":
            return Rule.objects.filter(
                name__iexact=planned.name,
                annotation__iexact=planned.fields["annotation"],
                **self.shared,
            ).first()
        if kind == "Category":
            return Category.objects.filter(
                section__name__iexact=planned.fields["section"],
                name__iexact=planned.name,
                **self.shared,
            ).first()
        if kind == "WeaponProfile":
            weapon = self.resolve(planned.fields["weapon"])
            return WeaponProfile.objects.filter(
                weapon=weapon, name__iexact=planned.name
            ).first()
        if kind == "DefaultAssignmentSet":
            from n26.library.models import DefaultAssignmentSet

            return DefaultAssignmentSet.objects.filter(
                name__iexact=planned.name, **self.shared
            ).first()
        return None

    #: Exists-marked rows of these kinds are pure leaves — nothing in a
    #: plan refers to them, so there is nothing to resolve.
    UNREFERENCED = {"CollectionEntry", "Restriction", "Modifier"}

    def perform_one(self, planned):
        if planned.action == "exists":
            if planned.kind not in self.UNREFERENCED:
                self.resolve(planned.key)
            return
        creator = getattr(self, f"_create_{planned.kind.lower()}")
        self.result.created[planned.key] = creator(planned)

    # -- one creator per kind, each a thin call into library.authoring ------

    def _create_category(self, planned):
        from n26.library import authoring

        return authoring.create_category(
            planned.fields["section"], planned.name, **self.shared
        )

    def _create_trait(self, planned):
        from n26.library import authoring

        return authoring.create_trait(
            planned.name, annotation=planned.fields["annotation"], **self.shared
        )

    def _create_gangtype(self, planned):
        from n26.library import authoring

        return authoring.create_gang_type(planned.name, **self.shared)

    def _create_subtype(self, planned):
        from n26.library import authoring

        return authoring.create_subtype(planned.name, **self.shared)

    def _create_skill(self, planned):
        from n26.library import authoring

        return authoring.create_skill(planned.name, **self.shared)

    def _create_rule(self, planned):
        from n26.library import authoring

        return authoring.create_rule(
            planned.name, annotation=planned.fields["annotation"], **self.shared
        )

    def _create_weapon(self, planned):
        from n26.library import authoring
        from n26.library.models import StatlineType

        return authoring.create_weapon(
            planned.name,
            slots=planned.fields["slots"],
            statline_type=self._standard(
                StatlineType,
                f"the {planned.fields['statline_type']!r} statline shape",
                name__iexact=planned.fields["statline_type"],
            ),
            price=planned.fields["price"],
            trade_point_price=planned.fields["trade_point_price"],
            is_exclusive=planned.fields["is_exclusive"],
            qualifier=planned.fields.get("qualifier", ""),
            category=self.resolve(planned.fields["category"]),
            **self.shared,
        )

    def _create_weaponprofile(self, planned):
        from n26.library import authoring

        profile = authoring.add_weapon_profile(
            self.resolve(planned.fields["weapon"]),
            planned.name,
            price=planned.fields["price"],
            trade_point_price=planned.fields["trade_point_price"],
            is_exclusive=planned.fields["is_exclusive"],
            traits=[self.resolve(key) for key in planned.fields["traits"]],
            position=planned.fields["position"],
            **self.shared,
        )
        self._set_statline(profile, planned.fields["stats"], WEAPON_COLUMNS)
        return profile

    def _create_wargear(self, planned):
        from n26.library import authoring

        return authoring.create_wargear(
            planned.name,
            price=planned.fields["price"],
            trade_point_price=planned.fields["trade_point_price"],
            is_exclusive=planned.fields["is_exclusive"],
            qualifier=planned.fields.get("qualifier", ""),
            category=self.resolve(planned.fields["category"]),
            **self.shared,
        )

    def _create_defaultassignmentset(self, planned):
        from n26.library import authoring

        return authoring.create_default_set(
            planned.name,
            members=[
                (
                    self.resolve(member["item"]),
                    {k: v for k, v in member.items() if k != "item"},
                )
                for member in planned.fields["members"]
            ],
            **self.shared,
        )

    def _create_profile(self, planned):
        from n26.library import authoring
        from n26.library.models import ProfileType

        profile = authoring.create_profile(
            planned.name,
            self._standard(
                ProfileType,
                f"the {planned.fields['profile_type']!r} profile type",
                name__iexact=planned.fields["profile_type"],
            ),
            self.resolve(planned.fields["gang_type"]),
            price=planned.fields["price"],
            qualifier=planned.fields.get("qualifier", ""),
            **self.shared,
        )
        if planned.fields["built_ins"]:
            profile.built_ins = self.resolve(planned.fields["built_ins"])
            profile.save()
        self._set_statline(profile, planned.fields["stats"], MODEL_COLUMNS)
        return profile

    def _create_collection(self, planned):
        from n26.library import authoring

        return authoring.create_collection(planned.name, **self.shared)

    def _create_collectionentry(self, planned):
        from n26.library.models import CollectionEntry

        overrides = {}
        if planned.fields["price_override"] is not None:
            overrides["price_override"] = planned.fields["price_override"]
        return CollectionEntry.objects.create(
            collection=self.resolve(planned.fields["collection"]),
            assignable=self.resolve(planned.fields["item"]),
            position=planned.fields["position"],
            **overrides,
            **self.shared,
        )

    def _create_restriction(self, planned):
        from n26.library import authoring

        return authoring.restrict_use(
            self.resolve(planned.fields["item"]),
            self.resolve(planned.fields["profile"]),
        )

    def _create_modifier(self, planned):
        from n26.library import authoring
        from n26.library.models.collection import CollectionSection

        places = planned.fields["places"]
        return authoring.modifier(
            planned.name,
            scope=authoring.targets_model(),
            effect=authoring.ef_places(
                self.resolve(places["category"]),
                self._standard(
                    CollectionSection,
                    f"the {places['section']!r} tier of {SKILLS_COLLECTION!r}",
                    collection__name__iexact=SKILLS_COLLECTION,
                    name__iexact=places["section"],
                ),
            ),
            attach_to=self.resolve(planned.fields["attach_to"]),
            **self.shared,
        )

    def _set_statline(self, owner, stats, columns):
        """Sheet-shaped values onto the owner's statline. Columns map to
        stat definitions by *full name* — the stat rows are shared, so a
        column's abbreviation and the stat's short name may differ (the
        weapon table's Str is the one Strength row)."""
        from n26.library import authoring
        from n26.library.models import Stat

        if not stats:
            return
        field_names = {column: Stat.derive_field_name(full) for column, full in columns}
        authoring.set_statline(
            owner,
            pack=self.plan.pack,
            **{field_names[column]: value for column, value in stats.items()},
        )


def _missing(key):
    raise LookupError(f"plan never mentions {key}")
