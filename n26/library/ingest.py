"""Import CSV spreadsheets through a read, plan and perform pipeline.

read_csv() parses sheet data. plan_ingest() reads the library and produces
Planned records, field changes and problems without writing. perform() applies
that plan in dependency order within one transaction.

UploadedSheet stores one file per author and sheet type. Preview and import
requests read these files and rebuild the plan against the current library.

References between sheets must match planned or existing content. Missing
references are reported rather than creating incomplete catalogue items.
Built-in equipment is free; its price is independent of equipment-list prices.
Standard content must be created from Foundations before an import.

Equipment lists preserve omitted entries and existing positions. New entries
append after the last stored position. Supplied entries can update prices.
Weapon traits and fighter skill grids are replaced; built-in kit and use
restrictions retain omitted members. A newly named equipment list replaces
the previous list in a fighter's built-ins.

The four supported sheets are Equipment, Weapon profiles, Equipment lists and
All Profiles. Item identity combines name, profile, category and section;
names alone can match multiple weapons. Qualifiers distinguish catalogue
items with otherwise identical identities.

Trading Post membership is derived from trade-point prices. Ingest sets those
prices and exclusivity from the sheet's TP column rather than creating entries.
"""

import csv
import io
import random
import re
from collections import Counter as TallyCounter
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max, Q

from n26.library.models.profile import TYPE_NAMES
from n26.library.sheets import SHEET_NAMES
from n26.library.standard_content import (
    GANG_LIST_SECTION,
    MODEL_CHARACTERISTICS,
    SKILLS_COLLECTION,
    SKILLS_SECTION,
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


#: Every planned record must be settled before perform() can execute it.
UNSETTLED = "pending"

#: Records resolved from the library are references, not import writes.
RESOLUTION = "resolution"

#: The plan key for a fighter's opening XP. The counter itself is
#: standard content, so it is never planned — it is named as a member
#: of a built-ins set and resolved by its fixed name.
XP_MEMBER = "Counter:xp"


@dataclass(frozen=True)
class Planned:
    """A library record to create, update, retain or resolve.

    Other planned records reference its key through fields. The settling pass
    sets action and changes after matching against the library. existing stores
    the matched primary key so updates target the record shown in the preview.
    """

    kind: str
    key: str
    name: str
    fields: dict
    action: str
    source: Source
    changes: dict = field(default_factory=dict)
    existing: str | None = None

    def as_dict(self):
        return {
            "kind": self.kind,
            "key": self.key,
            "name": self.name,
            "fields": self.fields,
            "action": self.action,
            "source": self.source.as_dict(),
            "changes": self.changes,
            "existing": self.existing,
        }


@dataclass(frozen=True)
class Problem:
    """A blocking error or informational note associated with a sheet line.

    Errors prevent the entire import. Notes report skipped content or retained
    values and allow the rest of the import to proceed.
    """

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
    """``"Ammo (5+)"`` → ``("Ammo", "5+")``; ``"Melee"`` → ``("Melee", "")``.

    The authoring layer's rule, borrowed rather than restated: a person
    typing ``Leash (3")`` into the admin and a sheet cell saying the
    same must land on the same row (``authoring.split_annotation``).
    """
    from n26.library.authoring import split_annotation

    return split_annotation(token)


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
    """Planned records, field changes and problems for the preview and import."""

    def __init__(self, pack):
        self.pack = pack
        self.planned = []  # ordered Planned rows
        self.problems = []
        self._by_key = {}
        self._at = {}  # key -> its place in `planned`, so settling is cheap
        self._rows = {}  # (sheet, line) -> the raw csv row

    @property
    def ok(self):
        return not any(p.severity == "error" for p in self.problems)

    def get(self, key):
        return self._by_key.get(key)

    def add(self, kind, name, fields, source, key=None):
        """Add a record before the settling pass determines its action."""
        key = key or f"{kind}:{_norm(name)}"
        if key in self._by_key:
            return self._by_key[key]
        row = Planned(
            kind=kind,
            key=key,
            name=name,
            fields=fields,
            action=UNSETTLED,
            source=source,
        )
        self._at[key] = len(self.planned)
        self.planned.append(row)
        self._by_key[key] = row
        return row

    def settle(self, planned, action, changes=None, existing=None):
        """Store the action, changed fields and matched primary key for a planned record."""
        settled = Planned(
            kind=planned.kind,
            key=planned.key,
            name=planned.name,
            fields=planned.fields,
            action=action,
            source=planned.source,
            changes=changes or {},
            existing=existing,
        )
        self._by_key[planned.key] = settled
        self.planned[self._at[planned.key]] = settled
        return settled

    def problem(self, source, message, severity="error"):
        self.problems.append(
            Problem(
                sheet=source.sheet, line=source.line, message=message, severity=severity
            )
        )

    def remember_row(self, source, row):
        self._rows[(source.sheet, source.line)] = dict(row)

    # -- preview ------------------------------------------------------------

    def preview(self, examples=3, sample=False, seed=None):
        """Return counts, changes, problems and sample sheet lines as serialisable data."""
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
            "changes": [
                {
                    "kind": row.kind,
                    "name": row.name,
                    "key": row.key,
                    "source": row.source.as_dict(),
                    "changes": row.changes,
                }
                for row in self.planned
                if row.action == "update"
            ],
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


def _fold_column(name):
    """A column heading's matching form: case and spacing set aside."""
    return re.sub(r"\s+", " ", str(name).strip()).casefold()


class Row(dict):
    """A CSV row with case-insensitive column lookup.

    Keep original headers and values for display in the preview.
    """

    def __init__(self, row):
        super().__init__(row)
        # Built once per row rather than per lookup: a sheet is tens of
        # thousands of gets, and a fold on each is the whole read.
        self._folded = {
            _fold_column(key): value for key, value in row.items() if key is not None
        }

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return self._folded.get(_fold_column(key), default)


def read_csv(text):
    """CSV text → rows. The file interface: everything after this is rows."""
    return [Row(row) for row in csv.DictReader(io.StringIO(text.strip()))]


# --- Held uploads: the bytes a preview and its import both read --------------


class SheetRefused(ValueError):
    """An unreadable or unsupported upload, with an explanation for the upload form."""


def store_sheet(owner, sheet, upload):
    """Store an author's CSV upload for one sheet type.

    Validate UTF-8 encoding and require at least one data row. Replace the existing
    upload record and delete the previous file only after the transaction commits.
    """
    from n26.library.models.staging import MAX_SHEET_BYTES, UploadedSheet
    from n26.write_pause import write_guard

    if sheet not in SHEET_NAMES:
        raise SheetRefused(f"{sheet!r} is not one of the sheets.")
    if upload.size > MAX_SHEET_BYTES:
        raise SheetRefused(
            f"File size is {upload.size // 1024}KB. The limit is "
            f"{MAX_SHEET_BYTES // 1024}KB."
        )
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as refused:
        raise SheetRefused(
            "The file is not UTF-8 text. Export it as CSV (UTF-8) and upload it again."
        ) from refused
    rows = read_csv(text)
    if not rows:
        raise SheetRefused(
            "No data rows found. Upload a CSV with a header and at least one data row."
        )

    with transaction.atomic(), write_guard():
        # Serialise replacements of an author's existing upload.
        held = (
            UploadedSheet.objects.select_for_update()
            .filter(owner=owner, sheet=sheet)
            .first()
        ) or UploadedSheet(owner=owner, sheet=sheet)
        superseded = held.file.name
        held.filename = upload.name or f"{sheet}.csv"
        held.lines = len(rows)
        held.file.save(f"{sheet}.csv", ContentFile(raw), save=False)
        held.save()
        if superseded and superseded != held.file.name:
            transaction.on_commit(
                lambda storage=held.file.storage, name=superseded: storage.delete(name)
            )
    return held


def held_sheets(owner):
    """Return this author's uploaded files, keyed by sheet type."""
    from n26.library.models.staging import UploadedSheet

    return {
        held.sheet: held
        for held in UploadedSheet.objects.filter(owner=owner)
        if held.sheet in SHEET_NAMES
    }


def rows_of(held):
    """Parse each uploaded CSV file into rows for the planner."""
    return {name: read_csv(upload.text()) for name, upload in held.items()}


def discard_sheets(owner, sheets=None):
    """Delete selected uploads and return the number removed.

    Delete stored files after the database transaction commits. Omitting sheets
    selects all of the author's uploads.
    """
    from n26.library.models.staging import UploadedSheet
    from n26.write_pause import write_guard

    held = UploadedSheet.objects.filter(owner=owner)
    if sheets is not None:
        held = held.filter(sheet__in=sheets)
    with transaction.atomic(), write_guard():
        uploads = list(held.select_for_update())
        UploadedSheet.objects.filter(pk__in=[upload.pk for upload in uploads]).delete()
        for upload in uploads:
            if upload.file.name:
                transaction.on_commit(
                    lambda storage=upload.file.storage, name=upload.file.name: (
                        storage.delete(name)
                    )
                )
    return len(uploads)


# --- Planning ----------------------------------------------------------------


def plan_ingest(
    equipment=(),
    weapon_profiles=(),
    equipment_lists=(),
    profiles=(),
    pack=None,
):
    """Plan catalogue items, weapon profiles, equipment lists and fighters.

    Resolve restrictions after fighter profiles are available. The settling pass
    matches planned records against the library and calculates field changes.
    Planning reads the database without writing.
    """
    from n26.library.models import get_default_pack

    plan = IngestPlan(pack or get_default_pack())
    # The catalogue pass needs to know which things have a profile,
    # because that is what decides whether a "Wargear" row is really a
    # weapon (see _plan_equipment). The statlines themselves are planned
    # after, once there is something for them to hang on.
    statlined = {ItemId.of(row).key for row in weapon_profiles}
    profile_prices = _plan_equipment(plan, equipment, statlined)
    _plan_weapon_profiles(plan, weapon_profiles, profile_prices)
    pending_restrictions = _plan_equipment_lists(plan, equipment_lists)
    _plan_profiles(plan, profiles)
    _plan_restrictions(plan, pending_restrictions)
    _settle(plan)
    return plan


def _exists(plan, model, **filters):
    return model.objects.filter(pack=plan.pack, **filters).first()


def _plan_category(plan, section, name, source, section_position=0):
    """A category and the heading above it. ``section_position`` is the
    order that heading reads in, and applies only where the plan founds
    it — a heading already in the pack keeps the order it has."""
    key = f"Category:{_norm(section)}:{_norm(name)}"
    if plan.get(key):
        return key
    plan.add(
        "Category",
        _clean(name),
        {"section": section.strip(), "section_position": section_position},
        source,
        key=key,
    )
    return key


def _plan_trait(plan, token, source):
    name, annotation = _name_and_annotation(token)
    key = f"Trait:{_norm(name)}:{annotation.lower()}"
    if plan.get(key):
        return key
    plan.add("Trait", name, {"annotation": annotation}, source, key=key)
    return key


#: The ``Assignable`` column's words → the kinds a plan speaks in.
EQUIPMENT_KINDS = {
    "weapon": "Weapon",
    "wargear": "Wargear",
    "weapon accessory": "WeaponAccessory",
    "weapon profile": "WeaponProfile",
}

#: The kinds that are a name, a home and a price and nothing more. They
#: differ only in which table they land in, so they are planned by one
#: branch rather than one apiece.
PLAIN_KINDS = ("Wargear", "WeaponAccessory")


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
        # No printed price of its own: whatever list offers it says so.
        "unpriced": not cost.isdigit(),
        "trade_point_price": None if exclusive or not trade.isdigit() else int(trade),
        "is_exclusive": exclusive,
    }


