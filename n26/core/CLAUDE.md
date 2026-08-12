# CLAUDE.md — n26/core

Player data and the layers that read it. The shape is a pipeline, and each
stage has one job:

```
models/        rows: Gang, Miniature, Assignment, LedgerEntry, Stash
operations.py  the only writer — every change to player data goes through it
card.py        loads a gang's rows into an in-memory tree: a pinned two
               row queries, one shared hydration pass
effects.py     computes what the rules do to a card — pure, no queries
render.py      plain dataclasses a template can draw (ModelCard, GangSheet)
browse.py      collections as one rendered shape, whatever their species
hire.py        the hire list, one entry per option
```

Read `models/assignment.py` and `operations.py` first — the module
docstrings explain the design. `n26/design/assignables.md` is the
underlying spec.

## Writing player data

- **Never create or modify an `Assignment`, `LedgerEntry`, or
  `LedgerEvent` outside `operation(gang, actor=...)`.** A bare
  `objects.create()` skips the ledger entry, the event, and the repin;
  nothing notices until `reconcile` runs.
- **Recompute, never delta.** `settle()` repins every touched total by
  recomputing it. If a new thing contributes to rating or credits, make
  sure `Operation.touched()` sees the affected model and
  `reconcile.sum_rating` / `total_spent` cover it.
- **Refuse at the boundary.** `NotEnoughCredits` is raised from
  `settle()` so the whole transaction unwinds. Do not add mid-operation
  affordability checks.
- **A refusal a player can reach is a `Refusal`**, and its message is a
  sentence written for them: views catch that one class, show it, and
  redirect. A content bug or a caller mistake is not one — nobody can
  press their way to it, so it stays an ordinary error with a traceback.
- Display-only state (`AssignmentSet`) deliberately bypasses operations.
  Keep the line clean: if a feature costs money or changes a rating, it
  goes through an operation.
- The ledger is append-only, and folding an entry's events must
  reproduce the entry — `reconcile.check_entry` checks exactly that.

## Reading player data

- **`effects.compute()` issues no queries and must stay that way.**
  Everything it needs is loaded by `card.py`. If compute needs a new
  relation, add it to `build_modifier_index` or `hydrate_rows`'s
  paths — then update the tests that pin exact query counts.
- The query budget is an invariant, not a hope: a whole gang is a fixed
  number of queries however many models and however much kit. Tests
  check the count stays flat as the gang grows.
- **Renderers get plain dataclasses.** Nothing in `render.py` knows HTML.
  A new display fact is a new field, computed in Python.
- Every assignable a card shows carries a `Provenance` saying where it
  came from.
- **Mind the broadcast flag.** The gang's own rows ride every member's
  card (marked `broadcast=True`) so gang-wide rules reach them — they
  draw no line, and gang rows carry no rating of their own. Any new code
  walking a card's nodes needs `if node.broadcast: continue` or it will
  double-count the gang's kit onto every fighter.
- **Inform, never police.** Restrictions become `Note`s attached to
  lines (`notes.py` — `about` is a real object, never a string). Nothing
  blocks; `buy` deliberately never consults access.

## Wiring — steps that are easy to miss

- **A new assignable kind is three edits**: an entry in
  `ASSIGNABLE_FIELDS` (`models/assignment.py`), a matching nullable FK
  on `Assignment`, and a migration. Startup checks (`n26.E001`/`E002`)
  refuse to boot if they disagree.
- A new condition model must be named in its scope's `CONDITIONS` tuple
  (`n26.E003`/`E004`) or its rows are stored but never read.
- `Has.as_q` needs a `register_lookup()` entry per (model, kind) pair,
  or it raises `NotExpressibleAsQuery`.
- **`Assignment.save()` derives the denormalised roots.**
  `objects.update()` / `bulk_update()` bypass it and the roots drift
  silently — `Operation.move` re-saves every row in a subtree for
  exactly this reason. Don't bulk-write assignments.
- A membership assignment's `miniature_root` is set by hand in
  `Operation.hire`, not by `save()` — it is hosted on the gang but
  *about* the model. Anything else creating one must do the same.
- A settings-group model registers itself on import; it must be reachable
  from `models/__init__.py` or `SETTING_GROUPS` never sees it.
- `archived=False` is never a default filter. Readers opt in explicitly
  (`card_rows` does; `reconcile.sum_rating` also excludes assignments
  whose model has left the roster).

## Views, forms, templates

- Views are thin function-based views: validate a plain `forms.Form`,
  wrap side effects in `operation(...)`, `messages.success`, redirect.
  `create_gang` is the shape to copy. No ModelForms in core.
- Compute display logic in the view, not the template.
- UI state lives in the URL. Alpine is allowed for presentation-only
  narrowing of content already on the page (the gang table's filter is
  the example to follow) — never for swapping form variants or anything
  the server would render differently.
- Template trees under `n26/core/templates/`:
  - `n26/…` — pages and layouts.
  - `cotton/n26/…` — this edition's components, used as `<c-n26.foo>`.
    A directory is a namespace: `gang_table/index.html` is
    `<c-n26.gang-table>`, `row.html` beside it is
    `<c-n26.gang-table.row>`. Underscores in filenames become dashes in
    tags.
  - `cotton/ui/…` — deliberate overrides of the installed kit's
    components. They win only because `n26.core` sits above
    `django_cotton_ui` in `INSTALLED_APPS`; reordering silently reverts
    them.
- **Every component opens with a `{% comment %}` block** (the tag, a
  usage example, the reasoning, the props), **and new components must
  declare their public props in `<c-vars>`** — include `class=""` and
  thread it through. The gallery reads both to build its docs, so an
  undeclared prop is invisible there.
- A new or renamed component must also be registered in
  `n26/designsystem/catalog.py` and given demos, or it will not appear
  in the gallery. See `n26/designsystem/CLAUDE.md`.
- Cotton traps: a `{% block %}` inside a component attribute renders as
  nothing (use `<c-slot>`); write `&amp;` not `&` in attributes; the
  platform's cotton checker does not scan n26 templates, so the
  `:field=` vs `field=` mistake is unguarded here — check your colons.
  A template filter inside a `:attribute` (`:count="roster|length"`)
  silently evaluates to nothing — compute the value in the view.
  Passing `class=` to a component whose `<c-vars>` does not declare it
  (the kit's `c-ui.badge`, for one) renders a *second* class attribute
  via `{{ attrs }}` — the browser keeps the first and silently drops
  the component's entire styling.

## Tests

Unit tests of one module's contract sit next to the code
(`n26/core/test_*.py` and `tests.py`, no `tests/` package). Anything
that needs a gang and rulebook-shaped content belongs in
`n26/tests/sandbox/` instead — see `n26/tests/CLAUDE.md`.

## Comments

A comment states a constraint, an invariant, or a consequence the code
cannot show — briefly, in plain words. It must make sense to a reader
who has never seen any earlier version of this code: no people, no
tickets or PRs, no "used to", no "for now". Longer reasoning belongs in
the module docstring or a `n26/design/` doc. The good examples to
imitate are in `operations.py` and `models/assignment.py`.
