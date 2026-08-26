# Built-in propagation programme — issue #2165

Built-ins added to a profile (or any carrier) never reach fighters already
hired from it. This plan makes propagation real: adds reach existing uses
within seconds, removals are an explicit author action, and a backfill
repairs history. Long-running programme; executed chunk-by-chunk via
sub-agents. **This file is the shared state** — each chunk updates its
status line when it lands.

Issue: https://github.com/gyrinx-app/gyrinx/issues/2165

## Outcomes

1. A built-in added to a carrier appears on existing uses within a few
   seconds of save (authoring or ingest).
2. Removal-propagation exists as an **explicit, previewed** author action —
   never automatic, and no automatic replacement (not even Collections).
3. Retroactive backfill: existing fighters gain the built-ins they should
   have been hired with.
4. Authors can preview the impact of a built-in change (async UI element,
   full-page fallback) before committing.
5. n26 maintenance gains incremental, resumable backfill machinery — the
   one-transaction backfill shape is retired.

## Decisions (settled — do not relitigate)

| #   | Decision                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| D1  | **Stored propagation**, not computed-only. Built-ins keep assignment identity (counters, picks, descendants, ledger).                                                                                                                                                                                                                                                                                                                                                                             |
| D2  | **Adds propagate automatically** after commit. **Removals never propagate automatically** — fixing a wrong equipment list is an explicit remove-propagation the author triggers, plus the add propagating. No automatic replace semantics anywhere in propagation (ingest's `REPLACED_BUILT_INS` still governs *library* content only).                                                                                                                                                           |
| D3  | **Matching is by provenance only.** A built-in member is satisfied iff a stored assignment materialised *from that member for that carrier* exists (provenance fields; legacy rows matched by `reason=DEFAULT` + `caused_by` during backfill tagging). Independent player-added matches and modifier-computed grants do **not** block materialisation; visible duplicates are accepted. ⚠ *Supersedes* the earlier rule that an independent matching rule/subtype/counter satisfies the built-in. |
| D4  | An **archived** materialised assignment (owner sold/removed it) still counts as satisfied — never re-grant what an owner parted with.                                                                                                                                                                                                                                                                                                                                                             |
| D5  | **All default-member deletion paths become archival** — authoring `remove_default_member` *and* ingest's superseded-Collection delete. Provenance FKs must never dangle.                                                                                                                                                                                                                                                                                                                          |
| D6  | `_granted_rows` / `rechoose` move onto provenance **before** any backfill runs (the newest-first heuristic breaks once built-ins are appended late).                                                                                                                                                                                                                                                                                                                                              |
| D7  | Backfills are **chunked, resumable, per-gang-committed**. The n26 maintenance "one transaction, all-or-nothing" shape is deliberately retired for this and future backfills.                                                                                                                                                                                                                                                                                                                      |
| D8  | The `buy()` materialisation asymmetry (kinds exposing built-ins that buying never materialises, `operations.py:1154-1185`) is **out of scope** — file as its own issue.                                                                                                                                                                                                                                                                                                                           |
| D9  | Owner `removes=True` assignments never satisfy a member and are preserved: the built-in materialises, the removal keeps suppressing it.                                                                                                                                                                                                                                                                                                                                                           |
| D10 | Preview is informative, not an authorisation token; the POST recomputes against current data. One shared planner powers authoring preview, ingest preview, and removal preview.                                                                                                                                                                                                                                                                                                                   |
| D11 | *(settled 2026-08-23)* **Withdrawing an option whose set has materialised copies refuses loudly**, naming why — never the current swallow-the-`ProtectedError`-and-orphan-the-set behaviour. Author-side policing is fine: a refusal stops the bad state existing, where engineering around it never ends. Built in C6. |
| D12 | *(settled 2026-08-23)* **A removal that would leave a priced option set empty warns or refuses** — a player must never pay for a set that grants nothing. Built in C6 (or C5's preview if it lands first). |
| D13 | *(settled 2026-08-23)* **An ammo built-in names its gun member.** `DefaultAssignment` gains a nullable self-reference: a weapon-profile member whose set holds a matching weapon member MUST name which one it rides — authoring validates, the form asks "for which gun?", ingest auto-links and errors on ambiguity instead of guessing. Null keeps a real meaning: "ammo for whatever live gun of this type the carrier holds" (the cross-set case, e.g. an option set arming a built-in gun). Reconcile resolution becomes a receipt lookup; the FIFO queue, occupied-gun set, and type-derived `dependent_members` are deleted. The flat-sibling shape is a launch-era mistake killed at authorship (the D11/D12 principle). Built as chunk **C2b**, after #2286 merges, before C4. |
| D14 | *(settled 2026-08-25)* **Propagation history: dedicated event kind, empty actor, sentence anchored on "comes with", one folded line per gang per pass.** A propagated grant is a new `LedgerEvent.Kind` (identifier settled in the C4 plan — candidates `CAUGHT_UP` / `KIT_UPDATED`) whose sentence names the source in the equip screen's own words: *"Bruta gained Frag Grenades — now part of what a Stimmer comes with"*. No synthetic actor — the `Act.actor` stays empty (the documented "nobody in particular" case); never invent a named speaker like "Gyrinx". All of one pass's events for a gang share a batch mark so several models fold into one line with sub-items (*"what a Stimmer comes with changed — Bruta and Skarr each gained Frag Grenades"*). C6's explicit removal takes the mirror wording ("no longer part of what a Stimmer comes with"); C7's backfill reuses the kind and may add a catch-up clause, decided inside C7. Rejected: bare `GRANTED` reuse (indistinguishable from modifier gains, answers "why did this appear?" with silence). |

## Open questions (resolve inside the relevant chunk, with the maintainer)

- ~~**History wording** for actor-less propagation events~~ — settled as
  **D14** (2026-08-25): dedicated kind, empty actor, "comes with" sentence,
  folded per gang per pass. Only the kind's identifier remains, settled in
  the C4 plan.
- **Paid descendants on explicit removal** — a bought ammo type riding a
  built-in gun. Preview must surface them; first version likely skips those
  carriers with a report rather than stranding or deleting paid things.
- Whether interim Collection duplicates (add landed, removal not yet
  triggered) get a `Note` on the equip screen ("inform, never police").

## Code map (verified 2026-08-22 — re-verify line numbers before editing)

**Materialisation (the copy loop):**
- `n26/core/operations.py:832` — `_materialise_defaults(carrier, taken, kinds, gang, built_ins)`; used by `hire` (:599, call at :641), `found`, `rechoose` (:711 → :765, `built_ins=False`), `add_legacy_profile` (:1100, `kinds=` narrowing).
- Special cases inside: `Weapon` → `_grant_free_profiles`; `WeaponProfile` members deferred as ammo, attached to the gun's assignment; `default_pickable_id` → `_choose_for_slot`; `counter_id` → `CounterValue.objects.create(assignment=…, value=member.amount)` (:906-913). **A naive assign() leaves counters without opening values.**
- Preview twin (no writes): `n26/core/card.py:770` — hire preview iterates `(profile.built_ins, *taken)`. Keep in step with the reconciler.
- `_granted_rows` `operations.py:794` — reverse-maps set→rows by `reason=DEFAULT` + `caused_by` + **newest-first**; docstring asserts built-ins materialise first. This is what D6 replaces.
- `operation(gang, actor=None)` `operations.py:1454` — atomic + `_hold(gang)` (select_for_update, :1435) + `settle()` (:1344, repins + `NotEnoughCredits` unwind). Never take a second lock around it.

**Library side:**
- `n26/library/models/defaults.py:75,106` — `DefaultAssignmentSet`, `DefaultAssignment` (kinds: `DEFAULT_ASSIGNABLE_FIELDS` :61 — weapon, weapon_profile, wargear, subtype, skill, rule, hidden, collection, counter, slot). `DefaultAssignment` inherits `Content` → already has `archived`.
- `n26/library/models/assignable.py:167` — `Assignable.built_ins` FK (PROTECT, nullable); `takes_built_ins` flag :212.
- Authoring verbs: `n26/library/authoring.py:967` `add_built_in`, `:1023` `add_default_member`, `:1056` `remove_default_member` (currently a **hard delete**, cascades `dependent_members`).
- Ingest: `n26/library/ingest.py:2584` `REPLACED_BUILT_INS = ("Collection",)`; `:2592` `_superseded_built_ins`; `:2614` `_built_ins_difference` (the existing preview diff — reuse for the shared planner); `:3011` `_update_defaultassignmentset` (**hard-deletes** superseded members; adds via `add_default_member`); profile `built_ins` set on create only (:3202).

**Core side:**
- `n26/core/models/assignment.py:41,64,68` — `ASSIGNABLE_FIELDS` (21 kinds), `HOST_FIELDS`, `Assignment`. Roots derived in `save()` — never bulk-write assignments. Membership `miniature_root` is set by hand in `hire`.
- `Reason.DEFAULT`: `n26/core/models/ledger.py:28` — the field is on **`LedgerEntry`**, so assignment lookups go via `ledger_entry__reason`. `ChosenProfileOption` / `CounterValue`: `n26/core/models/settings.py:53,82`.
- Equip tabs: `n26/core/access.py:47,91` — a tab exists only because a live `Assignment` with `collection_id` is on the card (`access.py:119`); `n26/core/views/equip.py:410-442,209`.

**Maintenance + tasks:**
- `n26/maintenance.py` — Operation slugs (:82, permanent), `LOCK_KEYS` (:114), `_run_recorded` (:216), `MAX_ATTEMPTS = 2` (:74), deletion-view shape (:519, preview-on-GET / enqueue-on-POST), registration (:598-694), `task_routes` (:697). Module docstring (:26-34) states the one-transaction rule D7 retires.
- `gyrinx/tasks/backend.py:32-36` — Pub/Sub publish is fire-and-forget; **loss possible** → durable pending row + scheduled sweep required. Delivery is at-least-once (see `gyrinx/tasks/CLAUDE.md`); business idempotency is the task's job. Chunked re-enqueue precedent: `n23/core/tasks.py`; chaos testing via the `task_queue` fixture (manual mode).

## Architecture

- **Provenance on `Assignment`**: `materialised_from` → `"library.DefaultAssignment"` (PROTECT — safe once D5 makes members archival-only) and `materialised_for` → the carrier assignment (`"core.Assignment"`). Both nullable forever for non-default rows. Partial unique constraint on `(materialised_from, materialised_for)` where `archived=False`; satisfaction checks (D3/D4) consider archived rows too.
- **Pending reconciliation row** lives in `n26/core` (core may name library models by label; library writes it via function-level import — boundary rules in `n26/CLAUDE.md`). Keyed by `DefaultAssignmentSet`; written in the authoring/ingest transaction; task enqueued `transaction.on_commit()`; coalesced per set; recovery sweep on a `TaskRoute` schedule.
- **Reconciliation engine**: `_materialise_defaults` refactored into "create what provenance says is missing", shared verbatim by acquisition, propagation, and backfill. Resolves carriers via `Assignable.built_ins` holders *and* acquisitions whose `ChosenProfileOption` names the set. Per gang: one `operation(gang, actor=None)`, bounded batches, keyset pagination.
- **Shared planner** `plan_built_in_change()` — read-only, powers: authoring async preview fragment (staff-only endpoint, `aria-live`, full-page POST fallback per the URL-state rule), the ingest preview's "N existing uses will not see this" line (extending `_built_ins_difference`), and the removal preview.
- **Explicit removal-propagation**: from the authoring UI, previewed, per member; archives the materialised assignments found by provenance (cause-chain cascade takes free grants); paid descendants surfaced per the open question.
- **Chunked maintenance runner**: per-gang batches committing independently, progress written onto the `Backfill` record, resumable after interruption, cooperative cancel, advisory-lock single-flight kept.

## Chunks

Each chunk: own branch + PR, run by a sub-agent with **only this file plus
the chunk brief** as context. Feature-planner first for anything
non-trivial. Update the status line here on merge.

**C0 — Measure production fan-out.** `manage prodshell` (read-only):
gangs, memberships per profile, members per built-ins set, worst-case
holders of one set. Record numbers here; they size C4 batches and decide
how much C3 machinery is genuinely needed now vs. built minimal.
*Status: DONE 2026-08-22.* Numbers (counts and shapes only):

- **Estate:** 1,830 gangs (1,389 live), 9,581 miniatures, 73,537 live
  assignments (max 157 / mean 40 per gang). 48,096 live
  `reason=DEFAULT` assignments. ⚠ `reason` lives on **`LedgerEntry`**,
  not `Assignment` — query via `ledger_entry__reason`. `Miniature` has
  no `archived` field.
- **Library:** 261 Profiles, all with `built_ins`; 487 sets, 1,737
  members (max 13/set, mean 3.6). By kind: subtype 505, weapon 300,
  rule 253, counter 236, skill 208, collection 98, wargear 66,
  hidden 61, slot 6, weapon_profile 4. **Zero archived members** — C1
  starts clean; any archived member found later is unambiguously
  post-C1.
- **Fan-out:** worst fighter entry = 386 live hires across 134 gangs
  (~3 hires/gang, so per-gang batching genuinely coalesces). **The true
  worst case is a gang type's founding set: 203 distinct gangs** (then
  173, 163, 159, 127). 1,596 gangs hold ≥1 hired profile.
- **Shared sets: none.** 284 holders → 284 distinct sets (Profile 261,
  GangType 17, Weapon 2, one each Wargear/Subtype/LastingEffect/
  Affiliation). Keep holder resolution general; build no fan-in
  machinery.
- **Options:** 786 `ChosenProfileOption` rows over 87 sets, max 96 per
  set — never the worst case.
- **C7 volume:** upper bound ~36,600 (use × member) pairs vs 48,096
  existing DEFAULT assignments — the backfill's dominant work is
  **tagging existing assignments with provenance**, not creating.
  Re-measure the genuinely-missing fraction after C1 lands, before C7
  runs.
- **Sizing verdict:** C3 = sequential per-gang loop, committing each
  gang, with resumability + progress + cancel; no parallelism, sharding
  or worker pools. Estate-wide pass ≈ 37 chunks at 50 gangs/task. A
  single set change is low hundreds of transactions. Re-runnable
  queries in the appendix below.

**C1 — Archival + provenance foundation.** Convert *every*
default-member deletion to archival (authoring `remove_default_member`
incl. `dependent_members`; ingest `_update_defaultassignmentset`). Filter
archived members out of every member read (`_materialise_defaults`,
`card.py:770` preview, `add_default_member` position count, ingest
`find_existing`, authoring pages). Add nullable provenance fields +
partial unique constraint. Move `_granted_rows`/`rechoose` to
provenance-first with legacy `reason=DEFAULT` fallback (fallback removed
in C8). No behaviour change for players. Regression test: rechoose still
unwinds correctly for provenance-tagged and legacy rows.
*Status: MERGED 2026-08-23 via PR
[#2276](https://github.com/gyrinx-app/gyrinx/pull/2276) (squash; the
migration landed as `n26.0021`).
Browser-tested through the authoring UI 2026-08-22: remove/re-add,
ammo cascade, collection tab, rechoose, provenance spot-check all pass,
zero server errors. The remove page states the archival semantics in
its own words. Caveats: the dev DB held no pre-C1 assignments, so
"legacy rows have null provenance" is unverified until C7's prod
preview; the authoring ammo picker omits the qualifier for same-named
weapon profiles (pre-existing gap, not C1 — authors cannot tell twins
apart).
Review round (commit `1b983ff3`): the rechoose fallback now counts every
tagged copy (archived included) and reads live members only, so it never
seizes a look-alike; a membership nothing materialised from is deleted,
not archived (archival is only for members provenance names — ingest
retires through the same verb); provenance is constrained to a pair or
nothing; positions come from the highest ever placed.*
Findings later chunks must honour:

- **D4/satisfaction checks must NOT filter on member archived state**
  when following provenance — an archived member's copies still resolve
  through the FK, and `_granted_rows` relies on that for unwinds.
- **Ammo copies match by the provenance pair, never by `caused_by`** —
  their cause is the gun; `materialised_for` is the carrier.
- **Option sets referenced by provenance are permanent**: member
  deletion cascading from a set delete raises `ProtectedError`, which
  `stop_offering`'s existing except-branch treats as "something holds
  it". C6's removal-propagation should expect this.
- `ChosenProfileOption`'s `(assignment, default_set)` unique constraint
  is what makes one-live-copy-per-member-per-carrier safe on hire.
- Two member reads filter archived in **Python** to keep prefetches
  warm (`card.py` hire preview, `_describe_profile`) — C2/C5 readers
  over prefetched members should do the same.
- After archival, `add_default_member` can reuse a live position number
  (live count vs surviving higher positions) — cosmetic ordering ties;
  matters only if C5's preview sorts by position.
- `materialised_from` is PROTECT, `materialised_for` is `"self"`/CASCADE
  (the plan's `"core.Assignment"` label was wrong — app label is `n26`).
  Migration: `n26.0018_a_grant_names_the_member_it_came_from`.

**C2 — Reconciliation engine.** Refactor materialisation into
idempotent desired-state reconcile (D3/D4/D9 matching). Covers weapons +
free profiles, ammo→correct gun, slots + starting picks (existing
answered slots untouched; new slot-with-default materialises settled),
counters + opening `CounterValue`, stored effects (exactly once under
redelivery), gang-hosted founding sets, stash-hosted, legacy-profile
`kinds=` narrowing. Sandbox tests: run-twice-creates-nothing; independent
matching rule does NOT block (duplicate accepted — D3); archived copy
blocks (D4); `removes=True` preserved (D9); every case ends
`assert_reconciled(gang)` **after `refresh_from_db`** (stale-pin gotcha).
*Status: MERGED 2026-08-23 via PR
[#2286](https://github.com/gyrinx-app/gyrinx/pull/2286) (squash;
migration landed as `n26.0022`). Three-lens review (no correctness
findings; four quality fixes), CI green, browser smoke-tested: hire /
rechoose-round-trip / buy-with-options / founding all pass, zero server
errors, provenance shapes identical to a C1-era hire. The smoke test
also surfaced pre-existing bug
[#2299](https://github.com/gyrinx-app/gyrinx/issues/2299) (Enter in the
equip search box buys the first item — not C2's).
Both oracle-driven deviations (below) APPROVED 2026-08-23:
D4 guards *unattended* re-grants, an explicit re-take is an
acquisition; ammo fallback stays exactly as it was, no extra tiers.*
Architecture settled (chosen over a minimal in-place refactor): a
**plan/apply split**. Pure `plan_defaults(carrier)` + `ReconcileOutcome`
in new `n26/core/builtins.py` (satisfaction predicate `copies_of` lives
there — one definition for reconcile, `_granted_rows`, and C6);
the `taken` parameter is eliminated — acquisitions write their
`ChosenProfileOption` rows first, then call one carrier-only
`Operation.reconcile_defaults`; `_materialise_defaults` is deleted and
its six call sites rewired. C5's preview calls `plan_defaults` directly.
Sub-decisions from design review: orphan ammo is SKIPPED on reconcile
(recorded in the outcome's `skipped`), raising only at genuine
acquisition; the twin-gun collision is fixed by member-keyed FIFO gun
resolution; migration `n26.0022` adds CheckConstraint
`removes=False OR materialised_from IS NULL` (D9 made structural);
`rechoose` stays strict deliberately; the per-member satisfaction query
cost feeds C3's batch sizing. Also noted: `buy()` DOES materialise
built-ins for option-capable kinds — D8's asymmetry is only the kinds
without `resolve_selection`.
Two implementation deviations, forced by the existing suites (the
stated oracle), approved by the maintainer:
(1) `plan_defaults`/`reconcile_defaults` take `fresh=` — sets being
taken right now, judged by LIVE copies only. Without it, rechoosing
back to a formerly-held set finds its refund-archived copies
"satisfied" (D4) and the player pays the delta for nothing; D4 stands
unchanged everywhere else.
(2) The ammo fallback keeps its old shape (any live same-host
assignment of the weapon, newest first, NO provenance filter): with
`built_ins=False` the plan cannot see the built-in gun, so the
provenance-null fallback specified in review breaks
`test_an_arriving_sets_ammo_lands_under_the_standing_gun` and the
cross-carrier buy-ammo-for-a-hired-gun case.
For C4/C5/C6: bare propagation reconciles must pass `strict=False`
(orphan ammo lands in `outcome.skipped`, never raises) and never pass
`fresh`; C5's preview calls `plan_defaults(carrier)` directly; the
per-member satisfaction check is one EXISTS query (mean 3.6
members/set), so a per-gang batch is tens of cheap queries.

**C2b — An ammo built-in names its gun (D13).** Nullable self-FK on
`DefaultAssignment`; authoring validation + a "for which gun?" picker
(fixing the qualifier-less ammo picker from C1's findings alongside);
ingest auto-links by type, erroring on ambiguity; data migration
back-links existing members (4 in prod per C0 — verify by hand);
engine simplification: ammo resolution becomes a receipt lookup on the
named member, the FIFO queue and occupied-gun set are deleted,
`dependent_members` reads the real relation instead of type-matching.
Null-FK members keep today's type fallback (the cross-set semantics).
UX agreed with the maintainer 2026-08-23: the "Comes with" listing
nests profile members under their gun (the card's own grammar); each
weapon member row gets an **"Add profile"** link (never "Add ammo" — a
weapon's extra lines are not always ammunition) to a page scoped to
that gun listing its priced profiles only, free ones arriving
automatically; the generic built-ins form stops offering the
weapon-profile kind (never offer the act that would be refused); option
sets keep a two-step weapon→profile door creating an unanchored member
with its meaning stated on the page.
*Status: MERGED 2026-08-23 via PR
[#2301](https://github.com/gyrinx-app/gyrinx/pull/2301) (squash;
migrations `library.0065`/`0066` — the back-link migration anchors
NOTHING in production: all 4 legacy profile members are cross-set, so
the machinery is purely for new authorship; ambiguity leaves null, an
author anchors in the UI). Review-hardened (two-lens + CodeRabbit:
create_default_set staged atomically weapons-first; position allocated
by the verb; archived anchors refused in clean; the "twin sheet cell
crashes ingest" finding was REFUTED by experiment — sheets cannot plan
a weapon-profile member, pinned by test) and browser-verified including
the pixel-level indent fix (`pl-6!` — the table component's td padding
must lose). CodeQL's redirect warning on `set_profiles` is a false
positive: path-relative, pk re-read from a validated object.*

**C3 — Chunked maintenance runner.** Generic per-gang resumable batch
support in `n26/maintenance.py` (D7): batches commit independently,
progress + failures on the `Backfill` record, resume after interruption,
cancel between batches. Sized by C0's numbers — build what the volume
demands, not a framework. Independent of C1/C2; must land before C7.
*Status: MERGED 2026-08-26 via PR
[#2322](https://github.com/gyrinx-app/gyrinx/pull/2322). As built:
`run_batched(backfill_id, operation=, what=, items=, do_one=, again=)`
+ the existing `_claim` now serving both shapes (every recorded batch
resets the attempt count — no separate batched claim). Cursor over a
total pk order; batches fetched by keyset (`pk__gt`), never
materialised; `done` counts successes; failures struck off when a later
walk settles the row; total pinned on the first attempt (items must be
a STABLE queryset, never self-filtering); cancel checked before each
batch and at each progress write; hand-back enqueued only after the
advisory lock is released (race caught in review: a summoned delivery
finding the lock held would stand down, ack, and strand the record
RUNNING — maintenance has NO sweep); the hand-back enqueue is the one
deliberate raise (redelivery re-summons). BATCH_BUDGET=4min to fit the
default 300s ack deadline (invariant: budget + one batch < route
deadline). For C7: pass `operation` registered in LOCK_KEYS; `do_one`
must be idempotent and own its transaction (operation(gang) is);
refusals-channel/report plumbing deliberately absent — decide in C7 if
needed; lock contention across two live deliveries is the one path no
test can exercise (single-connection suites can't contend) — watch the
console during C7's first prod run. The runner's first consumer is
`audit_reconcile` (PR #2326): a read-only per-gang `assert_reconciled`
walk from the console — run it in prod BEFORE C7 as the runner's
rehearsal (duplicate-delivery contention is safely pokeable because the
work writes nothing) and as the pre-backfill health check; any drifted
gang it names must be understood before C7 writes anything.*

**C4 — Live add-propagation.** Pending row + `on_commit` enqueue from
`add_built_in`/`add_default_member`/ingest perform, coalesced per set.
Task resolves holders + `ChosenProfileOption` selectors, reconciles per
gang via C2. Scheduled recovery sweep. Chaos tests via `task_queue`:
rollback enqueues nothing; duplicate/concurrent delivery materialises
once; drop leaves pending work the sweep drains; shared sets reach every
holder; option-set changes reach only selectors. End-to-end: authoring
save → existing card shows the built-in through the dev worker within
seconds. Decide history wording here (open question) before enabling.
*Design ruling (maintainer, 2026-08-25): the pending row is a
`gyrinx.state_machine.StateMachine` model, not bespoke status columns —
the pattern `TaskExecution` and `Battle` already use.* What that buys:
the claim race is `transition_to`'s row-locked validation (a duplicate
delivery's PENDING → RUNNING loses with `InvalidStateTransition` and
stands down — no hand-rolled advisory lock for the claim; reconcile
idempotency stays underneath); the sweep is an indexed status query plus
timestamped transition history; outcomes (gangs reconciled, skips) land
in transition `metadata`. *Refined 2026-08-25 (maintainer rejected the
RUNNING → PENDING loop-back as odd):* rows are single-shot
and the graph strictly forward, like Battle's: PENDING → RUNNING →
DONE | FAILED, no backward edge. Retry
after failure = the sweep files a fresh PENDING row; FAILED is terminal,
a record of the attempt. Sound because a row never encodes *which*
change — the task reconciles from current library state.
*Re-refined 2026-08-25 during the tour — the maintainer caught a real
TOCTOU in PENDING-row reuse and it is now BANNED:* the original design
coalesced via `get_or_create` under a partial unique (one PENDING per
set), but an authoring transaction could find and attach to the PENDING
row while uncommitted, the worker could then claim that row and read
the library before the author committed, and the edit would silently
never propagate (its post-commit publish stands down at the claim; the
row ends DONE). **Filing is append-only: every edit INSERTS its own
row, no reuse, no partial unique constraint.** A row's message
publishes only after its own edit commits, so the pass that claims it
always reads a library including the change that filed it. Redundant
passes are no-ops by idempotency (fine at C0's measured scale).
**Naming (maintainer, during the tour): the model is
`BuiltInPropagationTask`** — it must say built-ins and say it tracks
propagation of changes to them. The words "obligation" and "debt" are
BANNED from the branch and from future chunks' code and prose — say
"filed task", "run", "not yet applied". Verbs: `file_propagation_task`,
task `sweep_built_in_propagations` (renamed pre-ship because the task
name becomes the Cloud Scheduler job name).
The sweep is a `TaskRoute(schedule="...")` declaration —
the framework provisions a Cloud Scheduler job per scheduled task
(verified 2026-08-25: `gyrinx/tasks/route.py` + `provisioning.py`) —
but NOTE: no production task uses `schedule=` yet, so the sweep is the
feature's first live user: verify the Scheduler job exists and fires
after deploy (provisioning in `AppConfig.ready()` has bitten before),
and know the local backend never fires schedules — dev and chaos tests
invoke the sweep task directly, the cron leg is proven only deployed.
The row is NOT a `TaskExecution`:
one tracks a delivery attempt, the other the durable record that
survives a lost publish. Model lives in `n26/core`, importing
`gyrinx.state_machine` as the tasks framework does.
*Status: MERGED 2026-08-26 via PR
[#2305](https://github.com/gyrinx-app/gyrinx/pull/2305) (squash;
migration `n26.0029`). As built: model `BuiltInPropagationTask`
(`n26/core/models/built_in_propagation.py`), verbs in
`n26/core/propagation.py` (`file_propagation_task`,
`propagate_built_ins`, `sweep_built_in_propagations` at `*/5`,
thresholds 2min/15min/3-failure cap), one filing hook in
`add_default_member` (now `@transaction.atomic` so member + filing
commit together) covering form/`add_built_in`/ingest. D14 shipped as
`LedgerEvent.Kind.CAUGHT_UP` with per-source folding in `history.py`.
**Ships SHUT behind the `built-in-propagation` FeatureFlag** — worker
and sweep stand down, filing never does, so shut defers rather than
loses; `gyrinx.site.flags` gained `switched_on(slug)` for account-less
callers, re-exported via `n26/flags.py`. Review-hardened (two-lens +
bots + maintainer review), chaos-suite of 16 tests, browser-verified
twice (pre- and post-redesign demo gang "C4 Demo Crew" in the
worktree dev DB, flag opened there).
**Go-live owed after deploy:** verify the Cloud Scheduler job for
`sweep_built_in_propagations` exists and fires (first `schedule=` task
in production), then create + open the `built-in-propagation` flag in
the admin. Anything authored before the flag opens is repaired by the
backlog drain (rows filed while shut) — and anything authored before
C4 deployed at all remains C7's job.*

**C5 — Preview.** `plan_built_in_change()` shared planner; authoring
async fragment + non-JS fallback; ingest preview line ("N existing uses
were hired from this and will not see this change" becomes "…will gain
this within seconds" once C4 is live). Counts in SQL, bounded samples,
no writes, no tasks.
*Status: MERGED 2026-08-26 via PR
[#2316](https://github.com/gyrinx-app/gyrinx/pull/2316). As built:
`Reach` + `reach_of()` in `n26/core/propagation.py`, aggregating over
the SAME `_carriers_of` queryset the C4 pass reconciles (refactored so
preview and pass cannot disagree); flag-aware sentences ("…within
seconds" open / "…when built-in propagation is switched on" shut /
"Held by no gang yet…" zero) server-rendered on the authoring
profile page, built_in_profiles, set_profiles, option_add and the
ingest preview line. No async fragment, no migration. The removal
preview (C6) should call `reach_of` too, per D10.
NOTE for future chunks (maintainer, forcefully): size the process to
the chunk — C5-sized work gets ONE agent or none, orchestrator's own
review, no separate smoke agent.*

**C6 — Explicit removal-propagation.** Author-triggered, previewed,
per member (D2): archive provenance-matched assignments through
`operation(...)`, cause-chain takes free grants, paid descendants
surfaced/skipped per the resolved open question. This is the fix path
for a wrongly-added equipment list. Also builds the two author-side
refusals: D11 (`stop_offering` refuses while materialised copies stand,
instead of orphaning the set) and D12 (emptying a priced set
warns/refuses). Verify: equip tabs drop the removed Collection;
sold/archived copies untouched; rerun is a no-op; both refusals speak
in sentences an author can act on.
*Status: not started.*

**C7 — Retroactive backfill.** Maintenance operation on C3's runner:
tag unambiguous legacy `reason=DEFAULT` rows with provenance, reconcile
missing members via C2, per-gang outcomes recorded, rerun reports zero.
Before prod: fork content mirror at measured volume, time it, and verify
from outside — compare affected cards/assignment counts/ratings/credits
independently before and after.
*Status: not started.*

**C8 — Tighten + acceptance.** Remove the legacy `_granted_rows`
fallback; retire `_something_materialised`'s loose-evidence clause and
sweep archived members no copy references (the interim evidence
deliberately over-archives — a hidden row is recoverable, a deleted
anchor is not); consider stricter provenance constraints; acceptance pass:
add-a-rule reaches an existing model in seconds; redelivery adds
nothing; backfill twice → second run empty; full `pytest n26`, fmt,
migration checks, query-budget tests unchanged.
*Status: not started.*

**Separate issue (D8):** the `buy()` built-ins asymmetry.

## Sequencing

C0 → C1 → C2 → C2b → C4 → C5 → C6 → C7 → C8, with C3 in parallel any time
before C7. Preview (C5) ships only once C4's behaviour exists (never
promise propagation that doesn't happen). Incremental throughout:
built-in authoring never pauses; C4's backfill-from-current-state design
means anything added mid-rollout is repaired by C7.

## Sub-agent working notes

- One implementation agent at a time on this programme (worktree
  isolation is unreliable when the session is already in a worktree;
  concurrent agents collide on the test DB — give any parallel agent its
  own `DB_NAME`).
- n26 conventions bind: no "cost", no calling an assignment a "row",
  comments state constraints only (no tickets/people/history),
  British spelling, tests as narrative classes under `n26/tests/sandbox/`
  for gang-shaped scenarios, fixtures from `n26/tests/fixtures.py` only.
- **Comments earn their place.** Review every comment before committing.
  A comment states a constraint, an invariant, or a consequence the code
  cannot show — in plain words, for a reader who does not know the game
  and has never seen any earlier version of the code. That one test
  rejects the rest: nothing that restates the line below it, no
  changelog narration ("used to", "now we", "as before"), no people,
  tickets, or review references, no disguised TODOs ("for now"), and no
  matching a file's comment *volume* — match its usefulness. One or two
  sentences; reasoning that needs a paragraph belongs in the module
  docstring. When in doubt, delete it.
- **Reports read cold.** A PR description, chunk status update, or
  hand-back must work for a reader with none of the writing session's
  context. Lead with the outcome — the first sentence says what happened
  or what was found. Re-anchor in one clause ("chunk C2 of the built-in
  propagation programme: the reconciliation engine") before any detail.
  Plain words; any name the work itself introduced gets a few-word
  definition at first use; never lean on shorthand coined mid-session
  (test-group codes, agent labels, "the fix from earlier"). If a
  sentence needs the conversation to be understood, restate the fact in
  place rather than referencing where it was established. Brevity comes
  from selecting what matters, not from compressing prose — drop details
  that change nothing for the reader, and write what remains in full
  sentences.
- Never write `Assignment`/`LedgerEntry`/`LedgerEvent` outside
  `operation(...)`; never bulk-write assignments (roots derive in
  `save()`); readers skip `removes=True`.

## Appendix — C0 measurement queries

Single expressions for `echo '…' | manage prodshell` (IPython; one
expression per query, read results off the `In [N]:` lines). Re-run
before C7 to size the genuinely-missing fraction once provenance exists.

```python
from n26.core.models import Gang, Miniature, Assignment
from n26.core.models.ledger import Reason
from n26.core.models.settings import ChosenProfileOption
from n26.library.models import Profile, GangType
from n26.library.models.defaults import DefaultAssignmentSet, DefaultAssignment, DEFAULT_ASSIGNABLE_FIELDS
from django.db.models import Count, Avg, Max

# Totals
Gang.objects.count(); Gang.objects.filter(archived=True).count()
Assignment.objects.filter(archived=False).count()
Assignment.objects.filter(archived=False, ledger_entry__reason=Reason.DEFAULT).count()
Assignment.objects.filter(archived=False, profile__isnull=False).count()

# Library shape
DefaultAssignmentSet.objects.annotate(n=Count("members")).aggregate(Max("n"), Avg("n"))
{f: DefaultAssignment.objects.filter(**{f + "__isnull": False}).count() for f in DEFAULT_ASSIGNABLE_FIELDS}
DefaultAssignment.objects.filter(archived=True).count()

# Fan-out
per = Assignment.objects.filter(archived=False, profile__isnull=False).values("profile").annotate(n=Count("id"))
per.count(); per.aggregate(Max("n"), Avg("n"))
[(r["n"], Assignment.objects.filter(archived=False, profile_id=r["profile"]).values("gang_root").distinct().count()) for r in per.order_by("-n")[:5]]
Assignment.objects.filter(archived=False).values("gang_root").annotate(n=Count("id")).aggregate(Max("n"), Avg("n"))
Assignment.objects.filter(archived=False, gang_type__isnull=False).values("gang_type").annotate(n=Count("gang_root", distinct=True)).order_by("-n")[:5]

# Shared sets (holders by assignable model)
from django.apps import apps; from n26.library.models.assignable import Assignable; from collections import Counter
ms = [m for m in apps.get_app_config("library").get_models() if issubclass(m, Assignable)]
ids = [i for m in ms for i in m.objects.filter(built_ins__isnull=False).values_list("built_ins_id", flat=True)]
c = Counter(ids); (len(ids), len(c), max(c.values()))

# Options
ChosenProfileOption.objects.count(); ChosenProfileOption.objects.values("default_set").annotate(n=Count("id")).order_by("-n").first()

# Backfill upper bound (profile side; gang-type side analogous via GangType)
prof = list(Profile.objects.filter(built_ins__isnull=False).values_list("id", "built_ins_id"))
memb = dict(Assignment.objects.filter(archived=False, profile__isnull=False).values_list("profile").annotate(n=Count("id")).values_list("profile", "n"))
setn = dict(DefaultAssignmentSet.objects.annotate(n=Count("members")).values_list("id", "n"))
sum(memb.get(p, 0) * setn.get(s, 0) for p, s in prof)
```