def _plan_equipment(plan, rows, statlined=frozenset()):
    """Plan catalogue items and reference prices.

    Wargear with weapon statlines becomes a weapon that occupies no weapon slots.
    Defer weapon-profile prices until the statline sheet is processed.
    """
    # Pass 1: which printed names does more than one item claim? Those
    # want the author-facing qualifier — a power fist is Exo kit
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
                f"Unknown Assignable {said!r}. Supported types: "
                f"{', '.join(sorted(set(EQUIPMENT_KINDS.values())))}.",
            )
            continue

        ident = ItemId.of(row)
        if not ident.name:
            plan.problem(source, "Missing item name.")
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
            # This sheet prices a profile; the statline sheet is what
            # says the profile exists at all. Hold the price for that pass.
            if not ident.profile:
                plan.problem(
                    source,
                    f"{ident.name!r} needs a Profile value for the Weapon Profile type. "
                    f"Use Weapon for the weapon's base price.",
                )
                continue
            profile_prices[ident.key] = priced
            continue

        category = _plan_category(plan, ident.section, ident.category, source)

        # A grenade: typed Wargear because it does not count against the
        # weapons held, but it has a profile, so it is a weapon that
        # takes no slots. Slots carry the fact the typing was standing in
        # for; the category is left alone, so it still homes as Wargear.
        holds_no_slot = kind == "Wargear" and ident.key in statlined
        if holds_no_slot:
            kind = "Weapon"
            key = f"Weapon:{ident.key}"

        if kind in PLAIN_KINDS:
            plan.add(
                kind,
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
        )

    return profile_prices


def _plan_weapon_profiles(plan, rows, prices):
    """Plan weapon statlines, traits, ammunition and firing modes."""
    groups = {}
    seen = {}
    for line, row in enumerate(rows, start=1):
        source = Source("weapon_profiles", line)
        plan.remember_row(source, row)

        if (row.get("Sub-profile") or "").strip():
            plan.problem(
                source,
                f"{ItemId.of(row).printed!r} has a Sub-profile — a weapon "
                f"within a weapon is hand-authored, not imported",
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
                f"sheet defines no such thing — ignored, because an "
                f"import resolves what the sheets name and never "
                f"invents it",
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


#: The headings the profiles sheet homes fighters under, and the order
#: the hire list reads them in: the gang's own list first, everything
#: hired beside it after. A blank ``Section`` cell means the gang list —
#: the sheet only spells out the other one. The gang list's own heading
#: is named in standard_content, because the founding-budget seed reads
#: it too and two statements of it would drift.
PROFILE_SECTIONS = {GANG_LIST_SECTION: 0, "Supplementary Fighters": 1}


def _plan_home(plan, row, name, source):
    """Resolve a fighter's Section and Category to its hire-list category key."""
    section = _clean(row.get("Section") or "") or GANG_LIST_SECTION
    category = _clean(row.get("Category") or "")
    if not category:
        plan.problem(
            source,
            f"{name!r} has no Category. It will be imported without a category "
            f"in the hire list.",
            severity="note",
        )
        return None
    return _plan_category(
        plan,
        section,
        category,
        source,
        # A heading the sheet invents sorts after both known ones rather
        # than tying with the gang list at 0, where the tie-break is
        # alphabetical and would interleave it with the gang's own
        # fighters.
        section_position=PROFILE_SECTIONS.get(section, len(PROFILE_SECTIONS)),
    )


def _plan_profiles(plan, rows):
    """Plan fighter profiles, statlines, starting equipment and skill access.

    The sheet's Rating column supplies the profile's reference price.
    """
    from n26.library.models import Profile

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
                f"row that belongs on another sheet",
            )
            continue

        gang_name = _clean(row.get("Gang", ""))
        if not gang_name:
            # A missing gang name would create a blank option on the gang page.
            plan.problem(
                source,
                f"Missing Gang for {name!r}. Set the gang that can hire this profile.",
            )
            continue
        gang_key = f"GangType:{_norm(gang_name)}"
        if not plan.get(gang_key):
            plan.add("GangType", gang_name, {}, source, key=gang_key)

        members = []  # (key, extras) pairs for the built-ins set

        for subtype in _split_list(row.get("Subtype(s)", "")):
            key = f"Subtype:{_norm(subtype)}"
            if not plan.get(key):
                plan.add("Subtype", _clean(subtype), {}, source, key=key)
            members.append((key, {}))

        xp = (row.get("Starting XP") or "").strip()
        if xp.isdigit() and int(xp):
            members.append((XP_MEMBER, {"amount": int(xp)}))

        for token in _split_list(row.get("Special Rules", "")):
            # A rule's annotation is part of its identity, as a trait's
            # is: Leash (3") and Leash (9") are two rules sharing a
            # printed name, and both must exist.
            rule_name, annotation = _name_and_annotation(token)
            key = f"Rule:{_norm(rule_name)}:{annotation.lower()}"
            if not plan.get(key):
                plan.add("Rule", rule_name, {"annotation": annotation}, source, key=key)
            members.append((key, {}))

        skills_column = next(
            (column for column in row if column.startswith("Default skills")), None
        )
        for skill in _split_list(row.get(skills_column, "") if skills_column else ""):
            key = f"Skill:{_norm(skill)}"
            if not plan.get(key):
                plan.add("Skill", _clean(skill), {}, source, key=key)
            members.append((key, {}))

        for item in _split_list(row.get("Default assignment", "")):
            resolved = _resolve_item(plan, item)
            if resolved is None:
                # Unresolved built-in equipment does not prevent profile import.
                plan.problem(
                    source,
                    f"Built-in equipment {item!r} for {name!r} was not found in "
                    f"the sheets or library. The profile will be imported without it.",
                    severity="note",
                )
                continue
            members.append((resolved, {}))

        # A fighter reaches an equipment list by holding it among its
        # built-ins, which is why the column lands here rather than
        # anywhere else: access is a thing the fighter comes with.
        buys_at = _clean(row.get(EQUIPMENT_LIST_COLUMN) or "")
        if buys_at:
            listed = _resolve_equipment_list(plan, buys_at)
            if listed is None:
                plan.problem(
                    source,
                    f"{name!r} references {buys_at!r} in the {EQUIPMENT_LIST_COLUMN} column. "
                    f"The list was not found in the sheets or library. "
                    f"The profile will be imported without it.",
                    severity="note",
                )
            else:
                members.append((listed, {}))

        # Two gangs printing the same fighter name is normal, and the
        # qualifier is how the library holds both — author-facing
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
                f"Profile {name!r} already exists for another gang. This profile "
                f"will be qualified as {qualifier!r}, visible only to authors.",
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
            )

        # The grid is planned before the fighter, because the fighter's
        # own row is where the whole grid is stated: the sheet naming a
        # set in one tier and no longer in the other is a difference to
        # the *fighter*, and one modifier row cannot see it.
        grid = _plan_skill_grid(plan, row, profile_key, label, source)

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
                "category": _plan_home(plan, row, name, source),
                "skill_grid": grid,
            },
            source,
            key=profile_key,
        )


