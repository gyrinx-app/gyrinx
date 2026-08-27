# Converting Affiliation onto slots and picks — the plan

How the three leftover Affiliation systems move. Why they should, and
the split, live in
[`affiliation-conversion-eval.md`](affiliation-conversion-eval.md).
This file is the how: the runner, the window, each system's apply,
and the PR sequence.

Measured from production on 2026-08-27, read-only. n23 is out of
scope. Nothing here reads or writes it.

The old conversions ran `plan()` / `apply()` in **one transaction**
over a spread of gangs, and #2287 deleted that engine. What we have
now, proven in production by `audit_reconcile`, is `run_batched`
(`n26/maintenance.py`): a stable queryset of pks, `do_one(pk)` per
row on its own commit, a cursor on the `Backfill` record, a four-minute
budget, re-enqueue via `again()`, failures recorded and skipped.
Affiliation is too large for one transaction (359 gangs hold a live
pick) and is the first conversion that can use that runner for the
player rewrite. The library swap stays one-shot — it is pack-wide and
small.

## Decisions locked

| | |
|---|---|
| Three slot types | Affiliation, Variant, Chaos God. Clan House is a fourth type, chained off the Clan House pickable. Not one Affiliation type covering all three systems. |
| Order | Machinery → Outcast + Clan House → Chaos God (both doors) → Variants (including None) → cleanup later. |
| "None" | Archive the 187 live and 17 archived picks. Variant slot `min_picks=0`. An open optional Variant and a picked None must capture equal under a **conversion-local** comparator (`chosen` in `{"None", ""}` for that question). Preview names every gang whose stored answer is cleared. |
| Aranthian Gangers | Keep the modifier as authored. Do not fix it inside the rewrite. |
| Repeats | All four types refuse them. |
| Modifiers | **Share, do not move**, until cleanup. The affiliation row and the new pickable both carry the same `Modifier` rows (the M2M already allows this). Moving them at library time would strip payload from every gang not yet rewritten. |
| Kind column | Stays until cleanup. Do not drop `Affiliation`, `OFFERABLE_KINDS`, or the Assignment column in any rewrite PR. |
| Writes | Assignment updates are the sanctioned conversion exception (`n26/core/CLAUDE.md`): no `operation()`, no money, no ledger events. |
| Unit of work | A **gang**, not a pick. Chains (Clan House + house, Chaos Corrupted + god) live on one gang and must rewrite together. |

## Why the old engine cannot be replayed

The deleted runner (`n26/library/conversion/base.py` at `000f2022^`)
did library create, carrier swap, and pick rewrite in **one
`REPEATABLE READ` transaction**, captured a **spread**, and refused
and unwound the whole run on any page diff. That cannot hold 359
gangs. It also never showed the window below, because swap and
rewrite committed together.

`run_batched` is the opposite promise: each gang commits alone, the
cursor survives an interruption, a failing gang is recorded and
stepped past, an operator can cancel between batches. The queryset
**must not drop unprocessed rows as work proceeds** — do not filter
on "still has an affiliation pick". Freeze the pk list at enqueue.

What we do not resurrect: the 7,000-line module, the console-in-the-
library, or `plan()` returning a giant step list that apply runs
blind. New, small step helpers (create slot type / pickable / picklist
/ slot, swap carrier, rewrite pick) plus one maintenance operation per
system. The preview is still the contract; the apply performs exactly
those steps.

## The window

Library swap is pack-wide. Pick rewrite is per-gang. Between them:

1. The granted slot looks unanswered (`chosen_for_slot` is unset on
   the affiliation pick).
2. The affiliation pick may still draw as its own row.
3. If modifiers had been **moved** off the affiliation row, every
   unconverted gang would lose its payload.

(3) is why we share, not move. (1) and (2) are why there is a
temporary dual-read in `compute`.

After library swap the offer assignment is archived and a slot grant
stands in its place. Existing picks still have `caused_by` pointing
at the **old offer** (a different assignment than the grant) and
`chosen_for_slot` unset. Matching on `caused_by == grant.id` never
works for those rows. Name against the slot's picklist does.

