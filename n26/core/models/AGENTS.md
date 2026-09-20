# N26 player-data models

Read [`../AGENTS.md`](../AGENTS.md) for the player-data pipeline and query
rules. `models/assignment.py` and `../operations.py` contain the main design
explanations.

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
