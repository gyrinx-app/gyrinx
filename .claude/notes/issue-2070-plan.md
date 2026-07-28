# Issue #2070 — finish the stat-advancement cleanup, and tell affected players

Follow-up to #2069 (Track B of #1861), which converted 2,306 fighter/stat pairs and
deliberately left 155 alone. This handles the leftovers.

Delivered as a Backfill triggered from the maintenance admin — the app runs on Cloud
Run, so a management command has no way to reach production.

## Revised after review — what changes from the first attempt

The first implementation was reviewed twice and both passes found real defects. The
revision is driven by one lesson:

> **Every bug in this work came from computing what a value _should_ become instead of
> applying the change and reading what it _does_ become.**

That produced the wrong-arithmetic bug in 0196, the set-mode bug that inflated eleven
production fighters, and wrong predicted before/after values feeding player messages.
So the classification stops predicting.

### 1. Verify by re-resolution, not arithmetic

For every candidate: read the fighter's rendered stat, apply the change **in memory**,
read it again. Convert only when the two agree — or, for the deliberate corrections,
when they differ in exactly the expected direction. Build the player messages from
those real before/after values rather than predicted ones.

This closes the class. A `set`-mode mod, an odd base format, an unparseable value — all
show up simply as "the rendered value moved", with no proxy left to be wrong about.

### 2. Survive an interrupted run

Current code applies with no transaction and writes its memory record **last**. A
timeout mid-run leaves fighters changed and no record of them, and the next run then
reads its own repair as the bug and destroys a player's edit — the exact failure the
idempotency fix was for.

- Create the `Backfill` with `status=RUNNING` and `acted_pairs` populated **before**
  applying.
- Wrap the record write and the apply in one `transaction.atomic()`.
- Flip to `DONE` after.
- `previously_handled()` counts every status except `CANCELLED`, not just `DONE`.
- Send messages from `transaction.on_commit`, so nobody is told about a change that
  rolled back.

`persistent_stash.py` already does the transaction version of this; follow it.

### 3. Don't run twice at once

`_running_guard()` in `gyrinx/maintenance/admin.py` already exists for this. Two admins
or a double submit currently both apply and both message — the data converges but
players get duplicate notifications.

### 4. Harden `apply()` first

`gyrinx/content/models/modifier.py` throws on values it cannot parse (`+`, `7_` — both
real in production, 22 errors a week from one row) and misreads a negative intermediate
as a stat-linked value, so a plain stat driven below zero renders `+1` rather than `1`.
Re-resolution leans on `apply()` harder than the old arithmetic did, so fix it first.

### 5. Leave archived gangs out of the messaging

`ListFighter.objects` does not filter archived, so an owner can be told about a gang
they archived long ago. Fix the data, but keep them out of `plan.visible`.

## The situations (unchanged)

| # | Situation | Prod count | Action | Notify |
|---|---|---|---|---|
| 1 | Manual edit — number no advancement produces | 56 | Back-compute; card unchanged | No |
| 2 | Advancement output in the old format | 2 | Clear it; same number | No |
| 3 | Advancement inert — bought, showing nothing | 35 | Switch on; stat gains | **Yes** |
| 4 | Reads the other override store, or stat absent | 14 | Leave — Track C | No |
| 5 | Duplicate improvement, format-disguised | 7 | Clear it; stat drops | **Yes** |
| 6 | Duplicate improvement, partial count | 4 | Clear it; stat drops | **Yes** |
| 7 | Genuine manual edit alongside working advancements | 31 | Nothing | No |
| 8 | Value cannot be parsed | 6 | Nothing | No |
| 9 | Already handled by an earlier run | — | Nothing | No |

## Messages (agreed copy, unchanged)

One per owner covering all their gangs; reductions before improvements; always state
that rating and credits are unchanged; always end with how to correct it themselves.
Escape gang and fighter names — they are user input.

## Verification

1. Unit tests per situation, plus: interrupted run (delete the record, re-run, assert
   the repair survives), a set-mode fighter left alone, and the concurrency guard.
2. Local run against template-forked data; assert only intended stats move.
3. Production dry run, read-only, before applying anything.
4. Full local CI: pytest, ruff, djlint, prettier, migration checks, bandit.

## Not in scope

- The 14 in situation 4 — Track C reconciles the two override stores.
- The 31 in situation 7 — legitimate manual edits.
- Deleting the legacy code and column — needs situations 1–4 at zero.
- A UI hint for an advancement that a `set` swallows.
