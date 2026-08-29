# Converting Affiliation onto slots and picks — the plan

How the three leftover Affiliation systems move. Why they should, and
the split, live in
[`affiliation-conversion-eval.md`](affiliation-conversion-eval.md).
Production counts there are from 2026-08-27, read-only. n23 is out of
scope.

The cutover is the same shape the earlier conversions used, minus the
part that made them slow: **one write per system**, then an operator
runs `audit_reconcile` afterwards. Do not run the old offer and the
new slot on the same gang. Do not rewrite picks one gang at a time.

The writes are a few hundred assignments and are quick. The reconcile
walk is the slow part: the apply reconciles every reached gang inside
the transaction, and each gang needs several queries against a database
across the network. Duration depends on the gangs a system reaches. Do not
enqueue `run_batched` on the same Backfill — the conversion already
marks that record DONE. The after-the-fact check is the existing
`audit_reconcile` operation, run by hand.

## Decisions

| | |
|---|---|
| Three systems | Affiliation (Outcast + Clan House), Chaos God, Variant. Four slot types: Clan House is its own type, chained off the Clan House pickable. |
| Order | Machinery → Outcast + Clan House → Chaos God (both doors) → Variants (including None) → cleanup later. |
| One flip | Create the slots, move modifiers onto pickables, swap offer → grant, rewrite every pick of that system, in **one transaction**. Lock the reached gangs first so a Choose cannot land mid-write. |
| Proof in that transaction | A **spread** of shapes, `gang_state` before and after, refuse and unwind on any difference. Every reached gang `assert_reconciled`. |
| Proof after | Operators run `audit_reconcile` (read-only) after the flip. Do not nest `run_batched` on the conversion's Backfill. On a content-mirror fork, also diff **every** gang's pages from outside the run, and time the write. |
| "None" | Archive the 187 live and 17 archived picks. Variant `min_picks=0`. Spread compare treats chosen `"None"` and `""` as equal for that question. Preview names the 187. |
| Aranthian Gangers | Keep the modifier as authored. |
| Repeats | All four types refuse them. |
| Kind column | Stays until cleanup. |
| Writes | Assignment updates are the sanctioned conversion exception (`n26/core/CLAUDE.md`): no `operation()`, no money, no ledger events. |

If the fork write is not short (seconds, not minutes), stop and look
again. Do not then invent a per-gang window. A fork time is a floor:
the fork answers over a socket, and production answers over the
network, so production is slower than the assignment counts suggest.

## Reusable machinery

#2287 deleted `n26/library/conversion/`. Put back a **small** module,
not the 7,000 lines: frozen plan, typed steps, one apply, refuse in
words. Console operations in `n26/maintenance.py` call it through
`_run_recorded`. After a successful flip, operators run
`audit_reconcile`; the conversion does not enqueue it.

Steps the three systems share (copy from `000f2022^`, keep thin):

- `CreateSlotType`, `CreatePickable` (moves modifiers; qualifier if a
  name collides), `CreatePicklist`, `CreateSlot`
- `SwapCarrier`, `SwapSharedCarrier` (Variant needs `reach=gang_alone`)
- `RewritePick` — same `Assignment` pk: set `pickable`,
  `chosen_for=caused_by`, `chosen_for_slot`, clear the affiliation FK
  and `chosen_for_offer`. Children keep `caused_by_id`.

Apply helper, used three times:

1. `REPEATABLE READ` (`SET SESSION CHARACTERISTICS` **before**
   `transaction.atomic()` — isolation can only be chosen before the
   transaction has read anything).
2. `select_for_update` the reached gangs (holders first, ordered by
   pk).
3. Capture the spread.
4. Perform exactly the frozen steps.
5. Capture the spread again; refuse and unwind on a diff.
6. `assert_reconciled` every reached gang. That is a read-only check
   — it does not call `reconcile_defaults` or `self.assign`.

Nothing new in `compute`. `_choose_for_slot` already lands a pick on
the gang; chained grants already retract through cause; optional
slots already offer a None row.

A successful flip leaves the offers gone, so a retry is
`nothing_here`. A standing slot type of the same name is a refusal,
not a skip. A pick that already has `chosen_for_slot` is left.

