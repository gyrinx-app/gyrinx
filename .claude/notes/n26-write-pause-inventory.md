# n26 write-pause inventory

Checked against production Python outside migrations and tests.

## Guarded boundaries

- Gang and fighter writes: `core.operations.operation`; gang clone outer transaction; gang creation before its first operation.
- Campaign writes: `core.campaigns.campaign_operation`.
- Permanent deletion: `core.deletion.destroy_gang` and `destroy_campaign`.
- Direct display-state writes: print setup and dismissed-offer views. Other unsafe `/n26/` requests use the registered request gate before view or form parsing.
- Library authoring: every public authoring verb that directly mutates a model uses `guarded_write`. Unsafe library views and admin pages also use the request gate.
- Ingest: uploaded-sheet store/discard, perform, and clear use a guarded outer transaction. The upload guard is acquired before file storage writes or deletes.
- Admin: the registered `n26` and `library` app labels make unsafe model-admin requests enter the request gate before form parsing, including artwork upload validation and default saves, formsets, actions, and deletes.
- Commands: `n26_backfill_foundations` guards each idempotent seed transaction.
- Maintenance: every ordinary registered n26 operation carries `write_scope="n26"`; all task routes carry the same scope. `WritesPaused` escapes all broad runner catches. `N26PausedTaskRoute` is reserved for the exact activation consumer and requires `backfill_id` plus `pause_generation`.
- Built-in propagation: both propagation routes are declared in the scoped n26 route list, including the scheduled sweep. Its producer may enqueue during a pause; delivery is deferred before task execution starts.

## Deliberate control-plane path

`register_control_operation` leaves a pause-control page reachable while n26 is paused. It does not grant a write permit. Activation and cleanup domain code must use the exact bound consumer assertion; ordinary staff and superusers receive no bypass.

## Read paths

Ordinary safe n26 requests remain available. The base layout shows the persisted pause reason and states that n26 remains viewable. No ordinary render-time database mutation was found. The Journal content maintenance GET is the one preview that executes its seed and rolls it back; `journal_content.preview()` enters the transaction admission guard before its first scratch write, so it drains before a pause and returns the standard 503 while paused. The other maintenance GETs build read-only plans and preview their stored descriptions without mutating rows.

## Historical migrations

No n26 migration imports `n26.library.authoring`. Scope registration performs no database query during app loading, and the pause row is created from `post_migrate` only after its table exists. A fresh PostgreSQL migration smoke covers this ordering.