The window cannot create **new** affiliation picks of a converted
system: the offer is gone, so a player can only answer through the
slot. Gangs founded after the library swap are native and are not on
the frozen work-list.

### Dual-read shim

In `_fill_slot_choices` (`n26/core/effects.py`), query-free, no
system names hardcoded.

For each granted slot with no native pick (`chosen_for_slot_id ==
slot.pk`):

1. **Name match.** A live affiliation assignment on the same holder
   whose printed name is a member of this slot's picklist settles the
   slot. At most one such assignment per slot; two is a refuse in
   `do_one` (production has none — the 51 double-affiliation gangs
   are all chains, and the two names sit on different picklists).
2. **Hide.** That affiliation assignment does not draw as its own
   row. It is the answer, not a second fact.
3. **Empty choice.** After name-match, a remaining live affiliation
   assignment with **no modifiers**, on a holder that has an
   unanswered `min_picks=0` slot, is the explicit nothing-option of
   that slot: hide it, leave the slot unanswered. Clanless has no
   modifiers **and** is on the Affiliation picklist, so name-match
   wins first and this rule never fires on Outcast. "None" is not on
   the Variant picklist, so this is what hides it. Two unanswered
   `min_picks=0` slots competing for one empty-choice affiliation is
   a refuse; production does not have that shape (Helot Cult is not
   on Offer Variants).

`compute()` issues no queries. Names come off assignables already
loaded by `n26.core.card`. The shim must not fetch.

Delete the shim in cleanup, once no affiliation assignment remains.
A discovering test fails while the shim is still needed and fails
the other way once it is dead — that is the signal to remove it, not
a comment.

The shim is not a second source of truth for converted gangs:
`do_one` writes `chosen_for_slot`, and native `_fill_slot_choices`
takes over. After the last system, the shim is unreached.

## The runner shape

One console operation per system. One `Backfill` record. Two phases
in one task.

```
prologue  (library)     _run_recorded shape: one transaction,
                        REPEATABLE READ, spread capture, refuse-and-unwind
then
run_batched (player)    one gang per do_one, own commit, cursor, budget
```

`run_batched` as it stands has no prologue. Add an optional
`prologue(backfill)` (or a thin `run_library_then_batched` next to
it) that:

- runs once under the same lock and claim as the walk
- writes `summary["prologue"] = "done"` (and resets `attempts`)
  before any gang is rewritten
- is skipped on later deliveries when that flag is set
- on failure writes FAILED and walks nothing

Test it in `n26/tests/test_batched_runner.py` the way the walk is
already tested: prologue runs once; a crash after it does not rerun
it; a prologue refusal never starts the walk.

Do not nest `run_batched` inside `_run_recorded`. Do not split one
system across two slugs — the operator should have one button, and
the player phase is meaningless if the library has not landed. The
player preview refuses if the slot type is missing, so a half-run
cannot be started from a second direction.

### Frozen work-list

Computed at GET preview, stored on the record at POST, applied as
`Gang.objects.filter(pk__in=frozen).order_by("pk")`.

A gang is on the list if it holds a live **or archived** assignment
of this system's affiliation rows, **or** a live assignment of this
system's carrier (the unanswered case — capture is then a no-op
rewrite). Do not filter on "needs rewrite". Do not filter
`archived=False` on the affiliation *content* when finding picks a
subscriber already holds.

Gangs founded after enqueue are not on the list; they are native.

### `do_one(pk)`

Idempotent.

1. `select_for_update` the `Gang` row so a Choose mid-rewrite waits.
2. Fast path: every live and archived pick of this system on this
   gang already has `chosen_for_slot` set (and, for Variants, every
   None assignment is already archived) → return, **no capture**.
   A rerun of settled gangs must be cheap.
3. Capture `gang_state` before.
4. Rewrite live and archived picks in place (same `Assignment` pk):
   set `pickable`, `chosen_for=caused_by`, `chosen_for_slot`, clear
   the affiliation FK and `chosen_for_offer`. Kind-word history
   follows `chosen_for_slot.slot_type.name` (`n26/core/history.py`
   `_kindword`). Children keep `caused_by_id` because the parent row
   did not change pk — that is why Clan House's house pick and Chaos
   Corrupted's god grant survive the outer rewrite.