Preview is the contract. The apply performs those steps and no
others. Ship as a console operation after deploy, never as a
migration.

## System 1 — Outcast Affiliation + Clan House

Independent. Sandbox already green:
`n26/tests/sandbox/test_outcast_affiliation_shape.py`. Convert live
content to match that suite.

```
create slot type "Affiliation", refusing repeats
create pickables Clanless, Clan House, Mutant, Aranthian
  (move their modifiers; Clan House's offer becomes a grant of the house slot)
create picklist "Affiliations"
create slot "Affiliation", assigned_to="gang", 0..1
on hidden "Affiliation": replace the offer with a grant of that slot

create slot type "Clan House", refusing repeats
create pickables House Cawdor … House Van Saar
create picklist "Clan Houses"
create slot "Clan House", assigned_to="gang", 0..1
  granted by the Clan House pickable

rewrite live and archived Outcast + house picks
```

`min_picks=0` on both slots — a modifier offer never nagged;
`min_picks=1` added "Affiliation — 0 of 1 chosen" and broke capture
plus `Lead the Masses`. Clan House slot `label="Clan house"` so
`choice_label` matches `capfirst` of the old offer.

Spread must include: answered, unanswered, Clan House without a house,
Clan House + house, archived re-choice. History: Affiliation stays
"affiliation"; house picks reword to "clan house". Pin with a story
test.

Live-content tests that still build the old kind, moved the way #2307
moved the others — assertions unchanged:

- `test_outcast_affiliation_flow.py`
- `test_outcast_gang.py`

Fossils (unattached whole-kind offer, "Corruption" offer): do not
swap. Cleanup deletes them. House Goliath has never been picked;
still create the pickable.

## System 2 — Chaos God, both doors, before Variants

```
create slot type "Chaos God", refusing repeats
create pickables Architect of Fate, Blood God, Dark Prince, Plague Lord
create picklist "Chaos Gods"
create slot "Chaos God", assigned_to="gang", 0..1
  on hidden "Chaos God — Helots"
create slot "Chaos God", assigned_to="gang", 0..1
  on the Chaos Corrupted affiliation
rewrite live and archived god picks
```

`min_picks=0` on both doors — neither offer nagged. History rewords
to "chaos god". Both doors in this run, so Variants only shares an
existing grant onto the Chaos Corrupted pickable.

## System 3 — Variants, last

```
create slot type "Variant", refusing repeats
create pickables Chaos Corrupted, Genestealer Cult Corrupted,
                 Malstrain Corrupted
  (not None; move modifiers, including Chaos Corrupted's Chaos God grant)
create picklist "Variants"
create slot "Variant", assigned_to="gang", 0..1
on the seven gang types: SwapSharedCarrier, reach=gang_alone
rewrite live and archived corruption picks
archive live and archived "None" picks
```

Vestigial hidden "Variant" (0 assignments): do not swap. `test_gang_books.py`
moves with this system.

## PRs

0. **Machinery.** The small conversion module, apply helper, spread
   capture. A no-op against a database that has nothing to convert.
   No Affiliation row rewritten. After the flip, operators run
   `audit_reconcile` by hand.
1. **Outcast + Clan House.**
2. **Chaos God.**
3. **Variants.**
4. **Cleanup, later.** Empty the 18 kind rows, four menus, fossil
   offers, Variant hidden. Drop `affiliation` from `OFFERABLE_KINDS`,
   `LEAF_KINDS`, `ENTRY_ASSIGNABLE_FIELDS`. Then drop the model and
   the Assignment column, the way #2314 dropped the other three.

One PR and deploy per system. Do not convert all three in one
operation. Do not drop the kind in a rewrite PR. Recipes and
`concepts.md` start teaching a slot type for a new gang-level choice
after system 1 lands, not before.

Retire each operation afterwards by keeping its slug registered with
`view=None`.

## What not to do

- Render every reached gang inside the write.
- Dual-read in `compute`, per-gang flags, or dormant slots.
- Move modifiers in a transaction that has not yet rewritten the
  picks (there is no such transaction).
- Convert Variants before Chaos God.
- Silently correct Aranthian Gangers.
- Ship any of this as a migration.
