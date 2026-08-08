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

Sheet shapes: the weapons and equipment-list sheets are accepted in
both the current shape (a ``Name`` column, profiles as ``- `` dash
rows attached by position) and the asked-for shape (§7a/§7b: explicit
``Weapon`` and ``Profile`` columns). The ``Gang`` column is taken at
face value as a gang; the polymorphic cases (affiliations, alliances —
§4(c)) need the mapping table and are out of scope here.

Two gangs printing the same fighter name is normal, and the qualifier
(§6a) is how the library holds both: the second gang's row plans with
``qualifier = the gang's name``, said as a note in the preview.
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


def _norm(name):
    """The resolution key for a printed name: case, spacing, asterisks."""
    return re.sub(r"\s+", " ", name.strip().rstrip("*").strip()).lower()


def _clean(name):
    """The stored form: trimmed, asterisks (slot marks) off."""
    return re.sub(r"\s+", " ", name.strip().rstrip("*").strip())


_SMART = {"“": '"', "”": '"', "’": "'", "‘": "'"}


def _unsmart(value):
    for smart, plain in _SMART.items():
        value = value.replace(smart, plain)
    return value


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


def plan_ingest(weapons=(), equipment_lists=(), profiles=(), pack=None):
    """Rows from up to three sheets → one :class:`IngestPlan`.

    Order matters only inside: weapons plan first so equipment lists and
    built-ins resolve against them (resolve, never create).
    """
    from n26.library.models import get_default_pack

    plan = IngestPlan(pack or get_default_pack())
    _plan_weapons(plan, weapons)
    _plan_profiles(plan, profiles)
    _plan_equipment_lists(plan, equipment_lists)
    _backfill_prices(plan)
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