def _plan_skill_grid(plan, row, profile_key, label, source):
    """Plan Primary and Secondary skill-set placements for a fighter profile."""
    keys = []
    for column, section in (
        ("Primary Skill Sets", "Primary"),
        ("Secondary Skill Sets", "Secondary"),
    ):
        for skill_set in _split_list(row.get(column, "")):
            category = _plan_category(plan, "Skills", skill_set, source)
            plan.add(
                "Modifier",
                f"{label}: {skill_set} is {section}",
                {
                    "attach_to": profile_key,
                    "places": {"category": category, "section": section},
                },
                source,
                key=f"Modifier:{profile_key}:{_norm(skill_set)}:{section.lower()}",
            )
            keys.append(f"Modifier:{profile_key}:{_norm(skill_set)}:{section.lower()}")
    return keys


def _resolve_item(plan, name):
    """A name that must already mean something: a planned weapon or
    wargear, or one in the pack. Returns its key, or None.

    The catalogue is keyed by ID, which carries the category — but a
    fighter's built-in kit prints a bare name and no category, so this
    is the one place resolution goes by name alone. A name two catalogue
    rows share cannot be resolved that way and is refused rather than
    guessed at.
    """
    from n26.library.models import Wargear, Weapon, WeaponAccessory

    wanted = _norm(name)
    hits = [
        planned
        for planned in plan.planned
        if planned.kind in ("Weapon", *PLAIN_KINDS) and _norm(planned.name) == wanted
    ]
    if len(hits) == 1:
        return hits[0].key
    if len(hits) > 1:
        return None  # ambiguous by name; the ID is what tells them apart

    # Every kind at once, and every row of each: a sight and a piece of
    # wargear may print one name, as may two rows of one kind told apart
    # by their qualifier. Taking the first would answer by the order
    # these are asked in, which is no answer at all.
    found = [
        (kind, row)
        for kind, model in (
            ("Weapon", Weapon),
            ("Wargear", Wargear),
            ("WeaponAccessory", WeaponAccessory),
        )
        for row in model.objects.filter(pack=plan.pack, name__iexact=_clean(name))
    ]
    if len(found) != 1:
        return None
    kind, existing = found[0]
    return plan.add(
        kind,
        existing.name,
        {
            "price": existing.price,
            "unpriced": False,
            "qualifier": existing.qualifier,
        },
        Source(RESOLUTION, 0),
        key=f"{kind}:resolved|{wanted}",
    ).key


#: What the ``Collection`` column says these rows build. One kind today;
#: the column exists so the sheet can grow others without a new file.
EQUIPMENT_LIST_COLLECTION = "Equipment List"

#: The ``All Profiles`` column naming the list a fighter buys from. It
#: holds a ``Title`` from the equipment-lists sheet — "Escher" — because
#: that is the word an author has in front of them; the whole collection
#: name is understood as well.
EQUIPMENT_LIST_COLUMN = "Equipment List"


def _collection_name(title):
    """The collection a ``Title`` names — "Ash Waste Nomads Equipment List".

    The sheet splits the kind (``Collection``) from the name (``Title``);
    the library holds one row, so the two are put back together. Saying
    the kind matters: a gang type and its list would otherwise be one
    word apart in every dropdown.
    """
    return f"{_clean(title)} {EQUIPMENT_LIST_COLLECTION}"


def _resolve_equipment_list(plan, title):
    """Resolve an equipment-list title against planned or existing collections."""
    from n26.library.models.collection import Collection

    for name in (_collection_name(title), _clean(title)):
        key = f"Collection:{_norm(name)}"
        if plan.get(key):
            return key
        if existing := _exists(plan, Collection, name__iexact=name):
            return plan.add(
                "Collection",
                existing.name,
                {},
                Source(RESOLUTION, 0),
                key=key,
            ).key
    return None


def _plan_equipment_lists(plan, rows):
    """Plan entries for each collection named in the equipment-lists sheet.

    Resolve items by name, profile, category and section. Add price overrides where
    the list differs from the catalogue. Defer fighter restrictions until profiles
    are planned.
    """
    pending_restrictions = []
    positions = TallyCounter()
    listed = {}  # collection key -> the entry keys this upload names
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
            # Membership lets the preview name entries omitted from
            # this upload without removing them.
            plan.add(
                "Collection",
                name,
                {"entries": listed.setdefault(collection_key, [])},
                source,
                key=collection_key,
            )

        ident = ItemId.of(row)
        if not ident.name:
            plan.problem(source, "Missing item name.")
            continue

        item_key = _resolve_by_id(plan, ident)
        if item_key is None:
            plan.problem(
                source,
                f"{title} lists {ident.printed!r}, which was not found in the "
                f"equipment sheet or library. This entry will be skipped. "
                f"Create the item first if it needs manual authoring.",
                severity="note",
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
        )
        listed[collection_key].append(entry_key)
        positions[collection_key] += 1

        restriction = (row.get("Restrictions") or "").strip()
        if restriction:
            pending_restrictions.append(
                (source, restriction, item_key, title, entry.key)
            )

    return pending_restrictions


