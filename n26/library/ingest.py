"""Ingest — pre-ingest spreadsheets in, library rows out, preview between.

The pipeline (design/ingest.md §8) is three stages, and the middle one
is the interface:

* **read**: CSV text → rows (plain dicts, one per sheet line).
* **plan**: rows → :class:`IngestPlan` — a list of :class:`Planned`
  objects saying exactly which library row each sheet line becomes,
  plus :class:`Problem` rows for everything that doesn't resolve.
  Planning reads the database but never writes. It ends in one
  **settling** pass (:func:`_settle`) that says, for every planned row,
  whether the pack already holds it and what the sheets now say
  differently: ``create``, ``update``, ``unchanged``, or ``resolved``
  for a row that is not a sheet line at all but a lookup other lines
  point at. ``plan.preview()`` derives the upload-preview payload:
  counts by kind, the differences field by field, worked examples
  (sheet row → planned objects), and the problem list — plain data,
  JSON-able, per the structures-before-renderers convention
  (CLAUDE.md).
* **perform**: plan → rows, through the ``n26.library.authoring`` verbs,
  in dependency order, in one transaction. Perform never invents
  anything the plan didn't say: the preview *is* the contract, which
  now covers changes as well as creations — an update writes exactly
  the fields the preview named as changing, onto the row the preview
  measured.

An uploaded file is **held** between those stages
(``n26.library.models.staging``). A browser will not let a server fill a
file input back in, so a page that previewed an upload and then asked
for the file again was asking the author to promise it was the same one;
holding it makes the preview and the import two readings of one thing.
What is not held is the plan: it is made again on the visit that shows
it and again on the post that imports, because the contract is about the
library as it stands.

Three standing rules are load-bearing here:

* **Resolve, never create, across sheets.** An equipment-list line or a
  built-in names a weapon; if no weapon of that name is planned or
  already in the pack, that is a Problem, not a new weapon. Complex
  weapons are hand-authored first and resolved by name (§7b).
* **Built-ins are free.** Items named in a profile's default assignment
  attach at price 0 and never take a price from an equipment list,
  even on an exact name match (§5a — the Techmite's power fist is not
  the one on the Ironhead list). The same set is how a fighter reaches
  an equipment list at all: access is a built-in like any other, and
  its being free is what keeps buying rights out of a fighter's
  rating.
* **Ingest stands on standard content.** The statline shapes, profile
  types, XP counter and skill tiers a plan resolves against come from
  ``n26.library.standard_content`` — created from the foundations page, never
  re-declared here. Perform says which seed is missing rather than
  quietly planting its own.
* **Nothing is lost quietly.** Four tables say what can be done with a
  planned kind — :data:`PERFORM_ORDER`, :data:`SHEET_FIELDS`,
  :data:`CREATORS`, :data:`UPDATERS` — and perform reads the whole plan
  against them before writing anything, refusing by name if some of it
  has nowhere to go. Forget one and the rows would otherwise be passed
  over in silence while the upload reported success.

**The sheets, and how they join.** Four of them, each with one job:

* **Equipment** — the catalogue. One row per thing a gang can buy,
  typed by an ``Assignable`` column (a weapon, wargear, or one of a
  weapon's priced firing lines), carrying its category and its price.
  The only place a reference price lives.
* **Weapon profiles** — the statlines, and nothing else. A blank
  ``Profile`` is the weapon's own firing line; a named one is an ammo
  type or a mode.
* **Equipment lists** — a named collection per ``Title``, one entry per
  line, at this list's price where it differs from the catalogue's.
* **All Profiles** — the fighters, each with the heading and category
  it is hired under, and an ``Equipment List`` column naming the list
  it buys from.

They join on an ``ID`` column printing ``Name (Profile) (Category ←
Section)``, which :class:`ItemId` parses. Resolution goes through that,
never through the name alone: eight weapons share a printed name across
categories, so a name is not an identity. Where two catalogue rows do
share one, both are kept and told apart by the author-facing
``qualifier`` — renaming would put a word on a player's card that
the books do not print.

**Nothing here builds a Trading Post.** Membership there is *having a
trade point price* — the post is two sweeps created as standard content —
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

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q

from n26.library.models.profile import TYPE_NAMES
from n26.library.sheets import SHEET_NAMES
from n26.library.standard_content import (
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


#: A row nothing has settled yet. Planning writes it; :func:`_settle`
#: replaces every one of them. A plan still carrying one is a planner
#: that added a row after the settling pass, which would be a row
#: performed without anyone having asked whether the pack holds it.
UNSETTLED = "pending"

#: The sheet name a lookup carries. A row planned under it is not a
#: sheet line at all — it is a row read out of the pack so other rows
#: can point at it — so nothing about it is a claim the upload makes,
#: and nothing about it is ever written.
RESOLUTION = "resolution"

#: The plan key for a fighter's opening XP. The counter itself is
#: standard content, so it is never planned — it is named as a member
#: of a built-ins set and resolved by its fixed name.
XP_MEMBER = "Counter:xp"


@dataclass(frozen=True)
class Planned:
    """One library row the plan intends.

    ``key`` names it within the plan (``"Weapon:autogun"``); other
    planned objects refer to it by that key in their ``fields``, so the
    whole plan is plain, printable data.

    ``action`` is settled once, at the end of planning:

    * ``create`` — the pack does not hold it.
    * ``update`` — it does, and the sheet says something different.
      ``changes`` names each difference, printably.
    * ``unchanged`` — it does, and the sheet says the same.
    * ``resolved`` — not a sheet row at all: a row looked up so other
      rows can point at it.

    ``existing`` is the pk of the row it matched, so performing writes
    onto the row the preview described rather than onto whatever the
    same lookup finds a moment later.
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
    """One thing the plan cannot do.

    The line between the two severities is what proceeding would *do*.
    An **error** would write something wrong, or names a state that is
    never legitimate — two fighters claiming one identity, a priced row
    whose price would silently vanish. A **note** means the upload
    writes less than the sheet asked for and says so: a list line naming
    an item nothing defines, a statline for nothing in the catalogue, a
    restriction the model has no arm for. Nothing incorrect is written
    either way; the difference is whether waiting is the right answer.

    Most shortfalls are notes, because refusing a thousand good rows
    over three the sheets are not ready for helps nobody — and the
    report is where they are dealt with.
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
    """Everything the upload would do, as data. The preview derives from
    this; perform executes exactly this."""

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
        """One row the plan intends. What becomes of it — made, changed,
        left alone, or merely looked up — is not decided here: planning
        says what the sheets mean, and :func:`_settle` says once, at the
        end, what the pack already holds."""
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
        """Fix a row's action, and what makes it one — the difference the
        sheet asks for, and the row in the pack it will be written onto."""
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
    """A sheet row that finds a column however its heading was typed.

    Headings are typed by hand into a spreadsheet, so "Equipment list",
    "Equipment List" and a stray trailing space are one column to
    everyone except a dict. Matching them exactly means a heading that
    differs by a capital reads as *absent*, and the whole feature behind
    it goes missing with nothing said — the worst way for a sheet to be
    wrong, because the upload succeeds and the preview looks right.

    Only lookup folds. The row still holds what the file said, so
    anything reporting a heading back to an author quotes their own.
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
    """An uploaded file that will not be kept, and the reason in words.

    Refusing here rather than at planning time is the difference between an
    author being told "that is not a CSV" beside the file picker and being
    shown a preview of nothing.
    """


