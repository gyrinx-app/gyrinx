# N26 player-data models

Read [`../AGENTS.md`](../AGENTS.md) for the player-data pipeline and query
rules. `models/assignment.py` and `../operations.py` contain the main design
explanations.

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
  delta. `Kind.TRANSFERRED` is the one standalone event that moves money.

## Keep model wiring complete

- A new assignable kind needs an `ASSIGNABLE_FIELDS` entry, a matching nullable
  foreign key on `Assignment`, and a generated migration. Startup checks
  `n26.E001` and `n26.E002` enforce agreement.
- Add every new condition model to its scope's `CONDITIONS` tuple. Startup
  checks `n26.E003` and `n26.E004` catch omissions.
- `Assignment.save()` derives denormalised roots. Do not use `objects.update()`
  or `bulk_update()` for assignments. `Operation.move` re-saves each assignment
  in a subtree for this reason.
- `Operation.hire` sets a membership assignment's `miniature_root` by hand.
  Any other membership creator must do the same.
- Deleting a membership assignment also deletes its `Miniature`. Removing a
  model from a gang archives the membership instead.
- Import every settings-group model from `models/__init__.py` so it registers
  itself in `SETTING_GROUPS`.
- Readers opt into `archived=False`; it is never a default manager filter.
- An assignment with `removes=True` is machinery rather than a displayed line.
  `assemble()` keeps it in `Card.removals`, but direct database readers must
  also exclude it.