5. Variants only: archive remaining None assignments.
6. `assert_reconciled`.
7. Capture after. Refuse **this gang** on a diff (the runner records
   the failure and continues). Conversion-local comparator for
   Variant None as above; nowhere else.

`REPEATABLE READ` on the per-gang transaction so the two captures
see one world. A player purchase on a *different* gang is irrelevant;
on this gang the row lock holds them off.

Archived picks are rewritten even though `gang_state` does not see
them. Cleanup cannot drop the kind while archived rows still name it,
and history of an archived answer should tell the same truth as a
live one.

### Batch size

Default `BATCH_SIZE` is 50 and `BATCH_BUDGET` is four minutes.
`do_one` that captures renders the gang twice. Measure on a fork of
the content mirror before production; start at **20** if two renders
do not comfortably fit fifty into the budget. The attempt count
resets on every recorded batch, so a long walk is not mistaken for a
stuck one. Cancel is checked between batches.

### What the preview names

- Library steps (slot types, pickables, swaps), in words.
- Frozen gang count, and the spread the prologue will prove.
- Every gang whose stored answer will be cleared (Variants: the 187
  None).
- The history reword (Variant, Chaos God, Clan House).
- Problems: shared modifiers that are not this system's, name
  collisions with existing pickables, a slot type that already
  exists from a previous attempt (idempotent skip vs refuse — skip
  if it is ours, refuse if it is not).

## System 1 — Outcast Affiliation + Clan House

Independent of the others. Sandbox already green:
`n26/tests/sandbox/test_outcast_affiliation_shape.py`. No None. No
shared-across-types offer. The chain is the thing to prove.

```
create slot type "Affiliation", refusing repeats
create pickables Clanless, Clan House, Mutant, Aranthian
  (share their modifiers; Clan House's offer stays on both until
   the house slot grant replaces it)
create picklist "Affiliations"
create slot "Affiliation", assigned_to="gang", 1..1
on hidden "Affiliation": replace the offer with a grant of that slot

create slot type "Clan House", refusing repeats
create pickables House Cawdor … House Van Saar
create picklist "Clan Houses"
create slot "Clan House", assigned_to="gang", 1..1
  granted by the Clan House pickable
  (the offer on the affiliation row is swapped to this grant; the
   pickable shares it)

rewrite every Outcast affiliation pick and every house pick, live
and archived, on the frozen gangs
```

Work-list: Outcast foundings that hold the hidden (answered or not)
plus any gang that holds a house pick (should be a subset). ~119
gangs, 79 + 22 live picks, 34 + 7 archived.

Declared page diffs: none. History: Clan House picks reword from
"affiliation" to "clan house"; Affiliation picks stay "affiliation".
Pin both with a story test.

House Goliath has never been picked. Still create the pickable.

Fossils (unattached whole-kind Affiliation offer, unattached
"Corruption" offer): do not swap. Cleanup deletes them.

Live-content tests that still build the old kind, moved the way
#2307 moved the others — assertions unchanged:

- `n26/tests/sandbox/test_outcast_affiliation_flow.py`
- `n26/tests/sandbox/test_outcast_gang.py`

Do not rewrite `test_outcast_affiliation_shape.py` to match a
different shape. Convert live content to match that suite.

## System 3 — Chaos God, both doors, before Variants

One slot type, two slots, same picklist. A gang is never both a
Helot Cult and a corrupted house.

```
create slot type "Chaos God", refusing repeats
create pickables Architect of Fate, Blood God, Dark Prince, Plague Lord
create picklist "Chaos Gods"
create slot "Chaos God", assigned_to="gang", 0..1
  on hidden "Chaos God — Helots" (built into Chaos Helot Cult)
create slot "Chaos God", assigned_to="gang", 0..1
  on the Chaos Corrupted *affiliation* (the Variant chain's inner
  door — still an affiliation when this runs)
rewrite every god pick, live and archived
```