def store_sheet(owner, sheet, upload):
    """Keep an uploaded file as this author's copy of ``sheet``.

    Whatever they held for that sheet before is replaced: a corrected export
    supersedes a wrong one, and two files claiming to be the Equipment sheet
    would leave the planner to guess.

    The replacement writes over one row rather than removing one and making
    another, so an author whose upload fails halfway still holds the file
    they had. The superseded bytes go only once the new ones are stored,
    for the same reason.

    The file is read once here, both to count its lines and to find out now
    whether it can be read at all.
    """
    from n26.library.models.staging import MAX_SHEET_BYTES, UploadedSheet

    if sheet not in SHEET_NAMES:
        raise SheetRefused(f"{sheet!r} is not one of the sheets.")
    if upload.size > MAX_SHEET_BYTES:
        raise SheetRefused(
            f"That file is {upload.size // 1024}KB, and a sheet may be at most "
            f"{MAX_SHEET_BYTES // 1024}KB. It is probably not a CSV export."
        )
    raw = upload.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as refused:
        raise SheetRefused(
            "That file is not text this can read. Export it as CSV (UTF-8) "
            "and upload it again."
        ) from refused
    rows = read_csv(text)
    if not rows:
        raise SheetRefused(
            "That file has a heading row and nothing under it, or is not a CSV at all."
        )

    with transaction.atomic():
        # Locked, so an author who submits the same form twice replaces one
        # row twice rather than racing themselves into the constraint that
        # holds them to one sheet of each kind.
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
        held.file.storage.delete(superseded)
    return held


def held_sheets(owner):
    """What this author has uploaded, keyed by the planner's name for it."""
    from n26.library.models.staging import UploadedSheet

    return {
        held.sheet: held
        for held in UploadedSheet.objects.filter(owner=owner)
        if held.sheet in SHEET_NAMES
    }


def rows_of(held):
    """Held uploads → the rows :func:`plan_ingest` takes."""
    return {name: read_csv(upload.text()) for name, upload in held.items()}


def discard_sheets(owner, sheets=None):
    """Remove held uploads, bytes and all; return how many went.

    One at a time, because the stored file goes with the row and a queryset
    delete would leave the bytes behind.
    """
    from n26.library.models.staging import UploadedSheet

    held = UploadedSheet.objects.filter(owner=owner)
    if sheets is not None:
        held = held.filter(sheet__in=sheets)
    gone = 0
    for upload in held:
        upload.delete()
        gone += 1
    return gone


# --- Planning ----------------------------------------------------------------


def plan_ingest(
    equipment=(),
    weapon_profiles=(),
    equipment_lists=(),
    profiles=(),
    archetypes=(),
    pack=None,
):
    """Rows from up to five sheets → one :class:`IngestPlan`.

    The order is forced, and it is circular if done naively: statlines
    hang on catalogue rows, lists resolve against the catalogue, a
    fighter's built-in kit names things the catalogue defines, and a
    list's restrictions name fighters. So:

    1. the **equipment** sheet — the catalogue: what exists, and its price;
    2. the **weapon profiles** sheet — the statlines, onto those rows;
    3. the **equipment lists** — collections and entries, restrictions deferred;
    4. the **All Profiles** sheet — the fighters;
    5. those deferred restrictions, which needed the fighters;
    6. the **archetypes** — whose rows reach fighters by subtype or by name.

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
    _plan_archetypes(plan, archetypes)
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
    """The equipment sheet: the catalogue, and the only place a price lives.

    One row per thing a gang can buy, typed by its ``Assignable``
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
    trade point price* — the post is two sweeps created as standard content
    — so setting the field is the whole job.

    Returns the prices found for named weapon profiles, keyed by ID: the
    profiles themselves are defined by their statlines, and this sheet
    only says what they are priced at.
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
#: the sheet only spells out the other one.
GANG_LIST_SECTION = "Gang List"
PROFILE_SECTIONS = {GANG_LIST_SECTION: 0, "Supplementary Fighters": 1}