def _override(item, list_price):
    """Return the list price override, or None to use the catalogue price."""
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

    A listing that carries a ``Profile`` is offering one profile of a
    weapon — a grenade type, an ammo — which is its own listable thing;
    everything else is named directly.

    Against the pack the whole ID is used, category and all, because a
    printed name is not an identity: matching "Power fist" by name alone
    would take whichever row came first and could hand a list the wrong
    weapon at the wrong price. Only where the name turns out to be the
    pack's alone does it fall back to that, which is what lets a
    hand-authored item filed under its own category still be found.
    """
    from n26.library.models import (
        Wargear,
        Weapon,
        WeaponAccessory,
        WeaponProfile,
    )

    if ident.profile:
        candidates = [
            (
                "WeaponProfile",
                WeaponProfile,
                {"weapon__name__iexact": ident.name, "name__iexact": ident.profile},
                {
                    "weapon__category__name__iexact": ident.category,
                    "weapon__category__section__name__iexact": ident.section,
                },
            )
        ]
    else:
        homed = {
            "category__name__iexact": ident.category,
            "category__section__name__iexact": ident.section,
        }
        candidates = [
            ("Weapon", Weapon, {"name__iexact": ident.name}, homed),
            ("Wargear", Wargear, {"name__iexact": ident.name}, homed),
            (
                "WeaponAccessory",
                WeaponAccessory,
                {"name__iexact": ident.name},
                homed,
            ),
        ]

    for kind, _model, _by_name, _home in candidates:
        key = f"{kind}:{ident.key}"
        if plan.get(key):
            return key

    # Not planned this run — the pack may already hold it, which is what
    # a second upload and the hand-authored items both look like.
    for kind, model, by_name, home in candidates:
        found = _exists(plan, model, **by_name, **home)
        if found is None:
            named = model.objects.filter(pack=plan.pack, **by_name)
            found = named.first() if named.count() == 1 else None
        if found is not None:
            return _plan_existing(plan, kind, found, ident).key
    return None


def _plan_existing(plan, kind, found, ident):
    """A row the pack already holds, as a planned "exists" line.

    It carries what anything reading the plan will ask of it — the
    qualifier that tells two same-named rows apart, and for a weapon
    profile the weapon it hangs on, which is how an entry knows whether
    it is already listed. A key left off here surfaces much later as a
    missing lookup on somebody else's line.
    """
    fields = {
        "price": found.price,
        "unpriced": False,
        "qualifier": found.qualifier,
    }
    if kind == "WeaponProfile":
        weapon_key = f"Weapon:{ident.parent.key}"
        if not plan.get(weapon_key):
            plan.add(
                "Weapon",
                found.weapon.name,
                {
                    "price": found.weapon.price,
                    "unpriced": False,
                    "qualifier": found.weapon.qualifier,
                },
                Source(RESOLUTION, 0),
                key=weapon_key,
            )
        fields["weapon"] = weapon_key
    return plan.add(
        kind,
        found.name,
        fields,
        Source(RESOLUTION, 0),
        key=f"{kind}:{ident.key}",
    )


def _plan_restrictions(plan, pending):
    """Resolve supported use restrictions after fighter profiles are planned.

    Store restrictions on collection entries so other lists remain unaffected.
    Report unsupported rules, such as per-gang limits, as notes.
    """
    for source, restriction, item_key, gang, entry_key in pending:
        match = re.match(r"^(.*?)\s+only$", restriction, flags=re.IGNORECASE)
        if match is None:
            plan.problem(
                source,
                f"restriction {restriction!r} is not a restriction on use — "
                f"imported without it",
                severity="note",
            )
            continue

        named = match.group(1)
        allows = _profile_ref(plan, named, gang)
        if allows:
            plan.add(
                "Restriction",
                f"{plan.get(item_key).name} in {gang} ({restriction})",
                {"entry": entry_key, "allows": allows},
                source,
                key=f"Restriction:{entry_key}",
            )
        else:
            plan.problem(
                source,
                f"No profile matches restriction {restriction!r} in the sheets "
                f"or library. The entry will be imported without this restriction.",
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
                Source(RESOLUTION, 0),
                key=f"Profile:{_norm(name)}{suffix}",
            ).key
    return None


# --- Settling: what the pack already holds -----------------------------------


@dataclass(frozen=True)
class Fields:
    """What a sheet claims to know about one kind, split three ways.

    ``identity`` is what the lookup matched on, so it agrees by
    construction and is never a difference. ``updatable`` is what a
    re-upload may rewrite. ``ignored`` says, deliberately, that a
    planned field is not a claim about a row the pack already holds —
    a planning-time hint, or something that only applies where the row
    is being founded.
    """

    identity: tuple = ()
    updatable: tuple = ()
    ignored: tuple = ()

    def all(self):
        return {*self.identity, *self.updatable, *self.ignored}


#: What these four spreadsheets are authoritative about, per kind.
#:
#: This is a statement about the *sheets*, not about the content: a
#: second importer reading different columns would claim different
#: things, and the model stays the authority on what is valid either
#: way. Every field the planner puts in a row's ``fields`` appears in
#: exactly one of the three lists, and a test proves the partition is
#: total — a new planned field then fails a test rather than being
#: quietly left out of every difference.
SHEET_FIELDS = {
    "Category": Fields(
        identity=("section",),
        # A heading's reading order applies only where this upload
        # founds it; one already in the pack keeps the order it has.
        ignored=("section_position",),
    ),
    "Trait": Fields(identity=("annotation",)),
    "Rule": Fields(identity=("annotation",)),
    "GangType": Fields(),
    "Subtype": Fields(),
    "Skill": Fields(),
    "Collection": Fields(
        # The section where unplaced entries land is founded with the
        # collection; one already in the pack keeps the schema it has.
        ignored=("entries", "default_section"),
    ),
    "Weapon": Fields(
        identity=("qualifier",),
        updatable=(
            "price",
            "trade_point_price",
            "is_exclusive",
            "slots",
            "category",
        ),
        # "unpriced" is how the catalogue says "the lists price this",
        # which the entry pass reads and nothing stores. The statline
        # shape is standard content, fixed for every weapon there is.
        ignored=("unpriced", "statline_type"),
    ),
    "Wargear": Fields(
        identity=("qualifier",),
        updatable=("price", "trade_point_price", "is_exclusive", "category"),
        ignored=("unpriced",),
    ),
    "WeaponAccessory": Fields(
        identity=("qualifier",),
        updatable=("price", "trade_point_price", "is_exclusive", "category"),
        ignored=("unpriced",),
    ),
    "WeaponProfile": Fields(
        identity=("weapon",),
        updatable=(
            "price",
            "trade_point_price",
            "is_exclusive",
            "position",
            "stats",
            "traits",
        ),
        # A profile has no qualifier of its own — its weapon tells
        # it apart from the other weapon of the same name.
        ignored=("unpriced", "qualifier"),
    ),
    "Profile": Fields(
        identity=("qualifier",),
        updatable=(
            "price",
            "category",
            "gang_type",
            "built_ins",
            "stats",
            "skill_grid",
        ),
        # A fighter's type decides the shape of its statline, so
        # changing it would leave every stored value belonging to a
        # shape the fighter no longer has. That is an authoring
        # decision, not something a re-upload makes on the way past.
        ignored=("profile_type",),
    ),
    "DefaultAssignmentSet": Fields(updatable=("members",)),
    "CollectionEntry": Fields(
        identity=("collection", "item"),
        updatable=("price_override",),
        ignored=("position",),
    ),
    "Restriction": Fields(identity=("entry", "allows")),
    "Modifier": Fields(identity=("attach_to", "places", "targets", "offers")),
}

#: Kinds a re-upload never rewrites, and why. A kind with nothing
#: updatable must say so here: "there is nothing to change" is a claim
#: worth making out loud, and the alternative is an empty list nobody
#: can tell from an oversight.
NEVER_UPDATED = {
    "Category": "a category is its name and the heading above it, and both are its identity",
    "Trait": "a trait is a name and an annotation, and both are its identity",
    "Rule": "a rule is a name and an annotation, and both are its identity",
    "GangType": "the sheets know a gang by name and say nothing else about it",
    "Subtype": "the sheets know a subtype by name and say nothing else about it",
    "Skill": "the sheets know a skill by name and say nothing else about it",
    "Collection": "equipment-list uploads preserve existing content and ordering",
    "Restriction": "a restriction is the pairing itself — the entry, and who it is offered to",
    "Modifier": "a modifier is its pairing — the carrier, who it reaches, and what it does",
}

#: How each updatable field is compared and written. A **scalar** is
#: its own value; a **reference** is another planned row, compared by
#: asking whether the stored key points at the row this plan names; a
#: **set** is a collection of members, each kind of set with its own
#: rule about what happens to members the sheet no longer names.
FIELD_SHAPES = {
    "price": "scalar",
    "trade_point_price": "scalar",
    "is_exclusive": "scalar",
    "slots": "scalar",
    "position": "scalar",
    "price_override": "scalar",
    "category": "reference",
    "gang_type": "reference",
    "built_ins": "reference",
    "stats": "set",
    "traits": "set",
    "members": "set",
    "skill_grid": "set",
}


def find_existing(planned, pack, resolve):
    """Find the library record matching a planned record, or return None.

    Planning and performing share this identity lookup. resolve maps referenced
    plan keys to library objects, including the parent weapon or collection.
    """
    from n26.library.models import (
        Category,
        CollectionEntry,
        DefaultAssignmentSet,
        GangType,
        Modifier,
        Profile,
        Rule,
        Skill,
        Subtype,
        Trait,
        Wargear,
        Weapon,
        WeaponAccessory,
        WeaponProfile,
    )
    from n26.library.models.collection import Collection

    kind = planned.kind
    scope = {"pack": pack}

    by_name = {
        "GangType": GangType,
        "Subtype": Subtype,
        "Skill": Skill,
        "Collection": Collection,
        "DefaultAssignmentSet": DefaultAssignmentSet,
        "Modifier": Modifier,
    }
    if kind in by_name:
        return by_name[kind].objects.filter(name__iexact=planned.name, **scope).first()

    # Two catalogue rows may print one name, and the qualifier is the
    # only thing telling them apart.
    qualified = {
        "Weapon": Weapon,
        "Wargear": Wargear,
        "WeaponAccessory": WeaponAccessory,
        "Profile": Profile,
    }
    if kind in qualified:
        return (
            qualified[kind]
            .objects.filter(
                name__iexact=planned.name,
                qualifier__iexact=planned.fields.get("qualifier", ""),
                **scope,
            )
            .first()
        )

    annotated = {"Trait": Trait, "Rule": Rule}
    if kind in annotated:
        return (
            annotated[kind]
            .objects.filter(
                name__iexact=planned.name,
                annotation__iexact=planned.fields["annotation"],
                **scope,
            )
            .first()
        )

    if kind == "Category":
        return Category.objects.filter(
            section__name__iexact=planned.fields["section"],
            name__iexact=planned.name,
            **scope,
        ).first()

    if kind == "WeaponProfile":
        weapon = resolve(planned.fields["weapon"])
        if weapon is None:
            return None
        return WeaponProfile.objects.filter(
            weapon=weapon, name__iexact=planned.name
        ).first()

    if kind == "CollectionEntry":
        collection = resolve(planned.fields["collection"])
        item = resolve(planned.fields["item"])
        if collection is None or item is None:
            return None
        return CollectionEntry.objects.filter(
            collection=collection, **{CollectionEntry.field_for(item): item}
        ).first()

    if kind == "Restriction":
        # A restriction is not a row of its own: it is a link stored on
        # the collection entry. The entry stands for it, so whether the
        # pack already holds it is asked and answered like everything
        # else.
        entry = resolve(planned.fields["entry"])
        allows = resolve(planned.fields["allows"])
        if entry is None or allows is None:
            return None
        return entry if _already_allows(entry, allows) else None

    raise LookupError(f"nothing says what counts as the same {kind}")


def _already_allows(entry, allows):
    """Does this entry already name that fighter among the few this
    list offers the item to? Asked of the entry's own lists, which are
    the same three an item carries, so it reads either."""
    from n26.library.models import Profile, ProfileType, Subtype

    arms = {
        ProfileType: "usable_by_profile_types",
        Subtype: "usable_by_subtypes",
        Profile: "usable_by_profiles",
    }
    for model, arm in arms.items():
        if isinstance(allows, model):
            return getattr(entry, arm).filter(pk=allows.pk).exists()
    return False


def _settle(plan):
    """Match planned records and calculate their actions and changed fields.

    Process dependencies first so references can be compared by primary key.
    Existing equipment-list entries keep their positions; new entries append.
    """
    found = {}
    next_positions = {}

    def resolve(key):
        if key == XP_MEMBER:
            from n26.library.models import Counter

            return Counter.objects.filter(name__iexact=XP_COUNTER).first()
        return found.get(key)

    for planned in _in_perform_order(plan):
        row = find_existing(planned, plan.pack, resolve)
        found[planned.key] = row
        if planned.kind == "CollectionEntry":
            if row is not None:
                planned.fields["position"] = row.position
            else:
                collection_key = planned.fields["collection"]
                if collection_key not in next_positions:
                    collection = resolve(collection_key)
                    last = (
                        collection.entries.aggregate(last=Max("position"))["last"]
                        if collection is not None
                        else None
                    )
                    next_positions[collection_key] = 0 if last is None else last + 1
                planned.fields["position"] = next_positions[collection_key]
                next_positions[collection_key] += 1
        if planned.source.sheet == RESOLUTION:
            # A lookup, not a claim: nothing here to write or compare.
            plan.settle(planned, "resolved", existing=_pk(row))
        elif row is None:
            plan.settle(planned, "create")
        else:
            changes = _differences(plan, planned, row, resolve)
            plan.settle(
                planned,
                "update" if changes else "unchanged",
                changes=changes,
                existing=_pk(row),
            )

    _note_retained_entries(plan, found)
    _note_restrictions_the_sheet_no_longer_names(plan, found)


def _note_retained_entries(plan, found):
    """Report omitted entries in each uploaded list without retracting them."""
    from n26.library.models.collection import ENTRY_ASSIGNABLE_FIELDS, CollectionEntry

    matched = {}
    for planned in plan.planned:
        if planned.kind == "CollectionEntry" and planned.existing:
            matched.setdefault(planned.fields["collection"], set()).add(
                planned.existing
            )

    collections = {
        found[planned.key].pk: planned
        for planned in plan.planned
        if planned.kind == "Collection"
        and "entries" in planned.fields
        and found.get(planned.key) is not None
    }
    retained = {}
    entries = CollectionEntry.objects.filter(
        collection_id__in=collections
    ).select_related(*ENTRY_ASSIGNABLE_FIELDS, "weapon_profile__weapon")
    for entry in entries:
        planned = collections[entry.collection_id]
        if str(entry.pk) not in matched.get(planned.key, ()):
            retained.setdefault(planned.key, []).append(str(entry.assignable))
    for planned in collections.values():
        names = retained.get(planned.key)
        if not names:
            continue
        plan.problem(
            planned.source,
            f"{planned.name} keeps entries omitted from this upload: "
            f"{', '.join(sorted(names))}. Remove entries on the collection page.",
            severity="note",
        )


def _note_restrictions_the_sheet_no_longer_names(plan, found):
    """Report existing use restrictions omitted from the upload.

    Restrictions remain on the collection entry until an author removes them.
    """
    wanted, where = {}, {}
    for planned in plan.planned:
        if planned.kind == "CollectionEntry":
            wanted.setdefault(planned.key, set())
            where.setdefault(planned.key, planned.source)
        elif planned.kind == "Restriction":
            allows = found.get(planned.fields["allows"])
            if allows is not None:
                wanted.setdefault(planned.fields["entry"], set()).add(
                    (type(allows).__name__, allows.pk)
                )

    from django.db.models import prefetch_related_objects

    # The lists are the long sheets, so the entries' own lists are read
    # in one batch rather than once per line.
    entries = {
        key: found[key] for key in wanted if found.get(key) is not None
    }  # absent: founded by this upload, and carries only what this says
    prefetch_related_objects(list(entries.values()), "usable_by_profiles")
    for entry_key, entry in entries.items():
        named = wanted[entry_key]
        stored = list(entry.usable_by_profiles.all())
        unnamed = [row for row in stored if (type(row).__name__, row.pk) not in named]
        if not unnamed:
            continue
        said = ", ".join(sorted(str(row) for row in unnamed))
        plan.problem(
            where[entry_key],
            f"{entry} keeps existing use restrictions for {said}. These restrictions "
            f"are absent from the upload. Remove them on the collection page if needed.",
            severity="note",
        )


def _pk(row):
    return None if row is None else str(row.pk)


def _in_perform_order(plan):
    """The planned rows, in the order perform will take them. A kind
    with no place in that order would be planned and then skipped
    without a word, so it is refused here instead."""
    order = {kind: index for index, kind in enumerate(PERFORM_ORDER)}
    unplaceable = sorted({row.kind for row in plan.planned} - set(order))
    if unplaceable:
        raise LookupError(
            f"{', '.join(unplaceable)} can be planned but has no place in "
            f"PERFORM_ORDER, so it would be planned and never performed"
        )
    return sorted(plan.planned, key=lambda row: order[row.kind])


def _differences(plan, planned, row, resolve):
    """Compare sheet-owned fields against a matched library record.

    Return printable field differences for the preview. perform() updates only
    these fields.
    """
    changes = {}
    for name in SHEET_FIELDS[planned.kind].updatable:
        if name not in planned.fields:
            continue
        shape = FIELD_SHAPES[name]
        if shape == "scalar":
            difference = _scalar_difference(planned, row, name)
        elif shape == "reference":
            difference = _reference_difference(plan, planned, row, name, resolve)
        else:
            difference = _set_difference(plan, planned, row, name, resolve)
        if difference:
            changes[name] = difference
    return changes


def _scalar_difference(planned, row, name):
    wanted = planned.fields[name]
    stored = getattr(row, name)
    if wanted == stored:
        return None
    return {"from": stored, "to": wanted}


def _reference_difference(plan, planned, row, name, resolve):
    """Compare a planned reference with the stored foreign-key target.

    An unresolved nonempty plan key differs from an empty foreign key.
    """
    key = planned.fields[name]
    if not key:
        return None
    wanted = resolve(key)
    if wanted is not None and wanted.pk == getattr(row, f"{name}_id"):
        return None
    return {
        "from": _said(getattr(row, name)),
        "to": _planned_said(plan, key),
    }


def _said(row):
    """A row, as a person would name it in a report."""
    return None if row is None else str(row)


def _planned_said(plan, key):
    """Format a planned record's label for comparison with an existing record."""
    if not key:
        return None
    if key == XP_MEMBER:
        return XP_COUNTER
    planned = plan.get(key)
    if planned is None:
        return key
    if planned.kind == "Category":
        return f"{planned.fields['section']}: {planned.name}"
    annotation = planned.fields.get("annotation")
    if annotation:
        return f"{planned.name} ({annotation})"
    return planned.name or key


