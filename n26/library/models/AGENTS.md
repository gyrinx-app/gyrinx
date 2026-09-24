# N26 library models

Read [`../AGENTS.md`](../AGENTS.md) for the authoring pipeline, ingest and
author-facing documentation. Read `base.py` first, then `assignable.py`.

## Model rules

- Managers do not filter implicitly. `Profile.objects.all()` returns every
  pack's content, including archived rows. Subscriber reads must not add
  `archived=False`; discovery surfaces use `selectable()`.
- `Assignable` is a mixin rather than a table. Each kind is a concrete model
  with a `family`, the standard uniqueness constraints, a nullable foreign key
  on `n26.core.Assignment`, and an `ASSIGNABLE_FIELDS` entry.
- Help text lives on the model field. Specs reference it with
  `source=(Model, "field")`, and forms read it through the spec. Model docstrings
  appear on authoring pages, so write them as plain product copy.
- Store names, annotations, numbers and short original display copy. Never store copyrighted rules text.
- A `qualifier` distinguishes same-named content in authoring screens and must
  never reach a player.
- Use database constraints for exactly-one invariants, `clean()` for cross-row
  checks and form errors for mistakes an author can make. `save()` may
  canonicalise values but must not validate them.
- Generate migrations with `manage makemigrations library -n <name>`, then edit
  operations deliberately when needed. Prefer renames over drop-and-add so
  authored data survives. Keep `default_pack_id` importable from
  `models/pack.py`, and do not change the `library` app label.

## Modifiers

A modifier has one scope and one effect. Condition rows narrow the scope.

- Compile scopes to the selector algebra in `n26.core.select` with
  `as_selector()`.
- Read-time effects use `ef_*` verbs. Purchase-time writes use `op_*` verbs.
- Add every new condition model to its scope's `CONDITIONS` tuple. A startup
  check catches omissions.
