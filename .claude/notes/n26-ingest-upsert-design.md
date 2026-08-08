# n26 ingest: upsert

A design for making a re-ingest of changed spreadsheets *apply* the changes,
rather than skipping every row that already exists.

Written against `n26/library/ingest.py` at `d3033110`. Every claim about
current behaviour below was reproduced with throwaway tests against the real
fixture sheets in `n26/tests/sandbox/test_ingest.py`; the outputs are quoted.

---

## 1. The problem

Ingest is three stages — **read** (CSV → rows), **plan** (rows → an
`IngestPlan` of `Planned` objects; reads the database, never writes),
**perform** (plan → rows, through `n26.library.authoring`, in one
transaction). The governing property is that **the preview is the contract**:
what `plan.preview()` shows is exactly what `perform()` does.

`Planned.action` today has two values, `"create"` and `"exists"`. Planning
decides between them at nineteen sites, each spelled
`action="exists" if _exists(...) else "create"`. `perform_one` short-circuits
on `"exists"`: it resolves the key so other rows can point at it, and returns
without writing.

So a re-ingest of a changed sheet writes nothing. That is the headline, but it
undersells the damage: **a re-ingest of a changed sheet is not a no-op — it
litters the pack with orphan taxonomy rows.** The leaf rows a change implies
(a new Category, a new Rule, a new Trait) are planned `create`, because they
genuinely are not there; the row that would *point at them* is planned
`exists` and skipped. The taxonomy lands; nothing references it.

Reproduced, all on the fixture sheets:

| Change to the sheet | What happens today |
|---|---|
| A fighter gains `Category: Leaders` | `Category:gang list:leaders` planned **create**; `Profile:gang queen` planned **exists**. Category row created. `profile.category` stays `None`. |
| Autogun `Cost` 20 → 25 | Planned **exists**. Price stays 20. |
| A weapon profile's `Traits` become `Rapid Fire (2), Unwieldy`, `Str` 3 → 4 | `Trait:rapid fire:2` and `Trait:unwieldy:` planned **create**; the `WeaponProfile` planned **exists**. Two orphan traits; the profile keeps `Rapid Fire (1)` and `Str 3`. |
| A fighter gains `Special Rules: Witch, Overseer` | `Rule:overseer:` created and orphaned; built-ins unchanged. |
| An equipment-list line's `Credits` 20 → 40 | Entry planned **exists** with `price_override: 40` in its fields. Stored override stays 20. |
| An equipment-list line gains `Restrictions: Way-Brethren only` | `Restriction` planned **exists** (it inherits the entry's action). Never applied. The weapon's `usable_by_profiles` stays empty. |
| A skill set moves Primary → Secondary | The new modifier is planned **create** and lands; the old one is *not* retracted. The fighter ends up with **Combat in both tiers** — a wrong card, live in main today. |

The last row is worth separating out: it is not a skipped update, it is a
wrong result produced by the create path. Any design for upsert has to deal
with the retraction side, not just the writing side.

Two smaller findings from reading the code:

- `IngestPlan._replace` (`ingest.py:319`) is dead. Its docstring says
  "planning is two passes for prices; this is the second", but nothing calls
  it. Relevant because it is the only thing that would have made a
  `Planned.fields` dict mutate after `add()`.
- Planning and performing each carry their own statement of "what counts as
  the same row", and they **disagree for `WeaponProfile`**. Planning matches
  `weapon__name__iexact` (`ingest.py:782`); the performer resolves the weapon
  row and matches on it (`ingest.py:1650`). The fixture holds two weapons
  called "Power fist", so this is not hypothetical. Today the disagreement is
  mostly harmless, because nothing is written on an `exists`. Under upsert it
  becomes the difference between diffing against the right row and writing
  onto the wrong one.

---

## 2. What upsert can and cannot detect

The sheets join on an `ID` printing `Name (Profile) (Category ← Section)`,
parsed by `ItemId`. That key is the *sheet's* name for a row. It is not the
database's.

**The database identity, per kind** (from the unique constraints and the
lookups in `_find_existing`):

| Kind | Identity in the pack |
|---|---|
| Weapon, Wargear, WeaponAccessory | name + qualifier |
| WeaponProfile | weapon + name |
| Profile | name + qualifier |
| Category | section + name |
| Trait, Rule | name + annotation |
| Section, Collection, GangType, Subtype, Skill, Specialisation | name |
| CollectionEntry | collection + assignable |
| DefaultAssignmentSet | name (derived from the profile's label) |
| Modifier | name (derived from the profile label, skill set and tier) |

Everything not in that column is an **attribute**, and an attribute change is
detectable. Two consequences that are not obvious:

- **Re-homing a weapon is detectable.** Category and section are part of the
  sheet's ID but are attributes in the database, so moving "Respirator" from
  Personal equipment to Pets is an update, not a new row.
- **Renaming anything is not detectable, and never will be.** A renamed
  weapon plans as a create; the old row stays. No heuristic rescues this: the
  fixture already contains two weapons that print one name at different
  prices in different categories, which is precisely the case a fuzzy matcher
  would get wrong. Do not build a rename detector.

There is a third case that reads like a rename but is not:

- **The `qualifier` is derived from contest within the sheet.** Where two
  catalogue rows share a printed name, both are qualified by their category
  (`_plan_equipment`, the `contested` set). So moving a *contested* weapon
  between categories changes its qualifier, changes its identity, and looks
  like delete-plus-add. Same for a fighter: the qualifier is assigned when a
  second gang claims a name, so the order the sheets are uploaded in can
  decide which row is the bare one.

### What would change this

A **stable source reference** the sheets carry: a short code minted once per
row, never edited, surviving copy-paste and re-sorting; stored on each
ingested content model as `source_ref`, unique per pack. Then identity is the
code, *everything else* including the name is an attribute, renames become
ordinary updates, and rows that vanished from a sheet become exactly
detectable rather than guessed at.

This is the single change that would turn ingest from a re-import into a sync.
It costs one indexed column per ingested kind plus a discipline on the
spreadsheet side. **The backfill is cheap today and impossible later**: the
current content can be matched to sheet rows by today's derived identity in
one pass, but only until somebody renames something. If there is appetite for
this at all, add the column and populate it now, even before the sheets can
emit codes — the option is worth more than the column costs.

Everything below assumes no source ref, and stays correct if one arrives
later.

---

## 3. Recommended design

### 3.1 The action vocabulary

`"exists"` conflates three different things. Replace it with four actions:

| Action | Meaning | Perform does |
|---|---|---|
| `create` | Not in the pack | Inserts, as today |
| `update` | In the pack, and the sheet says something different | Writes the named changes |
| `unchanged` | In the pack, and identical | Nothing (registers the row so others can resolve it) |
| `resolved` | Not a sheet row at all — a row looked up so other planned rows can point at it | Nothing |

`resolved` earns its place. Roughly a third of today's `exists` rows are not
sheet rows: they come from `_plan_existing`, `_resolve_item`, `_profile_ref`
and `_specialisation_ref`, all carrying `Source("resolution", 0)`. Counting
them as "already there, unchanged" inflates the preview with plumbing, and
`perform_one`'s `UNREFERENCED` set is a symptom of the same conflation. Split
them and both problems go away.

The preview's `actions` block becomes
`{"create": n, "update": n, "unchanged": n, "resolved": n}`, and `counts`
(by kind) is unchanged. **A count of updates is not a contract**, so the
preview also grows a `changes` block — see 3.4.

### 3.2 Detect: one settle pass, not nineteen inline checks

The important structural recommendation: **do not rewrite the nineteen
`action="exists" if _exists(...)` expressions. Delete them.**

Replace them with a single pass at the end of `plan_ingest`:

```python
def plan_ingest(...):
    ...
    _plan_restrictions(plan, pending_restrictions)
    _settle(plan)          # <- new: decides every row's action, in one place
    return plan
```

`_settle` walks `plan.planned` in order and, for each row: finds the existing
row in the pack, compares the planned fields against it, and rewrites the
`Planned` with an action, a `changes` dict and the existing row's pk.

Why a final pass rather than in-line:

- **It is one place, not nineteen.** All the identity knowledge and all the
  comparison knowledge sit together and can be read in one screen.
- **It is immune to ordering.** Comparing a foreign-key field means asking
  "does the stored FK point at the row this plan key names?", which needs the
  referenced row to be planned already. A final pass guarantees that for every
  reference; in-line checks do not.
- **It kills a live duplication.** Planning's `_exists(...)` filters and the
  performer's `_find_existing` are two statements of the same fact that
  already disagree for `WeaponProfile`. `_settle` and the performer must share
  one function — promote `_find_existing` to module level as
  `find_existing(plan, planned)` and have both call it.

Only one place in planning reads `.action` today — `_plan_equipment_lists`
passes `entry.action` to `_plan_restrictions` (`ingest.py:1222`) so a
restriction is only created alongside a new entry. That read disappears: under
`_settle` a Restriction is settled on its own terms ("does this item already
allow this profile?"), which incidentally fixes the never-applied-restriction
bug in the table above.

**Comparison, by field shape.** Three shapes cover everything the sheets
carry:

- **Scalar** — `price`, `trade_point_price`, `is_exclusive`, `slots`,
  `position`, `price_override`, `annotation`. Compare the planned value with
  `getattr(existing, field)`.
- **Reference** — the planned value is another planned row's key
  (`category`, `gang_type`, `weapon`, `built_ins`, `attach_to`, `item`,
  `collection`, `allows`). Compare by resolving the key to the *planned* row
  and comparing its `existing_pk` with the stored FK's pk. If the referenced
  row is a `create`, its pk is `None` and the FK necessarily differs — which
  is the right answer. This needs no inverse `key_of()` function, which is
  fortunate, because the plan key encodes the sheet's ID and is not
  recoverable from a stored row.
- **Set** — statline values, traits, built-in members, entries of a
  collection, the skills grid. Compare as a collection of member identities
  plus their extras. See 3.6.

**The updatable table.** Beside `PERFORM_ORDER`, one table naming, per kind,
what the sheets claim to know:

```python
#: What a sheet may rewrite on a row the pack already holds. Every field
#: the planner puts in `fields` appears in exactly one of the three
#: lists, and a test proves the partition is total.
SHEET_FIELDS = {
    "Weapon": Fields(
        identity=("qualifier",),
        updatable=("price", "trade_point_price", "is_exclusive",
                   "slots", "category"),
        ignored=("unpriced", "statline_type"),
    ),
    ...
}
```

`identity` is what the lookup uses; `updatable` is what `_settle` diffs and
perform writes; `ignored` is a deliberate statement that a planned field is
not a claim about an existing row (`unpriced` is a planning-time hint;
`section_position` only applies when a heading is founded).

**Where this list lives: in the ingest planner, not on the model and not in
`specs.py`.** It is a statement about *the sheets* — what these four
spreadsheets are authoritative about — not about the content kind. A model
attribute would be wrong for a second importer with different columns, and a
spec describes what a *verb* takes, which is a different question. The model
stays the authority on what is valid; the planner is the authority on what
this import claims to know.

### 3.3 Represent: the plan carries the difference

`Planned` gains two frozen fields:

```python
@dataclass(frozen=True)
class Planned:
    kind: str
    key: str
    name: str
    fields: dict
    action: str          # create | update | unchanged | resolved
    source: Source
    changes: dict = field(default_factory=dict)   # {field: {"from":…, "to":…}}
    existing: str | None = None                   # pk of the row it matched
```

`changes` holds printable values, not model instances — a reference field
renders as the referenced thing's name, a set renders as
`{"added": [...], "removed": [...]}`. `as_dict()` includes both, and the whole
preview stays JSON-able (`test_the_preview_is_plain_data` keeps passing).

Carrying `existing` (the pk) matters for the contract: perform fetches *that
row*, not "whatever the same lookup finds now". If it has gone, that is a loud
error — "the row the preview described is no longer there; preview again" —
never a silent fallback to create.

### 3.4 Preview: show every change, grouped

The ingest page already posts the same files twice (Preview, then Import) and
keeps nothing between them, so the diff is recomputed deterministically. That
makes a confirm-the-diff flow free rather than a bolt-on.

`plan.preview()` gains:

```python
"changes": [
  {"kind": "Weapon", "name": "Autogun", "key": …, "source": {…},
   "changes": {"price": {"from": 20, "to": 25}}},
  ...
]
```

and the view groups it the way `_problems_by_shape` already groups problems —
by *what changed*, not by which row changed it:

> **142 × Weapon — price changed** — Autogun 20 → 25, Frag lance 0 → 15, …
> **3 × Profile — category set** — Gang Queen → Leaders (Gang List), …

The headline line on the page becomes
`412 to create, 145 to change, 2,208 unchanged`.

Two cheap guards belong here:

- **A wrong-file check.** If updates exceed a threshold of the pack (say
  half), say so prominently. Uploading last year's export over this year's
  content is the realistic accident, and it is loud in the aggregate and
  invisible row by row.
- **Cap the rendered list** (the problems list already does this with
  `examples`), because a genuine 3,000-change diff is not readable and
  pretending otherwise is worse than admitting it.

### 3.5 Perform: one new verb, not a new verb family

`perform_one` becomes explicit rather than `getattr`-driven:

```python
def perform_one(self, planned):
    if planned.action in ("unchanged", "resolved"):
        if planned.kind not in self.UNREFERENCED:
            self.resolve(planned.key)
        return
    if planned.action == "update":
        UPDATERS[planned.kind](self, planned)   # KeyError if missing — loud
        return
    self.result.created[planned.key] = creator(planned)
```

**On the authoring layer.** `n26/library/CLAUDE.md` says `authoring.py` is the
one API that writes content, and there is no `update_*` family. But the
codebase has already answered this question elsewhere: the staff edit pages
added in `fc9e2d24` update rows through `GeneratedForm.apply_to`
(`forms.py:368`), which does `setattr` over the fields the spec names and
saves — with a docstring saying so explicitly: *"The verb is for making
things; changing one is a write to the columns the spec already names."*

So the precedent is set, and I recommend following it rather than minting
twenty-five `update_*` verbs:

- **Add exactly one verb, `authoring.revise(row, **fields)`** — write the
  named columns of an existing authored row and save. Refactor
  `GeneratedForm.apply_to` to call it, so the admin edit path and the ingest
  update path are one write path.
- **Give it no spec, deliberately.** Its parameters are the *row's* fields,
  which the row's own spec already describes; a spec for `revise` would be a
  spec of a spec. The discovering guard in `tests/sandbox/test_specs.py` only
  refuses `targets_*` / `ef_*` / `op_*` without a spec, so nothing breaks —
  but this is a genuine, small departure from the "give create/add verbs a
  spec anyway" convention and should be a conscious call.
- **`revise` must refuse many-to-many fields**, not `setattr` them. A latent
  bug proves the point: `apply_to` raises `TypeError: Direct assignment to the
  forward side of a many-to-many set is prohibited` for any `Many` spec
  field. It is latent only because no leaf kind whose spec has a `Many`
  currently gets an edit page — `add_weapon_profile`'s `traits` is the one
  such field. Fix `apply_to` while unifying, and have `revise` route sets to
  the set-shaped verbs below.
- **Make `set_statline` idempotent.** It currently does
  `Statline.objects.create(owner=owner)`, and `Statline.profile` /
  `Statline.weapon_profile` are `OneToOneField`s, so a second call raises. A
  verb called "set" should be settable twice; this is a bug fix, not a new
  API.

Set-shaped writes get their own small verbs where the semantics are genuinely
"replace the set": `set_traits(weapon_profile, traits)` and, if replacement is
chosen for entries, `set_entries(collection, entries)`. These are `set_*`
verbs by the naming convention already in `authoring.py`.

`IngestResult` gains `updated: dict` alongside `created` and `existing`, and
the success message becomes "Created N rows, changed M."

### 3.6 Related sets, per kind

Replace deletes rows an author added by hand; add-only lets the pack drift
from the sheet forever. The right answer differs by kind, and the deciding
question is: **is this set somewhere hand-authored content actually lives?**

| Set | Recommendation | Why |
|---|---|---|
| **Statline values** (profile, weapon profile) | **Replace** — but a blank sheet cell means "the sheet says nothing", leaving the stored value alone. | Fixed columns, wholly sheet-owned. `_statline_values` already drops blanks; keep that meaning. |
| **Traits on a weapon profile** | **Replace** | Printed on the card, wholly from the statlines sheet. Add-only accumulates `Rapid Fire (1)` *and* `Rapid Fire (2)` forever. |
| **Skill-grid modifiers** | **Replace within the sheet's own footprint** — retract placement modifiers attached to this profile that place a *skills* category and that the sheet no longer names. | This is the live wrong-card bug. Retraction must detach from the profile and delete the modifier only if nothing else carries it (`attach_modifiers_to` makes them shareable), deleting the scope and effect rows with it — the pattern `_imported()` already uses. |
| **Collection entries** | **Replace, scoped to the collections this upload mentions** | The equipment-lists sheet is the whole statement about a list. The trap: "delete entries not planned" would empty every *other* gang's list on a partial upload. Scope to the `Title`s present. |
| **Restrictions (`usable_by_*`)** | **Add-only, with a note when the sheet drops one** | They are stored on the *item*, not the entry, so they are shared across every list naming that weapon; one list dropping a restriction must not retract another list's. (That sharing is itself a modelling wrinkle — two lists restricting one weapon differently already collide. Out of scope; worth an issue.) |
| **Built-in members** | **Add-only, with a note listing what the sheet no longer names** | This is where hand-authored content actually lives. Ingest's own comment says built-in-only kit — hunting rigs, exo-suits, natural weapons — "is never sold, so no sheet defines it", and the planner *drops* such items with a note today. Under replace, every re-import would delete exactly the kit an author added by hand to fix that. |

The built-ins row is the one I would most expect to be argued with, and it is
the one worth arguing about: add-only means an author who removes "Witch" from
the sheet sees a note on every import forever until they act. That is
annoying and honest. Replace is tidier and occasionally destroys work that
cannot be recovered from the sheets. I would take the annoyance.

### 3.7 Rows that disappear from a sheet: out of scope, and here is the report

**Removal and archival are explicitly out of scope for this work**, apart
from the within-row set retractions in 3.6.

The reason is not squeamishness: the upload form deliberately accepts one
sheet at a time ("a partial upload is a real thing to want — the statlines
alone, to fix a column"), so *absent from this upload* cannot mean *deleted*
without knowing the upload was complete. Nothing in the plan knows that. And
wholesale deletion is already served, safely, by the clear page — one
transaction, refuses when content is in use, leaves standard content whole.

What I do recommend now, because it is one query per kind and writes nothing:
**an unmentioned-rows report**. After settling, for each kind the upload
covers, count the rows in the pack that the upload did not mention, and say so
as notes:

> The equipment sheet does not mention 14 weapons the pack holds — Web
> pistol, Shock stave, … Nothing was removed.

If more is wanted later, the next step is **archival, not deletion**:
`archived` already exists on every `Content` row, it is reversible, and it
does not retract content from gangs that already hold it.

**The orphan Category rows in the motivating example are not a disappearance
problem** and need nothing here. They are orphaned because the Profile that
should point at them was skipped; once Profile plans `update` and writes its
category, the Category row it created is exactly right. Residual orphans (a
category the sheets stopped using) fall under the report above.

### 3.8 Nothing may fail silently

`PERFORM_ORDER` already has the property that a planned kind missing from it
is skipped without a word (issue #2153). This design adds a second thing that
can be planned and a third registry to forget, so the bug class should be
closed in the same work, not extended.

Four guards, all cheap:

1. **`perform()` refuses a plan it cannot fully execute.** Before the loop,
   check every planned kind against `PERFORM_ORDER` and raise naming the
   missing kind. Three lines, and it closes #2153.
2. **`UPDATERS` is a dict, looked up, not `getattr`.** A missing updater for a
   kind that planned an update is a `KeyError` with the kind's name, not a
   quiet skip.
3. **The partition is total.** A discovering test asserts that, for every
   `Planned` row the fixture sheets produce, every key of `fields` appears in
   exactly one of that kind's `identity` / `updatable` / `ignored` lists. A
   newly added plan field then fails a test rather than being silently
   un-diffed — which is the specific silence this design could introduce.
4. **Every plannable kind is accounted for.** A discovering test over the
   kinds ingest can plan asserts each appears in `PERFORM_ORDER`, has a
   creator, and either appears in `SHEET_FIELDS` or in an explicit
   `NEVER_UPDATED` set carrying a reason (a Trait is nothing but its identity;
   there is nothing to update). Paired with a
   `test_there_is_something_to_check`, per the house pattern in
   `test_money_words.py`.

---

## 4. Decisions with real alternatives

### D1. Clobbering hand-authored work

The one that matters. Authors edit content in the admin; the sheets are
re-exported and re-uploaded; something has to give.

| Option | Cost |
|---|---|
| **Sheet always wins** | Silent. An author's price fix vanishes on the next import with no trace, and `Content` carries no provenance to reconstruct what happened. |
| **Fill only what is empty** | Cheap, and wrong for the main use case — correcting a price 20 → 25 is exactly what the team wants and is not a fill. "Empty" is also ill-defined for a price of 0. |
| **Per-field provenance** | Honest and expensive: a new table, and *every* write path — including the admin edit pages — must record into it or the provenance lies. |
| **Show the diff, require a human to confirm** | The preview already exists, the page already has two buttons over the same files, and the diff is machinery this design needs regardless. |

**Recommendation: the fourth, all-or-nothing to begin with.** Preview lists
every change field by field, grouped by shape; Import applies exactly those.
This is "sheet always wins" *plus visibility*, and visibility is what turns
silent clobbering into a decision somebody made.

Two deliberate follow-ons, designed for but not built:

- **Granular confirmation.** Because plan keys are deterministic from the
  files, the preview form can post back a set of keys to skip and `perform`
  can honour it — no persisted plan needed. Build this the first time
  clobbering actually costs someone work, not before.
- **An ingest-run record.** A small model holding when, who, and the preview
  payload (which now contains the full diff). That is the cheap 80% of
  provenance: "when did this price change, and from what" becomes answerable
  after the fact, without touching any write path.

### D2. The stable source reference

Covered in section 2. **Recommendation: add the column now even if the sheets
cannot emit codes yet**, and backfill from today's derived identity. Renames
close the window permanently. If the answer is no, say so explicitly and
accept that ingest will never detect a rename or a deletion.

### D3. Built-ins: add-only or replace

Covered in 3.6. **Recommendation: add-only with notes**, because built-ins are
the known home of hand-authored kit. This is the decision most likely to be
wrong for reasons only the maintainer knows.

### D4. `revise` without a spec

Covered in 3.5. **Recommendation: one generic verb, no spec, and unify
`apply_to` onto it.** The alternative — a per-kind `update_*` family, each
with a spec — costs about twenty-five verbs and twenty-five specs, and only
pays for itself if the authoring *forms* ever need to compile to updates. They
do not today; `apply_to` deliberately bypasses the verbs already.

---

## 5. Implementation plan

**Stage 0 — unify identity. This is the riskiest part of the whole change.**
Promote `_find_existing` to a module-level `find_existing(plan, planned)` and
make planning use it in place of its own `_exists(...)` calls. Fix the
`WeaponProfile` divergence. No behaviour change intended, which is exactly why
it is dangerous: a subtle change to "what counts as the same row" silently
binds a later diff to the wrong row, and everything downstream then writes
confidently onto it. Land it alone, with a test that re-planning a performed
plan finds exactly the rows perform created, kind by kind.

**Stage 1 — vocabulary and detection, preview only, no writes.** `_settle`,
the four actions, `changes`, `existing`, `SHEET_FIELDS`, and the preview's
changes block. `perform` treats `update` exactly as `unchanged` and writes
nothing. Shippable and completely safe, and it is how the clobbering risk gets
sized honestly: **run it against the real sheets and look at the diff before
anyone writes a line of stage 2.**

**Stage 2 — scalar and reference updates.** `authoring.revise`, `UPDATERS`,
`IngestResult.updated`, the reworded success message, and all four guards from
3.8. At the end of this stage the motivating example works end to end: a
fighter's Category lands on re-ingest, and its Category row is no longer an
orphan.

**Stage 3 — related sets, one kind per change**, in ascending order of risk:
statlines, traits, collection entries and price overrides, restrictions
(fixing the never-applied bug), skill-grid modifiers (the live wrong-card
bug), built-ins last.

**Stage 4 — optional, independent.** The unmentioned-rows report; the
ingest-run audit record; granular skip-these-keys confirmation; the source-ref
column and backfill.

Housekeeping worth folding in: delete the dead `IngestPlan._replace`.

---

## 6. What to test

Existing tests that change meaning:

- `TestIdempotency.test_a_second_upload_plans_exists_and_creates_nothing` —
  `{p.action for p in again.planned} == {"exists"}` becomes
  `<= {"unchanged", "resolved"}`, plus an explicit
  `assert not [p for p in again.planned if p.action == "update"]`. The
  distinction matters: the old assertion's meaning was "nothing happens", and
  under the new vocabulary that has to be said in two parts.
- `TestPerform.test_creates_exactly_what_the_preview_said` — extend to
  `result.updated` against the preview's `update` tally, keeping "the preview
  is the contract" total rather than true only of creates.
- `TestPreview.test_the_preview_counts_what_the_upload_creates` — the
  `actions` dict has four keys.

New tests, by the claim they pin:

- **Upsert idempotency** (the stronger claim, and the one that should replace
  the old test in spirit): plan a *changed* sheet twice. The first run plans
  and applies exactly the changed fields; the second plans nothing but
  `unchanged`/`resolved` and writes nothing.
- **The motivating case, end to end**: import without a Category, re-import
  with one, assert `profile.category` is set *and* that no orphan Category
  row remains unreferenced.
- **One row per line of the table in section 1** — price, traits + statline,
  entry override, restriction added later, skill set moved between tiers.
- **The diff is the contract**: for each `update` row, the fields named in
  `changes` are the only fields that differ afterwards. Assert on a row that
  has a hand-edited field the sheet does not carry (a
  `library_author_help`, a `fits_category`) and prove it survives.
- **Reference comparison**: a weapon re-homed to a different category updates;
  the same weapon re-uploaded unchanged does not.
- **Related sets, per kind**: traits replaced, statline values replaced, blank
  cells leaving stored values alone, built-ins add-only with a note naming
  what the sheet dropped, entries scoped to the collections the upload
  mentions (a one-gang upload leaves other gangs' lists intact — the trap in
  3.6).
- **Nothing fails silently**: a plan carrying a kind absent from
  `PERFORM_ORDER` raises naming it; a kind planning an update with no updater
  raises naming it; the `SHEET_FIELDS` partition is total; every plannable
  kind is in `SHEET_FIELDS` or `NEVER_UPDATED`.
- **The vanished row**: an `update` whose `existing` pk has been deleted
  between preview and import raises, and the transaction holds.