def _set_difference(plan, planned, row, name, resolve):
    """Compare set-valued fields using each field's replacement rules.

    Traits and skill grids replace stored members. Built-in kit retains omitted
    members. Blank statline cells preserve stored values.
    """
    if name == "stats":
        return _stat_difference(planned, row)
    if name == "traits":
        return _members_difference(
            wanted=[
                (_planned_said(plan, key), resolve(key))
                for key in planned.fields["traits"]
            ],
            stored=list(row.traits.all()),
            retract=True,
        )
    if name == "members":
        return _built_ins_difference(plan, planned, row, resolve)
    return _grid_difference(plan, planned, row, resolve)


def _members_difference(wanted, stored, retract):
    """Compare labelled planned members with stored members.

    Include removals only when retract is True.
    """
    wanted_pks = {row.pk for _, row in wanted if row is not None}
    stored_pks = {member.pk for member in stored}
    added = [said for said, row in wanted if row is None or row.pk not in stored_pks]
    removed = [str(member) for member in stored if member.pk not in wanted_pks]
    difference = {}
    if added:
        difference["added"] = sorted(added)
    if removed and retract:
        difference["removed"] = sorted(removed)
    return difference


def _stat_difference(planned, row):
    """Compare supplied characteristic values, preserving cells left blank."""
    columns = MODEL_COLUMNS if planned.kind == "Profile" else WEAPON_COLUMNS
    stored = _stored_stats(row)
    from n26.library.models import Stat

    changed = []
    for column, full in columns:
        wanted = planned.fields["stats"].get(column)
        if wanted is None:
            continue
        was = stored.get(Stat.derive_field_name(full))
        if was == wanted:
            continue
        changed.append(f"{column} {was if was is not None else '—'} → {wanted}")
    return {"changed": changed} if changed else {}


def _stored_stats(row):
    """The row's statline, as ``{field name: the value as stored}``.
    The raw value, not the formatted one: a sheet cell and a stored
    cell must be comparable as the same kind of thing."""
    statline = getattr(row, "statline", None)
    if statline is None:
        return {}
    return {stat.field_name: stat.value for stat in statline.ordered_stats()}


#: Built-in members a sheet **replaces** rather than adds to, by the
#: kind the plan names. A fighter buys from one equipment list, so
#: naming one is naming *the* one: a fighter moved from the Escher list
#: to the Cawdor list must not be left holding both, which would widen
#: what they can buy without anybody saying so. Everything else in the
#: set is kit, and kit is only ever added to — that is where the pieces
#: no sheet defines are put by hand.
REPLACED_BUILT_INS = ("Collection",)