`min_picks=0` on both doors. The Helot offer never nagged (52 of 81
unanswered). Paths taught that `min_picks=1` on an offer that did
not nag is a capture failure. Chaos Corrupted's inner offer is the
same shape (5 of 33 unanswered). Do not introduce a nag.

Work-list: Helot Cult foundings (carrier, answered or not) plus
every gang that holds a god pick (the 28 corrupted). God pickables
carry no payload.

Declared page diffs: none. History: reword "affiliation" to "chaos
god". Pin with a story test.

Both doors in this operation, not Helot-only with Variants adding
the second later. Variants then shares the already-swapped grant
onto the Chaos Corrupted pickable; it does not create a second Chaos
God conversion.

## System 2 — Variants, last

Shared modifier "Offer Variants" on seven gang types (Cawdor,
Delaque, Escher, Goliath, Orlock, Palanite Enforcers, Van Saar).
`will_be_assigned_to=bearer`; the carrier is the gang type, hosted
on the gang, so every production pick is gang-hosted. Converted
slot: `assigned_to="gang"`. The swap is `SwapSharedCarrier` with
`reach=gang_alone` — not Gang Legacy's `reach=model`. Asked once on
the gang card, not echoed onto members as a choice.

```
create slot type "Variant", refusing repeats
create pickables Chaos Corrupted, Genestealer Cult Corrupted,
                 Malstrain Corrupted
  (not None; share modifiers, including Chaos Corrupted's grant of
   the Chaos God slot)
create picklist "Variants"
create slot "Variant", assigned_to="gang", 0..1
on the seven gang types: replace "Offer Variants" with a grant of
  that slot
rewrite the 65 corruption picks, live and archived
archive the 187 live and 17 archived "None" picks
```

Vestigial hidden "Variant" (0 assignments, not built in): do not
swap. Cleanup deletes it.

House types do not carry Variant in their built-ins. The offer rides
the gang type. Cawdor therefore keeps two gang questions: Path
(already a slot) and Variant.

Work-list: live foundings of the seven types (so unanswered / None /
corruption are all in), plus any gang that holds a Variant
affiliation pick. None is 45% of all live affiliation picks; the
fast path and the local comparator exist because of them.

Declared: the ledger loses 187 stored Nones. Pages capture equal
because the shim hides None against an unanswered `min_picks=0`
Variant, and `do_one` then archives the hidden assignment. Preview
names the 187. History: reword "affiliation" to "variant" for the
corruptions; None's archived history follows whatever `_kindword`
reads after the rewrite-or-archive — declare it, pin it.

`test_gang_books.py` builds Chaos corruption as an Affiliation. It
moves with this system.

### Why Chaos God before Variants

If Variants ran first, Chaos Corrupted would already be a pickable
and the inner offer would still be `OffersChoice(of_kind=affiliation)`
on that pickable until a later Chaos God run found it there. That
works, but it leaves a chain half on each machinery and makes the
Chaos God operation search two carrier kinds. Converting the inner
door while Chaos Corrupted is still the affiliation row matches
production as measured, and Variants then shares a grant that already
exists. Do not reverse this.

## What capture does not see

History wording. `gang_state` (`n26/core/capture.py`) holds names,
numbers, and `(kind_label, chosen)` — not provenance, not addresses,
not the ledger's kind word. A conversion may change where a control
leads and which machinery asks a question; it may not change what
the reader is told, except the declared None clearing (which the
local comparator makes a non-diff on the page) and the declared
history rewords (which capture never saw).

## Proof

Sandbox first, then a fork of the content mirror at the measured
volume. `backfill-lessons.md` still applies: plan frozen, refuse in
words, delete nothing (except the declared Nones), run as a task,
one lock per operation, verify from outside.

Per system, on the fork:

1. Snapshot `gang_state` for **every** reached gang, not the spread,
   from outside the operation.
2. Run the real console path (prologue then batched). Time it.
   Include at least one chain gang, one unanswered, one archived-
   only, one ordinary.
3. Diff the outside snapshots after. The operation's own capture is
   not the proof that ships.
4. Rehearse a Choose landing on a gang mid-`do_one` (the row lock)
   and a delivery dying after prologue (the flag). The Specialisation
   production failure was concurrent writes; do not skip this.

