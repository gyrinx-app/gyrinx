# Production maintenance and backfills

Use maintenance Backfills for production data repairs. Gyrinx runs on Cloud
Run. `manage prodshell` is read-only, and management commands cannot write to
production.

## Implement a production repair

- Put the repair logic in a module and add a `Backfill.Operation` choice in
  `models.py`.
- The maintenance admin GET previews a dry run. POST creates a `Backfill`
  record, enqueues work, and redirects to the record.
- Do all repair work in the task framework, never in the request. Record every
  final result on the `Backfill` row. Do not rely on an exception to preserve
  the result.
- Assume the task may be delivered more than once. If a second delivery must
  stop, guard the repair with an advisory lock. Record attempt counts so large
  jobs cannot retry forever.
- Re-enqueue long work in chunks and report progress on the same record.

Use `convert_specialisation` in `n26/maintenance.py` as the example for a task
that records its result. See [`../tasks/AGENTS.md`](../tasks/AGENTS.md) for retry
and duplicate-delivery rules.

## N26 gang-by-gang repairs

For repairs that process gangs one at a time, define `find` and
`apply_one(gang_id)`, then call `run_per_gang`. It calls `run_batched` to enqueue
the next chunk before the Pub/Sub or Cloud Run deadline.

Use `_run_recorded` only for library repairs and conversions that keep all
affected gangs in one transaction. The maintenance console tests reject any
gang-by-gang module that calls `_run_recorded`.

Before deployment, test with a disposable local database containing a similar
volume of data to production. Verify the affected records independently before
and after the repair.
