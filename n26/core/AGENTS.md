# N26 player data

Player data and the layers that read it. The shape is a pipeline, and each
stage has one job:

```
models/        rows: Gang, Miniature, Assignment, LedgerEntry, Stash
operations.py  the only writer — every change to player data goes through it
card.py        loads a gang's rows into an in-memory tree: two pinned
               row queries, one shared hydration pass
effects.py     computes what the rules do to a card — pure, no queries
render.py      plain dataclasses a template can draw (ModelCard, GangSheet)
browse.py      collections as one rendered shape, whatever their species
hire.py        the hire list, one entry per option
```

Read `models/assignment.py` and `operations.py` first — the module
docstrings explain the design. `n26/design/assignables.md` is the
underlying spec.

## Write player data through operations

- Never create or modify an `Assignment`, `LedgerEntry`, or `LedgerEvent`
  outside `operation(gang, actor=...)`. A bare `objects.create()` skips the
  ledger entry, event and repin. Conversions in `n26.library` are the exception:
  they move no money, emit no event and must prove that every affected gang
  reconciles or unwind the whole conversion.
- Removing an assignment recursively removes everything in its `caused_by`
  chain. Hire, built-ins and grants depend on this behaviour.
- Recompute totals rather than applying deltas. `settle()` repins every touched
  total. If a new object changes rating or credits, update `Operation.touched()`,
  `reconcile.sum_rating` and `total_spent` as needed.
- Raise `NotEnoughCredits` from `settle()` so the transaction unwinds. Do not
  add affordability checks part-way through an operation.
- Use `Refusal` only for errors a player can cause through the UI. Views show
  that message and redirect. Content bugs and caller errors must keep their
  tracebacks.
- Record every change to the gang's story through an operation, including
  renames, notes and characteristic overrides. Device preferences such as
  `AssignmentSet` and `PrintConfig` remain plain saves.
- The ledger is append-only. Folding an entry's events must reproduce the entry,
  as checked by `reconcile.check_entry`. Journal-only events have no entry or
  delta. `Kind.TRANSFERRED`, `Kind.INCOME` and `Kind.CREDITS_ADJUSTED` move
  money without an entry.

## Player-data models

Read [`models/AGENTS.md`](models/AGENTS.md) before changing assignments,
ledger records, model registration, denormalised roots or archive filtering.
Model-specific wiring rules live there.

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
- **Host decides visibility; the scope says the reach.** An assignment
  hosted on the gang rides every member's card (marked `broadcast=True`)
  so its modifiers *can* run there — they draw no line, and gang-hosted
  assignments carry no rating of their own. Whether a targets-the-model
  modifier actually reaches through that ride is the scope's stated
  `reach` ("the model carrying it" never does; "all models in the gang"
  is what the ride is for). Any new code walking a card's nodes needs
  `if node.broadcast: continue` or it will double-count the gang's kit
  onto every fighter.
- **What the gang holds by *grant* rides too.** A thing a modifier gave
  the gang has no row to broadcast, so the gang's card is computed first
  and its acquisitions are dealt onto each member as that card's guests
  (`ComputedCard.echoed`): their modifiers run, and they draw no line,
  add no rating, and say their stored effects only on the gang. Anything
  asking "what does this fighter get from the gang" must read both the
  broadcast rows and the guests, as `access.py` does.
- **Inform, never police.** Restrictions become `Note`s attached to
  lines (`notes.py` — `about` is a real object, never a string). Nothing
  blocks; `buy` deliberately never consults access.

## Cross-layer wiring

- `history.py` describes an old event through its assignment's current name.
  A conversion that changes an assignment's kind can therefore rewrite the
  displayed past. Check the history page and keep the player-facing kind words
  stable. A pick uses its slot type's name, never the slot's label.
- `Has.as_q` needs a `register_lookup()` entry for every model and kind pair, or
  it raises `NotExpressibleAsQuery`.

## Views, forms, templates

- Views are thin function-based views: validate a plain `forms.Form`,
  wrap side effects in `operation(...)`, `messages.success`, redirect.
  `create_gang` is the shape to copy. No ModelForms in core.
- Compute display logic in the view, not the template.
- New interaction state belongs in React islands, not Alpine. Load
  `.agents/skills/n26-react/SKILL.md`; the authoring list is the working example.
  Shareable navigation state belongs in the URL; transient controls and unsaved
  drafts can stay in React. Server validation and operations remain authoritative.
- Read [`templates/AGENTS.md`](templates/AGENTS.md) before changing a template
  or Cotton component.

## Tests

Unit tests of one module's contract sit next to the code
(`n26/core/test_*.py` and `tests.py`, no `tests/` package). Anything
that needs a gang and rulebook-shaped content belongs in
`n26/tests/sandbox/` instead — see `n26/tests/AGENTS.md`.