def _kind_of(key):
    """The kind a plan key names — the word before its first colon."""
    return key.split(":", 1)[0]


def _superseded_built_ins(members, stored, named):
    """Built-in members this upload takes off rather than keeps.

    Only the kinds a set holds at most one of, and only where the sheet
    names one of that kind: a column saying nothing takes nothing off.
    That reading matters, because the other one strips every fighter the
    first time a sheet without the column is uploaded — and a blank cell
    is the sheet declining to say, here as everywhere else.

    ``members`` is the planned membership, ``stored`` the rows the set
    holds, and ``named`` the assignables among them the sheet still
    names.
    """
    claimed = {_kind_of(member["item"]) for member in members} & set(REPLACED_BUILT_INS)
    return [
        member
        for member in stored
        if member.assignable.pk not in named
        and type(member.assignable).__name__ in claimed
    ]


def _built_ins_difference(plan, planned, row, resolve):
    """Compare built-in members, amounts and equipment-list access.

    Preserve omitted kit and ignore archived members. A newly named equipment
    list replaces the previous list.
    """
    stored = {
        member.assignable.pk: member for member in row.members.filter(archived=False)
    }
    added, changed, named = [], [], set()
    for member in planned.fields["members"]:
        said = _planned_said(plan, member["item"])
        thing = resolve(member["item"])
        held = None if thing is None else stored.get(thing.pk)
        if held is None:
            added.append(said)
            continue
        named.add(thing.pk)
        amount = member.get("amount", 0)
        if held.amount != amount:
            changed.append(f"{said} {held.amount} → {amount}")

    superseded = _superseded_built_ins(
        planned.fields["members"], stored.values(), named
    )
    # Preserve omitted built-ins, including equipment added through authoring.
    dropped = [
        member
        for pk, member in stored.items()
        if pk not in named and member not in superseded
    ]
    if dropped:
        plan.problem(
            planned.source,
            f"{planned.name} keeps built-in content omitted from this upload: "
            f"{', '.join(sorted(str(member.assignable) for member in dropped))}. "
            f"Remove built-ins on the profile's authoring page if needed.",
            severity="note",
        )

    difference = {}
    if added:
        difference["added"] = sorted(added)
    if changed:
        difference["changed"] = sorted(changed)
    if superseded:
        difference["removed"] = sorted(str(member.assignable) for member in superseded)
    return difference


def _grid_difference(plan, planned, row, resolve):
    """Compare skill-set placements and their Primary or Secondary tiers."""
    # The one reference that points the other way: a placement hangs on
    # the fighter, so the fighter settles first and the placements are
    # not yet in hand. They can be looked up regardless — a placement's
    # identity is its name and depends on nothing being settled.
    wanted = [
        (_planned_said(plan, key), find_existing(plan.get(key), plan.pack, resolve))
        for key in planned.fields["skill_grid"]
    ]
    return _members_difference(wanted, _placements(row), retract=True)


def _placements(carrier):
    """The placement modifiers on this carrier that place a skill set.

    Only those: a carrier may hold modifiers doing anything at all, and
    an import's statement about the grid is not a statement about the
    rest of them. Only the *skill* sets, too — a placement of a category
    from another heading is other content that happens to share the
    tiers, not part of any sheet's grid.
    """
    return [
        modifier
        for modifier in carrier.modifiers.filter(
            places_category__category__isnull=False
        ).select_related(
            "places_category__section__collection",
            "places_category__category__section",
        )
        if modifier.places_category.section.collection.name == SKILLS_COLLECTION
        and modifier.places_category.category.section.name == SKILLS_SECTION
    ]


# --- Performing ----------------------------------------------------------------


@dataclass
class IngestResult:
    """What perform did: rows created, rows changed, rows found already
    there and left alone."""

    created: dict = field(default_factory=dict)  # key -> model instance
    updated: dict = field(default_factory=dict)
    existing: dict = field(default_factory=dict)
    #: Whether what was created was held back from players.
    staged: bool = False

    def counts(self):
        tally = TallyCounter(key.split(":", 1)[0] for key in self.created)
        return dict(tally)


#: Creation order — PROTECT relations point up this list. It is also
#: the order rows settle in, so a row is always measured against
#: something already looked for.
#:
#: A collection comes before the built-in sets because a fighter's
#: equipment list is one of its built-ins: read the other way round, the
#: set would be asked to hold a list nothing had made yet.
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
    "WeaponAccessory",
    "Collection",
    "DefaultAssignmentSet",
    "Profile",
    "CollectionEntry",
    "Restriction",
    "Modifier",
]


#: Kinds a plan may name but must never make. What the sheets say about
#: these is only ever which one they mean.
NEVER_CREATED = {}


def _refuse_what_cannot_be_done(plan):
    """Validate every planned kind before executing any writes.

    Each action requires a perform order and a registered creator or updater.
    """
    shortfalls = []
    for planned in plan.planned:
        if planned.action == UNSETTLED:
            shortfalls.append(f"{planned.key} was never settled")
        if planned.kind not in PERFORM_ORDER:
            shortfalls.append(f"{planned.kind} has no place in the performing order")
        if planned.action == "create" and planned.kind not in CREATORS:
            shortfalls.append(
                f"{planned.kind} is planned to be made and nothing makes it"
                + (
                    f" — {NEVER_CREATED[planned.kind]}"
                    if planned.kind in NEVER_CREATED
                    else ""
                )
            )
        if planned.action == "update" and planned.kind not in UPDATERS:
            shortfalls.append(
                f"{planned.kind} is planned to change and nothing changes it"
            )
    if shortfalls:
        raise LookupError(
            "this plan cannot be carried out in full, so none of it was: "
            + "; ".join(sorted(set(shortfalls)))
        )


class StaleAppendPlan(LookupError):
    """An equipment list changed after its append positions were planned."""


def _lock_append_collections(plan):
    """Lock append targets, validate positions and return their pinned references."""
    from n26.library.models import Collection, CollectionEntry

    appends = {}
    parents = {}
    for planned in plan.planned:
        if planned.kind == "CollectionEntry" and planned.action == "create":
            collection = plan.get(planned.fields["collection"])
            if collection.existing:
                appends.setdefault(collection.existing, []).append(planned)
                parents[collection.existing] = collection
    if not appends:
        return {}

    # Acquire all parent locks in the same order and hold them through insertion.
    collections = list(
        Collection.objects.select_for_update().filter(pk__in=appends).order_by("pk")
    )
    if {str(collection.pk) for collection in collections} != set(appends):
        raise StaleAppendPlan(
            "An equipment list changed during import. Nothing was imported. "
            "Review the updated preview and try again."
        )
    last_positions = {
        str(row["collection_id"]): row["last"]
        for row in CollectionEntry.objects.filter(collection_id__in=appends)
        .values("collection_id")
        .annotate(last=Max("position"))
    }
    for collection in collections:
        key = str(collection.pk)
        last = last_positions.get(key)
        start = 0 if last is None else last + 1
        planned_positions = [row.fields["position"] for row in appends[key]]
        if (
            collection.name.casefold() != parents[key].name.casefold()
            or collection.pack_id != plan.pack.pk
            or planned_positions != list(range(start, start + len(appends[key])))
        ):
            raise StaleAppendPlan(
                f"{collection} changed during import. Nothing was imported. "
                "Review the updated preview and try again."
            )
    return {parents[str(collection.pk)].key: collection for collection in collections}


def perform(plan, *, staged=False):
    """Apply a valid plan in dependency order within one transaction.

    Create and update the records and fields specified by the plan. Reject plans
    with blocking problems, unsupported kinds or missing standard content.

    With staged=True, stage newly created content. Updates to existing content
    apply immediately.
    """
    if not plan.ok:
        errors = [p for p in plan.problems if p.severity == "error"]
        raise ValueError(
            f"plan has {len(errors)} unresolved problem(s); first: {errors[0].message}"
        )
    _refuse_what_cannot_be_done(plan)
    result = IngestResult(staged=staged)
    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
        result.existing.update(_lock_append_collections(plan))
        performer = _Performer(plan, result)
        for kind in PERFORM_ORDER:
            for planned in plan.planned:
                if planned.kind == kind:
                    performer.perform_one(planned)
        if staged:
            _stage_created(result)
    return result


def _stage_created(result):
    """Hold back the rows the import made, one write per kind.

    Only kinds a player is offered are staged (``stageable_kinds``): a
    category or a modifier the import made is reached through a fighter
    or a weapon that is, and staging it as well would only lengthen the
    list of things to put live. A planned row whose creator hands back a
    row of some other kind — a restriction returns the item it narrows,
    which may have been live for years — is left alone: what was made is
    what is staged.
    """
    from n26.library import authoring
    from n26.library.staged import stageable_kinds

    stageable = stageable_kinds()
    authoring.stage_all(
        [
            row
            for key, row in result.created.items()
            if type(row) in stageable and type(row).__name__ == key.split(":", 1)[0]
        ]
    )


