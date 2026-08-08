# CLAUDE.md — n26/library

Game content, and the tools for writing it. Everything an author can put
in the library flows through one chain, and nothing skips a layer:

```
models/          the content rows (Weapon, Skill, Profile, Collection, …)
authoring.py     the verbs — the one API that writes content
specs.py         each verb described as data (its fields, their types)
forms.py         Django forms generated from the specs
views.py         the staff authoring pages, driven by small registries
ingest.py        spreadsheets in → a previewable plan → rows out
standard_content.py  the seed rows nobody authors, planted idempotently
offers.py        what a kind declares about itself; forms derive the rest
```

Read `models/base.py` (107 lines) first — it states the app's governing
philosophy. Then `models/assignable.py` and `authoring.py`.

## The model rules

- **Managers do no implicit filtering.** `Profile.objects.all()` returns
  every pack's content, archived included. Narrowing is opt-in
  (`in_packs()`, `unarchived()`, `selectable(packs)`). Never add
  `archived=False` to a read path a subscriber sees; discovery surfaces
  use `selectable()`.
- **`Assignable` is a mixin, not a table.** Each kind is its own model.
  A new kind is: `class X(Content, Assignable[, UsableBy][, Optioned])`,
  a class-level `family = Family.…`, a `Meta` with verbose names and
  ordering, the standard constraints (unique per pack on lowercased
  name + qualifier; exclusive items carry no trade-point price) — and a
  column on `n26.core`'s `Assignment` plus an entry in
  `ASSIGNABLE_FIELDS`, or the app refuses to boot.
- **Help text lives on the model field, nowhere else.** Specs reference
  it (`source=(Model, "field")`); forms read it through the spec. Model
  docstrings are shown to authors on the authoring pages — write them as
  product copy: a plain definition first, detail after.
- **No rules text, ever.** Names, annotations, and numbers only; the
  book's wording is copyrighted.
- A `qualifier` is author-facing only — it tells two same-named things
  apart in authoring screens and must never reach a player. A test
  enforces this.
- Validation is layered on purpose: database constraints for
  exactly-one invariants; `clean()` for cross-row sense checks; form
  errors in words for anything an author can trip. `save()` is for
  canonicalising values only (it runs for importers too, which never
  call `full_clean`) — never for validation.
- Migrations are hand-edited and descriptively named. Prefer renames
  over drop-and-add so authored data survives. `default_pack_id` is
  referenced by name in migrations and must stay importable from
  `models/pack.py`; the app label is pinned to `library` — don't touch
  either.

## Modifiers

A modifier is one **scope** (who it reaches) plus one **effect** (what it
does), each a small typed row with an exactly-one constraint. Narrowing
lives in **condition rows** hung off the scope. The grammar:

- Scopes compile to the shared selector algebra in `n26.core.select`
  via `as_selector()`.
- Effects split by when they happen: computed at read time (`ef_*`
  verbs: adds, removes, changes a stat, offers a choice, places a
  category) versus written at purchase time (`op_*` verbs, e.g. adds a
  model).
- A new condition model must be named in its scope's `CONDITIONS`
  tuple, or its rows are stored but never read (a startup check
  catches this).

## Extending the authoring surface

Adding a verb means touching, in order:

1. The verb in `authoring.py` (naming: `create_*` for new things,
   `add_*` for parts of a thing, `ef_*`/`op_*` for effects,
   `targets_*` for scopes, predicates read as predicates).
2. A `Spec` in `specs.py` — discovering tests refuse a scope, effect,
   or condition verb (`targets_*`, `ef_*`, `op_*`) without one; give
   `create_*` and `add_*` verbs one too even though no guard forces it.
3. The registries in `views.py`: `LEAF_KINDS` if it gets a page (and
   `LEAF_DESCRIBE` for the page's blurb); `DETAIL_KINDS` if the thing
   has parts added to it over time; `DETAIL_VIEWS` for a bespoke detail
   page.

Several parallel lists are deliberate extension points, each guarded by
a check or a generated constraint (`ASSIGNABLE_FIELDS`, `SCOPE_FIELDS`,
`EFFECT_FIELDS`, `OFFERABLE_KINDS`, `GRANTABLE_FIELDS`, …). Widening one
is one line plus a migration plus deliberate thought — never quietly.

Kinds declare, forms derive: `ATTACHMENT_ASKS` and
`SUGGESTED_BUILT_INS` sit on the model class and `offers.py` computes
what a form shows — no form hardcodes a kind there (the inline-create
shortcut for rules and subtypes in `forms.py` is the one deliberate
exception). Note: `ATTACHMENT_ASKS` replaces rather than merges — a
kind that declares its own must restate the inherited asks it still
wants.

## Ingest

Three stages: read (CSV → dicts), plan (→ an `IngestPlan` of frozen
rows plus problems; reads the database, never writes), perform (executes
exactly the plan, through the authoring verbs, in one transaction).
**The preview is the contract** — what `plan.preview()` shows is what
`perform()` does. Standing rules: resolve, never create, across sheets;
built-ins are free; a missing seed row is a loud error, never quietly
re-planted. A new planned kind must be added to `PERFORM_ORDER`, or
`perform()` skips it without a word.

## Comments

A comment states a constraint, an invariant, or a consequence the code
cannot show — briefly, in plain words. It must make sense to a reader
who has never seen any earlier version of this code: no people, no
tickets or PRs, no "graduated from", no "used to be", no "for now".
Longer reasoning belongs in the module docstring or a `n26/design/`
doc, cited by filename — and never cite a design doc's section numbers
in user-visible messages. The examples to imitate:
`models/statline.py` (why canonicalising happens in `save`),
`models/pack.py` (why a function must stay importable).