def _plan_weapons(plan, rows):
    """The weapons sheet. Both shapes: an explicit ``Weapon``/``Profile``
    column pair, or ``Name`` with positional dash rows (§7a)."""
    from n26.library.models import Weapon

    current_weapon = None  # key of the weapon dash rows attach to
    for line, row in enumerate(rows, start=1):
        source = Source("weapons", line)
        plan.remember_row(source, row)

        explicit = "Weapon" in row
        if explicit:
            weapon_name = _clean(row.get("Weapon", ""))
            profile_name = _clean(row.get("Profile", "") or "")
            is_profile_row = bool(profile_name)
        else:
            raw = row.get("Name", "")
            if _is_dash_row(raw):
                if current_weapon is None:
                    plan.problem(source, f"profile row {raw!r} has no weapon above it")
                    continue
                weapon_name = plan.get(current_weapon).name
                profile_name = _clean(_dash_name(raw))
                is_profile_row = True
            else:
                weapon_name = _clean(raw)
                profile_name = ""
                is_profile_row = False

        if not weapon_name:
            plan.problem(source, "row names no weapon")
            continue

        stats = _statline_values(row, WEAPON_COLUMNS)
        traits = [
            _plan_trait(plan, token, source)
            for token in _split_list(row.get("Traits", ""))
            if token != "-"  # nosec B105 - a dash cell, not a password
        ]
        price = _price(row.get("Credits", ""))
        unpriced = row.get("Credits", "").strip() in ("-", "")
        # The TP column, as the sheet prints it: a number is the Trading
        # Post price, "E" is equipment-list only, "-" or blank means not
        # offered there — stored as NULL, never 0.
        tp_token = row.get("TP", "").strip()
        exclusive = tp_token.upper() == "E"
        trade_points = int(tp_token) if tp_token.isdigit() else None
        category = _plan_category(
            plan,
            row.get("Type", "Weapon"),
            row.get("Subtype") or "Uncategorised",
            source,
        )
        slots = 2 if "*" in (row.get("Name", "") + row.get("Weapon", "")) else 1

        weapon_key = f"Weapon:{_norm(weapon_name)}"

        if not is_profile_row:
            # A weapon row. With stats it is also its own first profile
            # (shape A); a stat-less header (shape B) starts bare.
            action = (
                "exists"
                if _exists(plan, Weapon, name__iexact=weapon_name)
                else "create"
            )
            plan.add(
                "Weapon",
                weapon_name,
                {
                    "price": price,
                    "unpriced": unpriced,
                    "trade_point_price": trade_points,
                    "is_exclusive": exclusive,
                    "category": category,
                    "slots": slots,
                    "statline_type": WEAPON_STATLINE,  # standard content's name
                },
                source,
                key=weapon_key,
                action=action,
            )
            current_weapon = weapon_key
            if stats:
                # The weapon's own line: an *unnamed* profile — the card
                # prints it as the weapon itself (library/authoring.py,
                # add_weapon_profile).
                plan.add(
                    "WeaponProfile",
                    "",
                    {
                        "weapon": weapon_key,
                        "price": 0,
                        # The weapon's own line sells as the weapon: its
                        # TP lives on the Weapon row, never here.
                        "trade_point_price": None,
                        "is_exclusive": exclusive,
                        "stats": stats,
                        "traits": traits,
                        "position": 0,
                    },
                    source,
                    key=f"WeaponProfile:{_norm(weapon_name)}:",
                    action=action,
                )
            continue

        # A profile row.
        if not plan.get(weapon_key):
            if existing := _exists(plan, Weapon, name__iexact=weapon_name):
                plan.add(
                    "Weapon",
                    existing.name,
                    {},
                    source,
                    key=weapon_key,
                    action="exists",
                )
            else:
                plan.problem(
                    source,
                    f"profile {profile_name!r} names unknown weapon {weapon_name!r}",
                )
                continue
        position = sum(
            1
            for p in plan.planned
            if p.kind == "WeaponProfile" and p.fields.get("weapon") == weapon_key
        )
        if position == 0 and price:
            plan.problem(
                source,
                f"{weapon_name!r}: a weapon's first profile is mandatory and "
                f"free, but {profile_name!r} is priced {price}",
            )
            continue
        # WeaponProfile has no database uniqueness (design/ingest.md §8
        # stage 2) — (weapon, name) is the importer's own key, checked
        # here so a re-run marks the row exists instead of duplicating it.
        from n26.library.models import WeaponProfile

        plan.add(
            "WeaponProfile",
            profile_name,
            {
                "weapon": weapon_key,
                "price": price,
                "trade_point_price": trade_points,
                "is_exclusive": exclusive,
                "stats": stats,
                "traits": traits,
                "position": position,
            },
            source,
            key=f"WeaponProfile:{_norm(weapon_name)}:{_norm(profile_name)}",
            action="exists"
            if _exists(
                plan,
                WeaponProfile,
                weapon__name__iexact=weapon_name,
                name__iexact=profile_name,
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

    rule_names_seen = {}
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
            rule_name, annotation = _name_and_annotation(token)
            key = f"Rule:{_norm(rule_name)}:{annotation.lower()}"
            clash = rule_names_seen.get(_norm(rule_name))
            if clash is not None and clash != annotation.lower():
                plan.problem(
                    source,
                    f"rule {rule_name!r} appears with annotations "
                    f"({clash!r}, {annotation.lower()!r}) but rules are "
                    f"unique on name alone — needs the §5d migration",
                )
                continue
            rule_names_seen[_norm(rule_name)] = annotation.lower()
            if not plan.get(key):
                plan.add(
                    "Rule",
                    rule_name,
                    {"annotation": annotation},
                    source,
                    key=key,
                    action="exists"
                    if _exists(plan, Rule, name__iexact=rule_name)
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
                plan.problem(
                    source,
                    f"{name!r} comes with {item!r}, which no sheet defines "
                    f"and the pack does not hold — built-ins resolve, "
                    f"never create",
                )
                continue
            members.append((resolved, {}))

        # Two gangs printing the same fighter name is normal, and the
        # qualifier (§6a) is how the library holds both. The first row
        # keeps the bare name; a second gang's row is qualified with its
        # gang's name — author-facing only, the card prints the name alone.
        plain_key = f"Profile:{_norm(name)}"
        planned_plain = plan.get(plain_key)
        existing_plain = _exists(plan, Profile, name__iexact=name, qualifier__iexact="")
        if planned_plain is not None:
            name_holder = planned_plain.fields["gang_type"]
        elif existing_plain is not None:
            name_holder = f"GangType:{_norm(existing_plain.gang_type.name)}"
        else:
            name_holder = None

        qualifier = ""
        if name_holder is not None and name_holder != gang_key:
            qualifier = gang_name
            plan.problem(
                source,
                f"profile {name!r} is also another gang's — this one is "
                f"qualified {qualifier!r} (§6a); authors see the qualifier, "
                f"players never do",
                severity="note",
            )

        profile_key = plain_key if not qualifier else f"{plain_key}:{_norm(qualifier)}"
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
    wargear, or one in the pack. Returns its key, or None."""
    from n26.library.models import Wargear, Weapon

    for kind in ("Weapon", "Wargear"):
        key = f"{kind}:{_norm(name)}"
        if plan.get(key):
            return key
    for kind, model in (("Weapon", Weapon), ("Wargear", Wargear)):
        if existing := _exists(plan, model, name__iexact=_clean(name)):
            return plan.add(
                "Weapon" if model is Weapon else "Wargear",
                existing.name,
                {},
                Source("resolution", 0),
                key=f"{kind}:{_norm(name)}",
                action="exists",
            ).key
    return None


def _plan_equipment_lists(plan, rows):
    """The equipment lists sheet: a Collection per gang, an entry per
    line. Weapon lines resolve; wargear lines create the wargear."""
    from n26.library.models import Wargear
    from n26.library.models.collection import Collection

    current_weapon = {}  # gang -> weapon key, for dash rows
    positions = TallyCounter()
    for line, row in enumerate(rows, start=1):
        source = Source("equipment_lists", line)
        plan.remember_row(source, row)
        gang = _clean(row.get("Gang", ""))
        collection_name = f"{gang} equipment list"
        collection_key = f"Collection:{_norm(collection_name)}"
        if not plan.get(collection_key):
            plan.add(
                "Collection",
                collection_name,
                {},
                source,
                key=collection_key,
                action="exists"
                if _exists(plan, Collection, name__iexact=collection_name)
                else "create",
            )

        row_type = (row.get("Type") or "").strip()
        price = _price(row.get("Credits", ""))
        priced = row.get("Credits", "").strip().isdigit()

        if row_type == "Wargear":
            name = _clean(row.get("Name", ""))
            category = _plan_category(
                plan, "Wargear", row.get("Subtype") or "Uncategorised", source
            )
            item_key = f"Wargear:{_norm(name)}"
            if not plan.get(item_key):
                plan.add(
                    "Wargear",
                    name,
                    {"category": category, "prices_seen": [], "price": 0},
                    source,
                    key=item_key,
                    action="exists"
                    if _exists(plan, Wargear, name__iexact=name)
                    else "create",
                )
        else:
            # A weapon line: explicit columns or Name with dash rows.
            if "Weapon" in row:
                weapon_name = _clean(row.get("Weapon", ""))
                profile_name = _clean(row.get("Profile", "") or "")
            else:
                raw = row.get("Name", "")
                if _is_dash_row(raw):
                    parent = current_weapon.get(gang)
                    if parent is None:
                        plan.problem(
                            source, f"profile line {raw!r} has no weapon above it"
                        )
                        continue
                    weapon_name = plan.get(parent).name
                    profile_name = _clean(_dash_name(raw))
                else:
                    weapon_name, profile_name = _clean(raw), ""

            weapon_key = f"Weapon:{_norm(weapon_name)}"
            resolved = _resolve_item(plan, weapon_name)
            if resolved != weapon_key:
                plan.problem(
                    source,
                    f"{gang} list sells {weapon_name!r}, which no sheet "
                    f"defines and the pack does not hold — resolve, never "
                    f"create (§7b)",
                )
                continue
            current_weapon[gang] = weapon_key
            if profile_name:
                item_key = f"WeaponProfile:{_norm(weapon_name)}:{_norm(profile_name)}"
                if not plan.get(item_key):
                    plan.problem(
                        source,
                        f"{gang} list sells {weapon_name!r} profile "
                        f"{profile_name!r}, which the weapons sheet does not "
                        f"define",
                    )
                    continue
            else:
                item_key = weapon_key

        restriction = (row.get("Restrictions") or "").strip()
        entry_fields = {
            "collection": collection_key,
            "item": item_key,
            "position": positions[collection_key],
            "list_price": price if priced else None,
        }
        positions[collection_key] += 1
        entry = plan.add(
            "CollectionEntry",
            f"{plan.get(item_key).name} in {gang} equipment list",
            entry_fields,
            source,
            key=f"CollectionEntry:{_norm(gang)}:{item_key}",
            action="exists"
            if _entry_exists(plan, collection_name, item_key)
            else "create",
        )
        if priced and (item := plan.get(item_key)) and item.kind == "Wargear":
            if item.action == "create":
                item.fields["prices_seen"].append(price)

        if restriction:
            match = re.match(r"^(.*?)\s+only$", restriction, flags=re.IGNORECASE)
            profile_ref = match and _profile_ref(plan, match.group(1), gang)
            if profile_ref:
                plan.add(
                    "Restriction",
                    f"{plan.get(item_key).name} ({restriction})",
                    {"item": item_key, "profile": profile_ref},
                    source,
                    key=f"Restriction:{entry.key}",
                    action=entry.action,
                )
            elif match:
                plan.problem(
                    source,
                    f"restriction {restriction!r} names a profile no sheet "
                    f"defines and the pack does not hold",
                )
            else:
                plan.problem(
                    source,
                    f"restriction {restriction!r} is not expressible yet — "
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

    kind, *rest = item_key.split(":")
    column = {
        "Weapon": "weapon",
        "WeaponProfile": "weapon_profile",
        "Wargear": "wargear",
    }[kind]
    filters = {f"{column}__name__iexact": plan.get(item_key).name}
    if kind == "WeaponProfile":
        filters["weapon_profile__weapon__name__iexact"] = rest[0]
    return CollectionEntry.objects.filter(
        pack=plan.pack,
        collection__name__iexact=collection_name,
        **filters,
    ).exists()


def _backfill_prices(plan):
    """Second pass on prices (§5b): reference price on the item, list
    disagreement becomes a per-entry override.

    Wargear reference is the modal list price. A weapon printed ``-``
    takes its reference from the lists the same way; one printed with a
    number keeps it. Entries matching the reference carry no override.
    """
    from n26.library.models import Wargear

    references = {}
    for planned in list(plan.planned):
        if planned.kind != "Wargear":
            continue
        if planned.action == "exists":
            row = _exists(plan, Wargear, name__iexact=planned.name)
            if row:
                references[planned.key] = row.price
            continue
        seen = planned.fields.pop("prices_seen", [])
        if seen:
            reference = TallyCounter(seen).most_common(1)[0][0]
            references[planned.key] = reference
            plan._replace(planned.key, price=reference)

    weapon_list_prices = {}
    for planned in plan.planned:
        if (
            planned.kind == "CollectionEntry"
            and planned.fields["list_price"] is not None
        ):
            weapon_list_prices.setdefault(planned.fields["item"], []).append(
                planned.fields["list_price"]
            )
    from n26.library.models import Weapon

    for planned in list(plan.planned):
        if planned.kind != "Weapon":
            continue
        if planned.action == "exists":
            row = _exists(plan, Weapon, name__iexact=planned.name)
            if row:
                references[planned.key] = row.price
        elif planned.fields.get("unpriced"):
            seen = weapon_list_prices.get(planned.key, [])
            if seen:
                reference = TallyCounter(seen).most_common(1)[0][0]
                references[planned.key] = reference
                plan._replace(planned.key, price=reference)
        else:
            references[planned.key] = planned.fields["price"]

    for planned in list(plan.planned):
        if planned.kind != "CollectionEntry":
            continue
        list_price = planned.fields.pop("list_price")
        reference = references.get(planned.fields["item"])
        override = (
            list_price
            if list_price is not None
            and reference is not None
            and list_price != reference
            else None
        )
        plan._replace(planned.key, price_override=override)


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
            "Weapon": Weapon,
            "Wargear": Wargear,
            "Collection": Collection,
        }
        if kind in simple:
            return (
                simple[kind]
                .objects.filter(name__iexact=planned.name, **self.shared)
                .first()
            )
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
            return Rule.objects.filter(name__iexact=planned.name, **self.shared).first()
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