class _Performer:
    def __init__(self, plan, result):
        self.plan = plan
        self.result = result
        self.shared = {"pack": plan.pack}

    def _standard(self, model, what, **filters):
        """A standard-content row, by its fixed name. Missing means the
        seed hasn't been created — say which, don't plant it here."""
        row = model.objects.filter(**filters).first()
        if row is None:
            raise LookupError(
                f"{what} is not there — create standard content first "
                f"(the foundations page; library/standard_content.py)"
            )
        return row

    def resolve(self, key):
        """A planned key → the model row it now names."""
        if key in self.result.created:
            return self.result.created[key]
        if key in self.result.existing:
            return self.result.existing[key]
        if key == XP_MEMBER:
            from n26.library.models import Counter

            return self._standard(
                Counter, f"the {XP_COUNTER} counter", name__iexact=XP_COUNTER
            )
        planned = self.plan.get(key) or _missing(key)
        row = find_existing(planned, self.plan.pack, self.resolve)
        if row is None:
            raise LookupError(f"nothing performs or holds {key}")
        self.result.existing[key] = row
        return row

    #: Nothing in a plan ever points at a row of these kinds, so a row
    #: already in the pack needs no looking up: there is no later line
    #: waiting to be told where it landed. A collection entry counts,
    #: though a restriction names the entry it narrows: ``resolve``
    #: looks a key up on demand, so the entry is found when a
    #: restriction is written onto it and not before — an upload of
    #: lists that gained none reads no entry at all.
    UNREFERENCED = {"CollectionEntry", "Restriction", "Modifier"}

    def perform_one(self, planned):
        if planned.action in ("unchanged", "resolved"):
            if planned.kind not in self.UNREFERENCED:
                self.resolve(planned.key)
            return
        if planned.action == "update":
            updater = getattr(self, UPDATERS[planned.kind])
            self.result.updated[planned.key] = updater(planned)
            return
        creator = getattr(self, CREATORS[planned.kind])
        self.result.created[planned.key] = creator(planned)

    def _the_row_the_preview_described(self, planned):
        """Return the record matched during planning, or reject a stale match.

        Stop the import if the original record was removed or the identity lookup
        now matches a different record.
        """
        row = find_existing(planned, self.plan.pack, self.resolve)
        if row is None or str(row.pk) != planned.existing:
            raise LookupError(
                f"{planned.key} is no longer the row the preview described — "
                f"the pack changed in between; preview again"
            )
        return row

    # -- changing what is already there -------------------------------------
    #
    # An updater writes exactly the fields the settling pass named as
    # different, and takes the values from the plan. Nothing decides
    # again here what has changed: the preview said, and this does that.

    def _revise_columns(self, planned, row):
        """The plain columns this change names — its own values, and the
        rows its keys point at — written through one verb."""
        from n26.library import authoring

        values = {}
        for name in planned.changes:
            shape = FIELD_SHAPES[name]
            if shape == "scalar":
                values[name] = planned.fields[name]
            elif shape == "reference":
                values[name] = self.resolve(planned.fields[name])
        if values:
            authoring.revise(row, **values)
        return row

    def _update_weapon(self, planned):
        return self._revise_columns(
            planned, self._the_row_the_preview_described(planned)
        )

    _update_wargear = _update_weapon
    _update_weaponaccessory = _update_weapon
    _update_collectionentry = _update_weapon

    def _update_weaponprofile(self, planned):
        from n26.library import authoring

        row = self._the_row_the_preview_described(planned)
        self._revise_columns(planned, row)
        if "traits" in planned.changes:
            authoring.set_traits(
                row, [self.resolve(key) for key in planned.fields["traits"]]
            )
        if "stats" in planned.changes:
            self._set_statline(row, planned.fields["stats"], WEAPON_COLUMNS)
        return row

    def _update_profile(self, planned):
        row = self._the_row_the_preview_described(planned)
        self._revise_columns(planned, row)
        if "stats" in planned.changes:
            self._set_statline(row, planned.fields["stats"], MODEL_COLUMNS)
        if "skill_grid" in planned.changes:
            self._retract_placements(row, planned)
        return row

    def _retract_placements(self, profile, planned):
        """Take off the skill-set placements this fighter's sheet no
        longer names.

        The placements it *does* name are made afterwards, as modifiers
        in their own right, so what is left here is only the leaving.
        A modifier can hang on more than one carrier, so it is detached
        first and only deleted where nothing else holds it — and then by
        its scope and effect rows, which are what the modifier cascades
        away with.
        """
        from n26.library import authoring

        wanted = {
            row.pk
            for row in (
                find_existing(self.plan.get(key), self.plan.pack, self.resolve)
                for key in planned.fields["skill_grid"]
            )
            if row is not None
        }
        for modifier in _placements(profile):
            if modifier.pk in wanted:
                continue
            authoring.detach_modifier(profile, modifier)
            if not _anything_carries(modifier):
                modifier.places_category.delete()
                if modifier.scope is not None:
                    modifier.scope.delete()

    def _update_defaultassignmentset(self, planned):
        """Add built-in members and update their amounts.

        Archive superseded equipment-list members and preserve omitted equipment.
        """
        from n26.library import authoring

        row = self._the_row_the_preview_described(planned)
        live = row.members.filter(archived=False)
        held = {member.assignable.pk: member for member in live}
        # After the last position ever placed, archived members
        # included, so a fresh add never ties with a surviving member.
        last = row.members.aggregate(last=Max("position"))["last"]
        position = 0 if last is None else last + 1
        named = set()
        for member in planned.fields["members"]:
            thing = self.resolve(member["item"])
            named.add(thing.pk)
            extras = {name: v for name, v in member.items() if name != "item"}
            already = held.get(thing.pk)
            if already is None:
                authoring.add_default_member(
                    row, thing, position=position, **extras, **self.shared
                )
                position += 1
            elif already.amount != extras.get("amount", 0):
                authoring.revise(already, amount=extras.get("amount", 0))
        for member in _superseded_built_ins(
            planned.fields["members"], held.values(), named
        ):
            authoring.remove_default_member(member)
        return row

    # -- one creator per kind, each a thin call into library.authoring ------

    def _create_category(self, planned):
        from n26.library import authoring
        from n26.library.models import Section

        # The heading is founded here rather than left to the verb so it
        # can carry the order it reads in; one already in the pack keeps
        # the order it has.
        #
        # Matched case-insensitively, the way every other lookup in this
        # performer matches: a pack is unique on a section's lowercased
        # name, so an exact-match lookup asked for "Gang list" where the
        # pack holds "Gang List" misses it, inserts, and trips the
        # constraint — taking the whole import down. Two sheets spelling
        # one heading differently is all it takes to get there.
        section = Section.objects.filter(
            name__iexact=planned.fields["section"], **self.shared
        ).first()
        if section is None:
            section = Section.objects.create(
                name=planned.fields["section"],
                position=planned.fields["section_position"],
                **self.shared,
            )
        return authoring.create_category(section, planned.name, **self.shared)

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

    def _create_weaponaccessory(self, planned):
        from n26.library import authoring

        # What an accessory fits — a category of weapon, or the
        # asterisked ones — is not in the sheets, so it arrives fitting
        # anything and is narrowed by hand. Importing it as unrestricted
        # is the honest reading of a column that does not exist.
        return authoring.create_weapon_accessory(
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

        home = planned.fields["category"]
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
            # No home means the hire list has no section to put it in: it
            # gathers at the end, under no heading.
            category=self.resolve(home) if home else None,
            **self.shared,
        )
        if planned.fields["built_ins"]:
            profile.built_ins = self.resolve(planned.fields["built_ins"])
            profile.save()
        self._set_statline(profile, planned.fields["stats"], MODEL_COLUMNS)
        return profile

    def _create_collection(self, planned):
        from n26.library import authoring

        collection = authoring.create_collection(planned.name, **self.shared)
        if planned.fields.get("default_section"):
            authoring.section_of(
                collection, planned.fields["default_section"], 0, is_default=True
            )
        return collection

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

        # The verb routes by the kind of thing allowed, so the plan
        # need only name it. Written onto the entry — this list's own
        # offer — never onto the item every list shares.
        return authoring.restrict_use(
            self.resolve(planned.fields["entry"]),
            self.resolve(planned.fields["allows"]),
        )

    def _modifier_scope(self, planned):
        """Who a planned modifier reaches. No ``targets`` means the
        carrier's own model — a fighter's grid placement; a row that
        names who it reaches narrows to a subtype or an entry."""
        from n26.library import authoring

        targets = planned.fields.get("targets")
        if not targets:
            return authoring.targets_model()
        # A row that names who it reaches is carried by something the
        # gang holds, so the reach is every model the condition names —
        # unless the row says the bearer alone.
        if "subtype" in targets:
            return authoring.targets_every_model(
                authoring.has_subtypes(self.resolve(targets["subtype"]))
            )
        named = authoring.is_profile(self.resolve(targets["profile"]))
        if targets.get("bearer_only", False):
            return authoring.targets_model(named)
        return authoring.targets_every_model(named)

    def _modifier_effect(self, planned):
        """What a planned modifier does: places a set in a tier, or puts
        a question on the bearer's card."""
        from django.apps import apps

        from n26.library import authoring
        from n26.library.models.collection import CollectionSection

        offers = planned.fields.get("offers")
        if offers:
            collection = self.resolve(offers["collection"])
            section = collection.default_section()
            if section is None:
                raise LookupError(
                    f"{collection.name!r} has no default section for the "
                    f"offer to draw from"
                )
            return authoring.ef_offers_choice(
                apps.get_model("library", offers["kind"]),
                from_section=section,
                label=offers["label"],
                will_be_assigned_to=offers["will_be_assigned_to"],
                mode=offers.get("mode", "select"),
            )
        places = planned.fields["places"]
        return authoring.ef_places(
            self.resolve(places["category"]),
            self._standard(
                CollectionSection,
                f"the {places['section']!r} tier of {SKILLS_COLLECTION!r}",
                collection__name__iexact=SKILLS_COLLECTION,
                name__iexact=places["section"],
            ),
        )

    def _create_modifier(self, planned):
        from n26.library import authoring

        return authoring.modifier(
            planned.name,
            scope=self._modifier_scope(planned),
            effect=self._modifier_effect(planned),
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


def _anything_carries(modifier):
    """Is any assignable still holding this modifier?

    Modifiers are shareable, so taking one off a fighter is not the
    same as being finished with it. The kinds are read off the app
    rather than listed, so a new one is covered without anyone
    remembering to say so.
    """
    from django.apps import apps

    return any(
        model.objects.filter(modifiers=modifier).exists()
        for model in apps.get_app_config("library").get_models()
        if hasattr(model, "modifiers")
    )


#: How each kind is made, and how a kind the sheets can change is
#: changed. Two tables that can be read against a plan before anything
#: is written, which is the point of their being tables: a kind planned
#: to be made or changed with nothing to do it is refused up front
#: (:func:`_refuse_what_cannot_be_done`) rather than failing part way
#: through an import, on the one row that needed it.
CREATORS = {
    "Category": "_create_category",
    "Trait": "_create_trait",
    "GangType": "_create_gangtype",
    "Subtype": "_create_subtype",
    "Skill": "_create_skill",
    "Rule": "_create_rule",
    "Weapon": "_create_weapon",
    "WeaponProfile": "_create_weaponprofile",
    "Wargear": "_create_wargear",
    "WeaponAccessory": "_create_weaponaccessory",
    "DefaultAssignmentSet": "_create_defaultassignmentset",
    "Profile": "_create_profile",
    "Collection": "_create_collection",
    "CollectionEntry": "_create_collectionentry",
    "Restriction": "_create_restriction",
    "Modifier": "_create_modifier",
}

UPDATERS = {
    "Weapon": "_update_weapon",
    "Wargear": "_update_wargear",
    "WeaponAccessory": "_update_weaponaccessory",
    "WeaponProfile": "_update_weaponprofile",
    "Profile": "_update_profile",
    "DefaultAssignmentSet": "_update_defaultassignmentset",
    "CollectionEntry": "_update_collectionentry",
}


# --- Clearing ------------------------------------------------------------------


def _imported(pack=None):
    """Return imported content querysets in deletion order.

    Preserve standard content and delete dependent records before their targets.
    """
    from django.apps import apps

    from n26.library.models import (
        Category,
        DefaultAssignmentSet,
        GangType,
        HasSubtypes,
        Modifier,
        Profile,
        Rule,
        Skill,
        Subtype,
        Trait,
        Wargear,
        Weapon,
        WeaponAccessory,
        WeaponProfile,
    )
    from n26.library.models.collection import Collection, CollectionEntry
    from n26.library.standard_content import (
        FIGHTER_SUBTYPES,
        GANG_TYPES,
        INHERENT_SET,
        INHERENT_SKILLS,
        SKILL_SETS,
        SKILLS_COLLECTION,
        SKILLS_SECTION,
        TRADING_POST_COLLECTION,
        VEHICLE_SUBTYPES,
        fighter_advancement_modifiers,
        lasting_effect_status_modifiers,
        visit_contribution_counter,
    )

    scope = {} if pack is None else {"pack": pack}
    standard_skills = [s for skills in SKILL_SETS.values() for s in skills]
    standard_skills += INHERENT_SKILLS

    profiles = Profile.objects.filter(**scope)

    # Every modifier goes except standard content's own: the rest either
    # came from an import or name content that is about to go, and a
    # modifier pointing at a deleted trait is what stops the whole clear.
    # A seeded one is recognised the way its own seed recognises it — by
    # what it does, never by its name — so rewording one does not put it
    # back in the way of a clear.
    # The founding-budget modifiers are not among the spared, though they
    # are standard content too: each names the fighter entries it reaches,
    # and a scope left naming nothing narrows nothing — every model in the
    # gang would read a Leader's allowance. So they go with the entries
    # and are made again the next time the seed runs.
    spared = Q(pk__in=())
    visit_counter = visit_contribution_counter()
    if visit_counter is not None:
        spared = Q(contributes_to_counter__counter=visit_counter)
    # The lasting-effect tables' own status effects are standard content
    # too, and they hold nothing an import made.
    spared |= lasting_effect_status_modifiers()
    # Advancement results carry the modifiers that make their stat and skill
    # rewards work.  They are foundations too, and deleting their typed scope
    # or effect rows makes the seed incomplete even though its table survives.
    spared |= fighter_advancement_modifiers()
    # Conditions on retained modifiers must keep the subtype identities they name.
    kept_subtypes = HasSubtypes.objects.filter(
        scope__modifier__in=Modifier.objects.filter(spared),
        subtypes__isnull=False,
    ).values("subtypes")
    doomed = list(
        Modifier.objects.filter(**scope).exclude(spared).values_list("pk", flat=True)
    )

    # A modifier holds its scope and effect, and those rows are what
    # hold the trait — deleting the modifier alone leaves them behind
    # still protecting it. So the scope and effect rows are the ones
    # swept, and the modifier cascades away with them. Read off the
    # model rather than listed, so a new scope or effect kind is
    # covered without anyone remembering to say so.
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    parts = []
    for field_name in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        model = Modifier._meta.get_field(field_name).related_model
        parts.append(
            (
                "modifiers",
                model.objects.filter(
                    Q(modifier__pk__in=doomed) | Q(modifier__isnull=True)
                ),
            )
        )

    section = apps.get_model("library", "Section")
    return parts + [
        ("collection entries", CollectionEntry.objects.filter(**scope)),
        ("fighter profiles", profiles),
        # The built-in sets go before the collections they name: a
        # fighter's equipment list is one of its built-ins, and the
        # membership row protects the list.
        ("built-in sets", DefaultAssignmentSet.objects.filter(**scope)),
        (
            "collections",
            Collection.objects.filter(**scope).exclude(
                name__in=[SKILLS_COLLECTION, TRADING_POST_COLLECTION]
            ),
        ),
        ("weapon profiles", WeaponProfile.objects.filter(**scope)),
        ("weapons", Weapon.objects.filter(**scope)),
        ("wargear", Wargear.objects.filter(**scope)),
        ("weapon accessories", WeaponAccessory.objects.filter(**scope)),
        ("special rules", Rule.objects.filter(**scope)),
        ("weapon traits", Trait.objects.filter(**scope)),
        ("skills", Skill.objects.filter(**scope).exclude(name__in=standard_skills)),
        (
            "subtypes",
            Subtype.objects.filter(**scope).exclude(
                Q(name__in=FIGHTER_SUBTYPES + VEHICLE_SUBTYPES)
                | Q(pk__in=kept_subtypes)
            ),
        ),
        (
            "gang types",
            GangType.objects.filter(**scope).exclude(
                Q(name__in=GANG_TYPES) | Q(excluded_built_in_actions__isnull=False)
            ),
        ),
        (
            "categories",
            Category.objects.filter(**scope).exclude(
                section__name=SKILLS_SECTION,
                name__in=[*SKILL_SETS, INHERENT_SET],
            ),
        ),
        # A heading with nothing under it is not content. The skills one
        # is standard and keeps its categories, so it never empties.
        (
            "sections",
            section.objects.filter(**scope)
            .exclude(name=SKILLS_SECTION)
            .filter(categories__isnull=True),
        ),
    ]


def count_imported(pack=None):
    """Count imported content by type, omitting empty types.

    Combine scope and effect counts under the shared modifiers label.
    """
    found = TallyCounter()
    for label, rows in _imported(pack):
        found[label] += rows.count()
    return {label: count for label, count in found.items() if count}


def clear_imported(pack=None):
    """Delete imported content in one transaction and preserve standard content.

    Raise ProtectedError if referenced content prevents deletion. Roll back every
    deletion on failure. Return the number deleted for each content type.
    """
    from n26.write_pause import write_guard

    gone = TallyCounter()
    with transaction.atomic(), write_guard():
        for label, rows in _imported(pack):
            found = rows.count()
            if found:
                rows.delete()
                gone[label] += found
    return dict(gone)


def _missing(key):
    raise LookupError(f"plan never mentions {key}")
