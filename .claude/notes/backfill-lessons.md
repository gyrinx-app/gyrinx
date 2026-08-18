# Lessons learned: building good backfill operations

Distilled from the Paths, Specialisation and Skill Tree conversions
and the wargear merge (2026-07 to 2026-08). The short version: **plan
frozen, prove sampled, delete nothing, run as a task, hold one narrow
lock, and verify from outside.**

## Shape

1. **Plan / apply, and the preview is the contract.** The plan reads
   the world and returns frozen, typed steps plus problems; it never
   writes. The apply performs exactly those steps. Whatever the
   preview page says is precisely what happens — no judgement calls at
   apply time.
2. **Refuse in words, in the plan.** Every assumption the apply relies
   on is a plan check that appends a human sentence to `problems`
   ("…is shared — also carried by X"). A conversion that can be
   surprised at apply time was underchecked at plan time. The refusal
   reaches the operator's screen from the view, before anything is
   enqueued.
3. **Delete nothing.** Every hard problem in the early attempts —
   PROTECT errors, fossil wiring, doubled answers — came from retiring
   old rows, which is tidiness, not the switch. Old rows left alone go
   on saying what they said; retire them later, one at a time, by
   hand. The switch is only ever *what the pages read from*.
4. **Never ship a conversion as a migration.** A migration running
   live ORM code inherits a dependency on every column that code will
   ever read, and the pin needed to say so can contradict the recorded
   history of a database that already ran it. Conversions run from the
   maintenance console after deploy, on a schema that is fully
   migrated by construction. (`manage n26_convert <system>` covers
   dev databases.)

## Proving

5. **Capture pages, not intentions.** Before writing, capture what
   every proven gang's pages say (`gang_state`); after writing,
   capture again; refuse and unwind on any difference, and on any
   gang that stops reconciling. "Every page reads the same" is the
   only claim worth making.
6. **Prove a spread, not the estate.** Proving every gang holds the
   transaction for minutes on a live app — worse than incompletely
   proven. Prove a fixed-size sample chosen to hold every *shape* the
   system comes in (the doubled answer, the repeat, the partial, the
   never-answered, the ordinary), one from each kind per round so a
   plentiful kind cannot crowd a rare one out. What breaks is shaped
   by the content, not by one gang's data.
7. **One snapshot for the whole run.** On a live database the proof's
   two readings must see one world, or a player's mid-run purchase
   reads as the conversion's doing and the run refuses for a reason
   nobody can act on. REPEATABLE READ, set on the session before the
   transaction reads anything, restored afterwards, non-masking on
   failure.
8. **The captures don't see the ledger's wording.** History describes
   old events by what their assignments name *now*, so moving an
   assignment between kinds rewrites already-written stories
   silently. Check the history page against a converted assignment;
   pin the story with a same-words test.

## Running

9. **The work runs on the task runner, never in the request** —
   however small it looks. A request that does the work holds a
   worker and a transaction for its whole duration, dies at the
   timeout with no record of how far it got, and shows a spinning tab
   instead of a page to come back to. The audit record is created
   *before* enqueue (status RUNNING), so an in-flight run is visible.
10. **Design for at-least-once delivery.** The task never raises (a
    raised error just goes round again); every ending is written to
    the record. A redelivery must leave no trace while the first copy
    works, and must not be able to unwrite a recorded ending —
    terminal statuses are immutable, and the ending-writer drops late
    writes.
11. **One advisory lock per operation, never shared.** The lock
    fences redeliveries of *one operation's own run*. Shared, one
    conversion enqueued while another runs stands down at the lock
    without writing, acks its message, and strands its record in
    RUNNING forever — with the per-operation running-guard then
    refusing every retry. Postgres frees advisory locks with the
    connection, so a killed run cleans up itself.
12. **Cap the attempts.** Count each start on the record, outside the
    conversion's transaction so the count survives a rollback. A run
    too large to finish gets noticed and says so instead of repeating
    forever at full cost.
13. **The ack deadline equals the request timeout.** A run outliving
    its deadline is redelivered while the first copy works; the second
    copy stands down, answers 200, and acks the message out from under
    the first. Change one, change the other.

## Verifying (before shipping)

14. **Smoke-test on a real database at production's measured volume.**
    Fork the content mirror, read the counts off prodshell rather
    than guessing, build the population — including the weird shapes
    (the gang that answered everything with one thing, the doubled
    click, the archived re-choice) — run the real code path, and time
    it. Tests prove the logic on a handful of rows; the smoke run
    catches the volume, the runtime, and the shapes nobody wrote a
    fixture for. The Specialisation rehearsal failed in production
    for a reason (concurrent writes) that no test database could show.
15. **Verify from outside the run.** After the smoke apply, diff
    *every* affected gang's pages and history stories yourself — not
    just the sample the run proves for itself — instead of trusting
    what the feature checks internally.
16. **Rehearse the failure you fixed.** The snapshot-isolation fix was
    proven by deliberately racing a purchase mid-run with the fix on
    (applies) and off (reproduces the production failure). A fix
    whose failure you can't reproduce isn't known to be a fix.

## Writing it down

17. **The record is the report.** Preview into the record at enqueue,
    report lines into it at DONE, refusal words into `error` at
    FAILED. The detail page should answer "what happened" without
    anyone reading logs.
18. **Retire an operation by keeping its slug registered with no
    view.** The old audit records keep reading as a name; the console
    index stops offering the operation; the code that could be copied
    is gone.