def _plan_home(plan, row, name, source):
    """A fighter's home category, from the sheet's ``Category`` and
    ``Section``. Returns its key, or None where the sheet names none."""
    section = _clean(row.get("Section") or "") or GANG_LIST_SECTION
    category = _clean(row.get("Category") or "")
    if not category:
        plan.problem(
            source,
            f"{name!r} names no Category — it arrives ungrouped, under no "
            f"heading in the hire list",
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
    """The All Profiles sheet. Rating **is** the price (§5a); the grid
    columns become placement modifiers on the profile itself, and the
    ``Category`` and ``Section`` columns are the fighter's home — where
    the hire list groups it."""
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
            # Every entry is hired off a gang list, and a gang type with
            # no name draws as an empty card on the create-gang page,
            # landing before every real one — nothing sorts before nothing.
            plan.problem(
                source,
                f"{name!r} names no Gang — every entry is hired off a gang "
                f"list, and the sheet has not said which",
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

        # A fighter reaches an equipment list by holding it among its
        # built-ins, which is why the column lands here rather than
        # anywhere else: access is a thing the fighter comes with.
        buys_at = _clean(row.get(EQUIPMENT_LIST_COLUMN) or "")
        if buys_at:
            listed = _resolve_equipment_list(plan, buys_at)
            if listed is None:
                plan.problem(
                    source,
                    f"{name!r} has {buys_at!r} in the {EQUIPMENT_LIST_COLUMN} "
                    f"column, and no equipment list of that title is defined "
                    f"or in the pack — imported without it, so the fighter "
                    f"buys from nothing (lists resolve, never create)",
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
                f"profile {name!r} is also another gang's — this one is "
                f"qualified {qualifier!r}; authors see the qualifier, "
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
    """The fighter's Primary and Secondary skill-set columns, as
    placement modifiers. Returns their keys, in the order the sheet
    reads, which is the fighter's whole statement about its grid."""
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
    """The equipment list a fighter's ``Equipment List`` cell names.

    A title is put together with the kind exactly as the equipment-lists
    sheet's own rows are, so a fighter and the list it buys from cannot
    come to mean different collections. A cell spelling the whole name
    out is then taken as written, which makes both readings of the
    column land on one row; each attempt is an exact match on a folded
    name, so neither is a guess.

    Resolve, never create: an equipment list is defined on its own
    sheet, and a title carried by none of them is a miss.
    """
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
            # The list's contents are its own field, filled in as
            # the rest of the sheet is read: a line leaving the sheet
            # is a statement about the list, and no single entry can
            # see it.
            plan.add(
                "Collection",
                name,
                {"entries": listed.setdefault(collection_key, [])},
                source,
                key=collection_key,
            )

        ident = ItemId.of(row)
        if not ident.name:
            plan.problem(source, "row names nothing")
            continue

        item_key = _resolve_by_id(plan, ident)
        if item_key is None:
            plan.problem(
                source,
                f"{title} lists {ident.printed!r}, which the equipment "
                f"sheet does not define and the pack does not hold — "
                f"this list arrives without it. Author the item first "
                f"if it is one of the hand-built ones",
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

    A listing that carries a ``Profile`` is offering one firing line of a
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
    qualifier that tells two same-named rows apart, and for a firing
    line the weapon it hangs on, which is how an entry knows whether it
    is already listed. A key left off here surfaces much later as a
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
    """The deferred restrictions pass: fighter profiles exist by now.

    Three shapes turn up. "<Fighter> only" narrows an item to a profile
    and "<X> specialist only" to a specialisation — both are arms of
    ``UsableBy``, so both become real restrictions. A gang-wide cap
    ("Max one per gang") is not a restriction on *use* at all, so it is
    said and carried past rather than bent into the wrong mechanism.

    The regex only proposes a name; what decides is whether that name
    resolves to something real. Nothing is ever restricted on a guess.
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
        allows = _profile_ref(plan, named, gang) or _specialisation_ref(plan, named)
        if allows:
            plan.add(
                "Restriction",
                f"{plan.get(item_key).name} ({restriction})",
                {"item": item_key, "allows": allows},
                source,
                key=f"Restriction:{entry_key}",
            )
        elif re.search(r"\bspecialist$", named, flags=re.IGNORECASE):
            plan.problem(
                source,
                f"restriction {restriction!r} names a specialisation the "
                f"pack does not hold — author it and upload again; "
                f"imported without it",
                severity="note",
            )
        else:
            plan.problem(
                source,
                f"restriction {restriction!r} names a fighter no sheet "
                f"defines and the pack does not hold — imported without it",
                severity="note",
            )


def _specialisation_ref(plan, named):
    """The specialisation a restriction names: "Gunner specialist" is the
    Gunner specialisation, the field a Specialist chose.

    Resolve, never create — which specialisations exist is authored
    content, and a restriction string is not allowed to invent one.
    """
    from n26.library.models import Specialisation

    bare = re.sub(r"\s*\bspecialist$", "", named, flags=re.IGNORECASE).strip()
    if not bare or _norm(bare) == _norm(named):
        return None  # only the "<X> specialist" shape names one

    key = f"Specialisation:{_norm(bare)}"
    if plan.get(key):
        return key
    if existing := _exists(plan, Specialisation, name__iexact=bare):
        return plan.add(
            "Specialisation",
            existing.name,
            {},
            Source(RESOLUTION, 0),
            key=key,
        ).key
    return None


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


# --- The archetypes sheet -----------------------------------------------------

#: The sheet's fixed columns. Every other heading is a skill set, and
#: its cell places that set in a tier — a new set is a new column,
#: never new code.
ARCHETYPE_FIXED_COLUMNS = ("Archetype", "Gang Type", "Profile", "Subtype", "Own pick")

OWN_PICK_COLUMN = "Own pick"

#: What a skill cell may say. Blank and "-" say nothing.
_TIER_WORDS = {"primary": "Primary", "secondary": "Secondary"}


def _own_pick(row):
    """The ``Own pick`` cell, strictly read: True, False, or None for a
    value that reads as neither."""
    cell = (row.get(OWN_PICK_COLUMN) or "").strip().casefold()
    if cell in ("", "-", "n", "no"):
        return False
    if cell in ("y", "yes"):
        return True
    return None


def _subtype_ref(plan, name):
    """The subtype an archetype row names — planned, or already in the
    pack; None otherwise. An archetype row never mints a subtype."""
    from n26.library.models import Subtype

    key = f"Subtype:{_norm(name)}"
    if plan.get(key):
        return key
    existing = _exists(plan, Subtype, name__iexact=_clean(name))
    if existing is None:
        return None
    plan.add("Subtype", existing.name, {}, Source(RESOLUTION, 0), key=key)
    return key


def _archetype_profile_ref(plan, cell, gang):
    """The profile an archetype row names. The sheet may print the entry
    with its gang in front — "Outcast Champion" for the Outcast gang's
    "Champion" — so the printed name is tried first and the stripped one
    after."""
    found = _profile_ref(plan, cell, gang)
    if found is not None:
        return found
    bare = _clean(cell)
    prefix = f"{_clean(gang)} ".casefold()
    if bare.casefold().startswith(prefix):
        return _profile_ref(plan, bare[len(prefix) :].strip(), gang)
    return None


def _wearers(plan, gang_name, subtype_key):
    """The gang's profiles that come wearing this subtype — planned in
    this upload, or already in the pack. These are the entries that
    carry the gang-held archetype question."""
    from n26.library.models import Profile

    gang_key = f"GangType:{_norm(gang_name)}"
    found = []
    for planned in plan.planned:
        if planned.kind != "Profile":
            continue
        if planned.fields.get("gang_type") != gang_key:
            continue
        built = plan.get(planned.fields.get("built_ins") or "")
        if built and any(
            member["item"] == subtype_key for member in built.fields["members"]
        ):
            found.append(planned.key)
    subtype_name = plan.get(subtype_key).name
    for existing in Profile.objects.filter(
        pack=plan.pack,
        gang_type__name__iexact=_clean(gang_name),
        built_ins__members__archived=False,
        built_ins__members__subtype__name__iexact=subtype_name,
    ):
        key = _profile_ref(plan, existing.name, gang_name)
        if key is not None and key not in found:
            found.append(key)
    return found


def _plan_archetypes(plan, rows):
    """The Archetypes sheet: one carrier per named archetype, and the
    skill table its rows radiate.

    Each row reaches one rank of one gang — via a **subtype**, where
    every entry wearing it reads the gang's pick (the Leader variants),
    or via a named **profile**, where the rank's subtype is shared
    vocabulary another gang's entry might wear. ``Own pick`` marks the
    profile rows whose table wakes only for the model's own choice — so
    those entries are offered their own question, while subtype rows put
    the gang-held question on every entry of the gang that wears the
    subtype. The pick list is a small collection per gang, so each offer
    narrows to exactly its own archetypes.
    """
    grids = {}  # archetype key -> the modifier keys its rows state
    stated = {}  # (archetype, target, set) -> (tier, line) — one claim each
    by_gang = {}  # gang name -> what its rows gather
    unworn = set()  # (gang, subtype) pairs already noted as asked by nobody

    for line, row in enumerate(rows, start=1):
        source = Source("archetypes", line)
        plan.remember_row(source, row)
        name = _clean(row.get("Archetype", ""))
        if not name:
            plan.problem(source, "row names no archetype")
            continue
        gang_name = _clean(row.get("Gang Type", ""))
        if not gang_name:
            plan.problem(source, f"{name!r} names no gang type")
            continue

        profile_cell = _clean(row.get("Profile", ""))
        subtype_cell = _clean(row.get("Subtype", ""))
        if bool(profile_cell) == bool(subtype_cell):
            said = (
                "both a Profile and a Subtype"
                if profile_cell
                else "neither a Profile nor a Subtype"
            )
            plan.problem(source, f"{name!r} names {said} — a row reaches exactly one")
            continue
        own_pick = _own_pick(row)
        if own_pick is None:
            plan.problem(
                source,
                f"{name!r} has {row.get(OWN_PICK_COLUMN)!r} in the "
                f"{OWN_PICK_COLUMN} column — it reads Y, or is left blank",
            )
            continue
        if own_pick and subtype_cell:
            plan.problem(
                source,
                f"{name!r}: {OWN_PICK_COLUMN} marks a named entry choosing "
                f"for itself — a Subtype row reads the gang's pick",
            )
            continue

        gathered = by_gang.setdefault(
            gang_name, {"archetypes": [], "askers": {}, "source": source}
        )
        archetype_key = f"Archetype:{_norm(name)}"
        if not plan.get(archetype_key):
            plan.add(
                "Archetype",
                name,
                {"qualifier": "", "skill_grid": grids.setdefault(archetype_key, [])},
                source,
                key=archetype_key,
            )
        if archetype_key not in gathered["archetypes"]:
            gathered["archetypes"].append(archetype_key)

        if subtype_cell:
            subtype_key = _subtype_ref(plan, subtype_cell)
            if subtype_key is None:
                plan.problem(
                    source,
                    f"{name!r} reaches {subtype_cell!r} models, and no sheet "
                    f"defines that subtype and the pack does not hold it — "
                    f"the row is skipped (archetypes resolve, never create)",
                    severity="note",
                )
                continue
            targets = {"subtype": subtype_key}
            target_label = f"{plan.get(subtype_key).name} models"
            wearers = _wearers(plan, gang_name, subtype_key)
            for wearer in wearers:
                gathered["askers"].setdefault(wearer, "gang")
            if not wearers and (gang_name, subtype_key) not in unworn:
                unworn.add((gang_name, subtype_key))
                plan.problem(
                    source,
                    f"no {gang_name} fighter comes with the "
                    f"{plan.get(subtype_key).name!r} subtype — the archetype "
                    f"question is offered by nobody until one does",
                    severity="note",
                )
        else:
            profile_key = _archetype_profile_ref(plan, profile_cell, gang_name)
            if profile_key is None:
                plan.problem(
                    source,
                    f"{name!r} reaches {profile_cell!r}, and no sheet defines "
                    f"that fighter and the pack does not hold it — the row is "
                    f"skipped (archetypes resolve, never create)",
                    severity="note",
                )
                continue
            targets = {"profile": profile_key, "bearer_only": own_pick}
            target_label = plan.get(profile_key).name + (
                " (own pick)" if own_pick else ""
            )
            if own_pick:
                gathered["askers"][profile_key] = "bearer"

        target_norm = _norm(target_label)
        fixed = {_fold_column(column) for column in ARCHETYPE_FIXED_COLUMNS}
        for column in row:
            if not column or _fold_column(column) in fixed:
                continue
            cell = (row[column] or "").strip()
            if cell in ("", "-"):
                continue
            tier = _TIER_WORDS.get(cell.casefold())
            if tier is None:
                plan.problem(
                    source,
                    f"{name!r} has {cell!r} under {column!r} — a cell reads "
                    f"Primary, Secondary or '-'",
                )
                continue
            set_name = _clean(column)
            claim = (archetype_key, target_norm, _norm(set_name))
            already = stated.get(claim)
            if already is not None:
                tier_before, line_before = already
                if tier_before == tier:
                    plan.problem(
                        source,
                        f"{name!r} places {set_name} for {target_label} twice "
                        f"— the second is ignored",
                        severity="note",
                    )
                else:
                    plan.problem(
                        source,
                        f"{name!r} places {set_name} at {tier} for "
                        f"{target_label}, and line {line_before} already "
                        f"placed it at {tier_before} — one table cannot say "
                        f"both",
                    )
                continue
            stated[claim] = (tier, line)
            category_key = _plan_category(plan, SKILLS_SECTION, set_name, source)
            modifier_key = (
                f"Modifier:{archetype_key}:{target_norm}"
                f":{_norm(set_name)}:{tier.lower()}"
            )
            plan.add(
                "Modifier",
                f"{name}: {target_label} — {set_name} is {tier}",
                {
                    "attach_to": archetype_key,
                    "targets": targets,
                    "places": {"category": category_key, "section": tier},
                },
                source,
                key=modifier_key,
            )
            grids[archetype_key].append(modifier_key)

    for gang_name, gathered in by_gang.items():
        source = gathered["source"]
        collection_name = f"{gang_name} Archetypes"
        collection_key = f"Collection:{_norm(collection_name)}"
        entries = []
        plan.add(
            "Collection",
            collection_name,
            {"entries": entries, "default_section": "Archetypes"},
            source,
            key=collection_key,
        )
        for position, archetype_key in enumerate(gathered["archetypes"]):
            item = plan.get(archetype_key)
            entry_key = f"CollectionEntry:{_norm(collection_name)}:{archetype_key}"
            plan.add(
                "CollectionEntry",
                f"{item.name} in {collection_name}",
                {
                    "collection": collection_key,
                    "item": archetype_key,
                    "position": position,
                    "price_override": None,
                },
                source,
                key=entry_key,
            )
            entries.append(entry_key)
        for profile_key, host in gathered["askers"].items():
            asker = plan.get(profile_key)
            what = "the gang's Archetype" if host == "gang" else "an Archetype"
            plan.add(
                "Modifier",
                f"{asker.name}: chooses {what}",
                {
                    "attach_to": profile_key,
                    "offers": {
                        "kind": "Archetype",
                        "collection": collection_key,
                        "label": "archetype",
                        "will_be_assigned_to": host,
                    },
                },
                source,
                key=f"Modifier:offer:{profile_key}",
            )


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
    "Specialisation": Fields(),
    "Archetype": Fields(identity=("qualifier",), updatable=("skill_grid",)),
    "Collection": Fields(
        updatable=("entries",),
        # The section where unplaced entries land is founded with the
        # collection; one already in the pack keeps the schema it has.
        ignored=("default_section",),
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
        # A firing line has no qualifier of its own — its weapon tells
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
        updatable=("position", "price_override"),
    ),
    "Restriction": Fields(identity=("item", "allows")),
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
    "Specialisation": "which specialisations exist is authored, never imported",
    "Restriction": "a restriction is the pairing itself — the item, and who may use it",
    "Modifier": "a modifier is its pairing — the carrier, who it reaches, and what it does",
}

#: Fields settled in a second pass, because comparing them needs rows
#: the first pass has not looked for yet. A collection settles before
#: its entries — an entry's identity is its collection and the thing
#: listed — so what its entries matched is not known until after.
SETTLED_LATE = {"entries"}

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
    "entries": "set",
    "stats": "set",
    "traits": "set",
    "members": "set",
    "skill_grid": "set",
}


def find_existing(planned, pack, resolve):
    """The row in the pack a planned row names, or ``None``.

    One statement of what counts as the same row, because two things
    ask it: settling, to measure a difference against the row that will
    be written onto, and performing, to point other rows at it. Kept
    apart, the two drift — and the drift is silent, a difference
    measured against one row and written onto another.

    ``resolve`` answers a plan key with the row it names, or ``None``
    where nothing holds it yet. Some identities need it: a firing
    line's is the weapon it hangs on, an entry's is its collection and
    the thing listed. Matching those by name instead would take
    whichever row came first, and one printed name can belong to two
    weapons.
    """
    from n26.library.models import (
        Archetype,
        Category,
        CollectionEntry,
        DefaultAssignmentSet,
        GangType,
        Modifier,
        Profile,
        Rule,
        Skill,
        Specialisation,
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
        "Specialisation": Specialisation,
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
        "Archetype": Archetype,
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
        # the item. The item stands for it, so whether the pack already
        # holds it is asked and answered like everything else.
        item = resolve(planned.fields["item"])
        allows = resolve(planned.fields["allows"])
        if item is None or allows is None:
            return None
        return item if _already_allows(item, allows) else None

    raise LookupError(f"nothing says what counts as the same {kind}")


def _already_allows(item, allows):
    """Does this item already name that fighter or specialisation among
    the few who may use it?"""
    from n26.library.models import Profile, ProfileType, Specialisation, Subtype

    arms = {
        ProfileType: "usable_by_profile_types",
        Subtype: "usable_by_subtypes",
        Profile: "usable_by_profiles",
        Specialisation: "usable_by_specialisations",
    }
    for model, arm in arms.items():
        if isinstance(allows, model):
            return getattr(item, arm).filter(pk=allows.pk).exists()
    return False


def _settle(plan):
    """Decide every planned row's action, once, in one place.

    Planning says what the sheets mean; this says what the pack already
    holds, and the two are worth keeping apart. All the identity
    knowledge and all the comparison knowledge sit here and read
    together, and a row is compared against the row it will be written
    onto rather than against whatever a second, separately written
    lookup happens to find.

    The order is the performing order, so every row a row names is
    settled before it. That is what makes a foreign key comparable at
    all: "does the stored key point at the row this plan names?" cannot
    be asked until the named row has been looked for.
    """
    found = {}

    def resolve(key):
        if key == XP_MEMBER:
            from n26.library.models import Counter

            return Counter.objects.filter(name__iexact=XP_COUNTER).first()
        return found.get(key)

    for planned in _in_perform_order(plan):
        row = find_existing(planned, plan.pack, resolve)
        found[planned.key] = row
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

    _settle_contents(plan, found)
    _note_restrictions_the_sheet_no_longer_names(plan, found)


def _settle_contents(plan, found):
    """A second, smaller pass: what a list this upload mentions holds
    that the upload no longer names.

    It cannot be part of the first pass. A collection is settled before
    its entries, because an entry's identity is its collection and the
    thing listed — so when the collection is settled, what its entries
    matched has not been looked for yet, and that is exactly what this
    needs.

    Scoped to the lists the upload mentions, and that scoping is the
    whole care here: "delete the entries nothing planned" would empty
    every other gang's list on an upload of one gang's.
    """
    matched = {}
    for planned in plan.planned:
        if planned.kind == "CollectionEntry" and planned.existing:
            matched.setdefault(planned.fields["collection"], set()).add(
                planned.existing
            )

    for planned in plan.planned:
        if planned.kind != "Collection" or "entries" not in planned.fields:
            continue
        collection = found.get(planned.key)
        if collection is None:
            continue  # founded by this upload: it holds only what this says
        gone = [
            entry
            for entry in collection.entries.all()
            if str(entry.pk) not in matched.get(planned.key, ())
        ]
        if not gone:
            continue
        plan.settle(
            planned,
            "update",
            changes={
                **planned.changes,
                "entries": {"removed": sorted(str(entry.assignable) for entry in gone)},
            },
            existing=planned.existing,
        )


def _note_restrictions_the_sheet_no_longer_names(plan, found):
    """Say which fighters an item is still restricted to that no line of
    this upload names — and retract none of them.

    A restriction is stored on the *item*, so it is shared by every list
    that carries that item. One list dropping "<Fighter> only" cannot be
    read as retracting it, because another list may be the reason it is
    there. Add-only, and the note is how an author finds the ones to
    take off by hand.
    """
    from n26.library.models.assignable import UsableBy

    wanted, where = {}, {}
    for planned in plan.planned:
        if planned.kind == "CollectionEntry":
            wanted.setdefault(planned.fields["item"], set())
            where.setdefault(planned.fields["item"], planned.source)
        elif planned.kind == "Restriction":
            allows = found.get(planned.fields["allows"])
            if allows is not None:
                wanted.setdefault(planned.fields["item"], set()).add(
                    (type(allows).__name__, allows.pk)
                )

    for item_key, named in wanted.items():
        item = found.get(item_key)
        # Not everything listable can be narrowed: a firing line is
        # bought through the weapon, which is where the restriction is.
        if not isinstance(item, UsableBy):
            continue
        stored = [
            *item.usable_by_profiles.all(),
            *item.usable_by_specialisations.all(),
        ]
        unnamed = [row for row in stored if (type(row).__name__, row.pk) not in named]
        if not unnamed:
            continue
        said = ", ".join(sorted(str(row) for row in unnamed))
        plan.problem(
            where[item_key],
            f"{item} is restricted to {said} in the pack, which no line of "
            f"this upload names — nothing was retracted, because the "
            f"restriction is on the item and other lists may be its reason",
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
    """What the sheet says that the pack's row does not, field by field.

    Printable values only — a reference renders as the name of the
    thing referred to, a set as what joined and what left. This is what
    the preview shows, and the fields it names are exactly the fields
    perform writes; perform takes the values themselves from
    ``planned.fields``, so that the two cannot describe different
    writes.
    """
    changes = {}
    for name in SHEET_FIELDS[planned.kind].updatable:
        if name not in planned.fields or name in SETTLED_LATE:
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
    """A foreign key, compared without ever asking a stored row what
    the plan would have called it.

    The question is only "does the stored key point at the row this
    plan names?", so it is asked in that direction: resolve the key,
    and compare. A key the upload is about to found resolves to
    nothing, and that is a difference rather than a match — it is about
    to point somewhere that does not exist yet.

    Naming nothing is not the same as naming nothing in particular: a
    blank cell is the sheet declining to say, exactly as a blank stat
    cell is, so what the row already points at stays.
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
    """A plan key, as the thing it names.

    Read alongside :func:`_said`, so the two sides of a difference are
    named the same way whether or not the pack holds them yet — which
    is the whole use of it, since half of what a change names is a row
    the upload has not made.
    """
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
    """A collection of members: what joins, what leaves, what shifts.

    Each set has its own answer to "what about a member the sheet no
    longer names", and the deciding question is whether the set is
    somewhere hand-authored content lives (3.6 of the design note).
    Traits and the skill grid are wholly the sheets'; a fighter's
    built-in kit is not, and a statline's blank cell is the sheet
    declining to say rather than saying nothing is there.
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
    """What joined the set and what left it.

    ``wanted`` pairs each member's printable name with the row in the
    pack it means, which is ``None`` for one this upload is about to
    make — and a member that does not exist yet is necessarily
    joining, which is why the name has to be carried alongside the row
    rather than read off it.

    ``retract`` says whether leaving is something this set does at all.
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
    """The sheet's stat cells against the stored ones.

    A blank cell is the sheet saying nothing about that characteristic,
    not saying it is empty — the planner drops blanks, and what is
    dropped is left exactly as the pack has it.
    """
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
    """A fighter's built-in kit: what the sheet adds, and never what it
    stops naming.

    This is where hand-authored content actually lives — the kit no
    sheet defines, added by hand precisely because an import could not
    bring it. Replacing the set would delete exactly that, every time.
    So the sheet may add, and what it no longer names is said instead.

    The fighter's equipment list is the exception, because it is not
    kit: there is one of it, and naming a new one is naming a
    replacement (:data:`REPLACED_BUILT_INS`).

    An archived member is off the set for this reading: the sheet
    naming its thing again measures as an addition, exactly what the
    performer will do.
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
    # What the sheet has stopped naming stays, and is said instead. An
    # author who meant to take it off has to, which is annoying and
    # honest; the alternative deletes the hand-added kit on every
    # re-upload and cannot be undone from the sheets.
    dropped = [
        member
        for pk, member in stored.items()
        if pk not in named and member not in superseded
    ]
    if dropped:
        plan.problem(
            planned.source,
            f"{planned.name} still comes with "
            f"{', '.join(sorted(str(member.assignable) for member in dropped))}, "
            f"which this sheet no longer names — kept, because built-in kit "
            f"no sheet defines is added by hand",
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
    """A fighter's skill grid: the sets it may take, and in which tier.

    Wholly the sheet's, and the tier is part of what is said — a set
    moving from Primary to Secondary is one placement leaving and
    another arriving. Left add-only, the fighter would end up with the
    set in both tiers, which is a wrong card rather than an untidy one.
    """
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
    from another heading (an archetype's powers) is other content that
    happens to share the tiers, not part of any sheet's grid.
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
    "Specialisation",
    "Rule",
    "Weapon",
    "WeaponProfile",
    "Wargear",
    "WeaponAccessory",
    "Archetype",
    "Collection",
    "DefaultAssignmentSet",
    "Profile",
    "CollectionEntry",
    "Restriction",
    "Modifier",
]


#: Kinds a plan may name but must never make. What the sheets say about
#: these is only ever which one they mean.
NEVER_CREATED = {
    "Specialisation": (
        "which specialisations exist is authored content, and a "
        "restriction string does not get to mint one"
    ),
}


def _refuse_what_cannot_be_done(plan):
    """Stop before writing anything if some of the plan has nowhere to
    go.

    Every kind must have a place in the performing order, a way of
    being made and a way of being changed — whichever of those the plan
    asks for. A missing one used to mean the row was passed over in
    silence, which is the worst outcome available: the upload reports
    success and part of it never happened.
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


def perform(plan):
    """Execute the plan through the authoring verbs, in one transaction.

    Refuses a plan with error problems: the preview said no. Returns an
    :class:`IngestResult` whose creations and changes match what the
    preview said — the preview is the contract, and a change writes
    exactly the fields the preview named as changing.

    Standard content must already exist (the foundations page): the
    statline shapes, profile types, XP counter and skill tiers are
    resolved by their standard names and a missing one is a loud
    LookupError, never quietly re-planted.
    """
    if not plan.ok:
        errors = [p for p in plan.problems if p.severity == "error"]
        raise ValueError(
            f"plan has {len(errors)} unresolved problem(s); first: {errors[0].message}"
        )
    _refuse_what_cannot_be_done(plan)
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
    #: waiting to be told where it landed.
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
        """The row a change is to be written onto — that row, not
        whatever the same lookup finds now.

        A preview and an import are two requests over the same files,
        and the pack can move between them. If what the preview
        measured is gone, or is no longer the row that lookup answers
        with, the whole import stops: the alternative is writing a
        difference onto a row nobody looked at.
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

    def _update_collection(self, planned):
        """A list, with the lines the sheet stopped carrying taken off.

        The equipment-lists sheet is the whole statement about a list,
        so a line that has gone from it has gone from the list. Only
        the lists this upload mentions are touched — the settling pass
        scoped that, and it is the difference between reading one gang's
        sheet and emptying every other gang's list.
        """
        row = self._the_row_the_preview_described(planned)
        if "entries" not in planned.changes:
            return row
        kept = {
            self.plan.get(key).existing
            for key in planned.fields["entries"]
            if self.plan.get(key).existing
        }
        for entry in row.entries.all():
            if str(entry.pk) not in kept:
                entry.delete()
        return row

    def _update_defaultassignmentset(self, planned):
        """A fighter's built-in kit, added to — and its equipment list
        put in place of whichever it held.

        Kit is never taken from: this is where the pieces no sheet
        defines are added by hand, precisely because an import cannot
        bring them, and replacing the set would delete exactly that on
        every re-upload. A fighter buys from one list, though, so a
        sheet naming a list is naming the only one there is — and the
        superseded one is archived rather than deleted, because every
        copy it materialised names it as its provenance. An archived
        member is off the set for this reading too: a sheet naming its
        thing again is adding it afresh.
        """
        from n26.library import authoring

        row = self._the_row_the_preview_described(planned)
        live = row.members.filter(archived=False)
        held = {member.assignable.pk: member for member in live}
        position = live.count()
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
            member.archive()
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

    def _create_archetype(self, planned):
        from n26.library import authoring

        return authoring.create_archetype(
            planned.name,
            qualifier=planned.fields.get("qualifier", ""),
            **self.shared,
        )

    def _update_archetype(self, planned):
        row = self._the_row_the_preview_described(planned)
        if "skill_grid" in planned.changes:
            self._retract_placements(row, planned)
        return row

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

        # The verb routes by the kind of thing allowed — a profile, a
        # specialisation — so the plan need only name it.
        return authoring.restrict_use(
            self.resolve(planned.fields["item"]),
            self.resolve(planned.fields["allows"]),
        )

    def _modifier_scope(self, planned):
        """Who a planned modifier reaches. No ``targets`` means the
        carrier's own model — a fighter's grid placement; an archetype
        row narrows to a subtype or names an entry outright."""
        from n26.library import authoring

        targets = planned.fields.get("targets")
        if not targets:
            return authoring.targets_model()
        # A sheet that names who it reaches is an archetype-shaped row: the
        # carrier is something the gang holds, so the reach is every model
        # the condition names — unless the row says the bearer alone.
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
    "Archetype": "_create_archetype",
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
    "Archetype": "_update_archetype",
    "DefaultAssignmentSet": "_update_defaultassignmentset",
    "CollectionEntry": "_update_collectionentry",
    "Collection": "_update_collection",
}


# --- Clearing ------------------------------------------------------------------


def _imported(pack=None):
    """What an import owns, as ``[(what it is, the rows)]`` in the order
    they must go — entries before collections, statlines with their
    owners, the taxonomy last.

    One definition, so counting and deleting cannot disagree: a
    confirmation screen that promised different numbers from the ones
    that went would be worse than no screen.

    What is *not* here is the point. Standard content's own rows are
    excluded by reading its lists rather than restating them, so the
    two cannot drift, and a clear always leaves the foundations whole.
    """
    from django.apps import apps

    from n26.library.models import (
        Archetype,
        Category,
        DefaultAssignmentSet,
        GangType,
        Modifier,
        Profile,
        Rule,
        Skill,
        Specialisation,
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
        SPECIALISATIONS,
        TRADING_POST_COLLECTION,
        VEHICLE_SUBTYPES,
    )

    scope = {} if pack is None else {"pack": pack}
    standard_skills = [s for skills in SKILL_SETS.values() for s in skills]
    standard_skills += INHERENT_SKILLS

    profiles = Profile.objects.filter(**scope)

    # Modifiers go, apart from the ones standard content wired: the
    # eight specialisation grants, which are as fixed as the skills
    # they hand out. Everything else either came from an import or
    # names content that is about to, and a modifier pointing at a
    # deleted trait is what stops the whole clear.
    standard_modifiers = list(
        Modifier.objects.filter(
            **scope,
            library_specialisation_set__name__in=[name for name, _ in SPECIALISATIONS],
        )
        .distinct()
        .values_list("pk", flat=True)
    )
    doomed = list(
        Modifier.objects.filter(**scope)
        .exclude(pk__in=standard_modifiers)
        .values_list("pk", flat=True)
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
        ("archetypes", Archetype.objects.filter(**scope)),
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
        (
            "specialisations",
            Specialisation.objects.filter(**scope).exclude(
                name__in=[name for name, _ in SPECIALISATIONS]
            ),
        ),
        ("skills", Skill.objects.filter(**scope).exclude(name__in=standard_skills)),
        (
            "subtypes",
            Subtype.objects.filter(**scope).exclude(
                name__in=FIGHTER_SUBTYPES + VEHICLE_SUBTYPES
            ),
        ),
        ("gang types", GangType.objects.filter(**scope).exclude(name__in=GANG_TYPES)),
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
    """How much a clear would take, as ``{what it is: how many}`` —
    only the kinds that have anything.

    Several querysets may answer to one name: a modifier's scope and its
    effect live in separate tables and are one thing to a reader, so the
    counts add up under the word rather than listing the plumbing.
    """
    found = TallyCounter()
    for label, rows in _imported(pack):
        found[label] += rows.count()
    return {label: count for label, count in found.items() if count}


def clear_imported(pack=None):
    """Delete everything an import writes, leaving standard content whole.

    The inverse of :func:`perform`, and it lives here because the module
    that writes this content is the one that knows its extent. After a
    clear every standard-content seed still reports itself complete, and
    importing the same sheets again lands in the same place. That round
    trip is the point: it makes an import repeatable while the
    spreadsheets are still changing.

    Anything may hold imported content and protect it — a gang that
    bought a weapon, an authored modifier naming a trait — and that
    stops the clear with ``ProtectedError`` rather than taking the thing
    out from under its holder.

    All of it in one transaction, because the holders are only
    discovered part-way through: the weapons go, then a trait turns out
    to be spoken for, and a caller left holding half a library has a
    worse problem than the one it started with. All or nothing, however
    it is called.

    Returns ``{what it was: how many}`` for what went.
    """
    gone = TallyCounter()
    with transaction.atomic():
        for label, rows in _imported(pack):
            found = rows.count()
            if found:
                rows.delete()
                gone[label] += found
    return dict(gone)


def _missing(key):
    raise LookupError(f"plan never mentions {key}")