Spread the prologue proves, so a library mistake still unwinds
before any player row is rewritten. The batched walk then proves
every gang, which is the upgrade batching buys over the old "25 of
65" sample.

Volume:

| system | live picks | gangs (approx.) | archived |
|---|---|---|---|
| Outcast Affiliation | 79 | 119 foundings, 79 answered | 34 |
| Clan House (chain) | 22 | 22 of 25 Clan House gangs | 7 |
| Chaos God | 57 | 28 corrupted + 29 Helot (81 Helot foundings on the work-list) | 10 |
| Variant (corruptions) | 65 | 65 | 33 |
| Variant "None" | 187 | 187 | 17 |
| **total live to rewrite** | **223** (plus 187 Nones to clear) | **359** gangs hold at least one | **101** |

## PR sequence

One PR and deploy per system, same as last time. Do not convert all
three in one operation.

0. **Machinery, no system.** Dual-read shim + discovering tests;
   `prologue` on `run_batched`; the small step helpers; a Paths-
   shaped no-op against a database that has nothing to convert.
   Ship this first so the shim can sit in production empty (unreached)
   before anything swaps.
1. **Outcast + Clan House.** Operation, live-content test port,
   story tests for the Clan House reword. Recipes / `concepts.md`
   start teaching a slot type for a new gang-level choice after this
   lands, not before.
2. **Chaos God**, both doors.
3. **Variants**, including None.
4. **Cleanup, later, separate.** Empty the 18 kind rows, the four
   menus, the two fossil offers, the Variant hidden. Drop
   `affiliation` from `OFFERABLE_KINDS`, `LEAF_KINDS`,
   `ENTRY_ASSIGNABLE_FIELDS`. Delete the shim. Then drop the model
   and the Assignment column, the way #2314 dropped
   Archetype / SkillTree / Specialisation.

Retire each operation afterwards by keeping its slug registered with
`view=None`, same as the five that already ran.

## What not to do

- Replay the old one-transaction engine over 359 gangs.
- Move modifiers at library time.
- Filter the batched queryset on "still needs rewrite".
- Convert all three systems in one operation, or Variants before
  Chaos God.
- Drop the kind, the column, or `OFFERABLE_KINDS` in a rewrite PR.
- Hardcode system names in the shim.
- Silently correct Aranthian Gangers.
- Put a None pickable on the Variant list so capture can pretend the
  stored answer survived. Unanswered `min_picks=0` is the page;
  archiving None is the ledger change; the local comparator is the
  proof they read the same.
- Ship any of this as a migration.
- Query from `compute()`.
- Fold Variant and Chaos God into one Affiliation slot type to
  avoid the history reword.

## Worked example — one Clan House gang through the window

Before. Hidden "Affiliation" on the Outcast type offers the menu.
The gang holds Clan House (affiliation, `caused_by` the offer) and
House Cawdor (affiliation, `caused_by` the Clan House assignment).
Pages say Affiliation: Clan House, Clan House: House Cawdor. History
says "affiliation" twice.

Prologue. Slot types Affiliation and Clan House exist. Pickables
share the modifiers. Hidden offer becomes a grant of the Affiliation
slot. Clan House affiliation's offer becomes a grant of the Clan
House slot; the Clan House pickable shares that grant. Spread
captures, including this shape, match. This gang has not been
rewritten: `chosen_for_slot` is unset, `caused_by` still names the
archived offer.

Window, this gang. Dual-read: "Clan House" is on the Affiliation
picklist so that assignment settles the Affiliation slot and does
not draw as an affiliation row; "House Cawdor" is on the Clan House
picklist so that assignment settles the Clan House slot. Payload
still rides the affiliation rows. A visitor sees the same words. A
Choose goes through the slot, not the offer.

`do_one`. Both assignments rewritten in place. Clan House pick's pk
is unchanged, so House Cawdor's `caused_by` still points at it.
`chosen_for_slot` set. Native fill takes over. Capture matches.
History of the house pick now says "clan house".

Cleanup (later). No affiliation assignment remains on this gang. The
empty Clan House affiliation row can go. The shim no longer matches
anything here.
