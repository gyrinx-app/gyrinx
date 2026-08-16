# Migrating the chosen kinds onto slots and picks

The plan for retiring Affiliation, Archetype, SkillTree and Specialisation
in favour of slot types, pickables, picklists and slots. Grounded in
`.claude/notes/chosen-kinds-map.md` (the survey of the eight authored
systems and 1,330 live production picks). Maintainer rulings, 2026-08-16:
**concrete pickables** (the old kinds' rows become Pickable rows; the old
kinds retire), **slots arrive granted by modifiers** (never built in,
except where a starting pick demands it), **one PR and deploy per system**.

## The two facts the plan stands on

1. **Every live pick's `caused_by` already names the right anchor.** All
   1,330 picks are caused by the offering carrier's assignment — the
   founding hidden, the gang's founding (gang type) assignment, the
   profile membership, the materialised Specialist subtype. Those rows
   stay.
2. **Granted slots make old and new gangs uniform.** The carrier that
   used to say *offers a choice of X* says *adds the X slot* instead.
   Existing gangs' stored carriers immediately ask the new question; no
   assignments are planted. A pick's new `chosen_for` is exactly its
   existing `caused_by`.

So the player-data rewrite is a **column mapping**, per pick row:

```
pickable        = mapping[old kind row]
chosen_for      = caused_by            (already set on all 1,330)
chosen_for_slot = the system's Slot
affiliation/archetype/skill_tree/specialisation = NULL
```

No new rows, no ledger events, no rating movement (picks are free);
`assert_reconciled` on every touched gang.

## Phases (per system, in one PR each)

**0. Engine preconditions** (once, before the pilot):
   - The anchor stack lands (#2207 with #2206 folded in).
   - Verify `puts the chosen set under…` reads a slot-borne pick, and
     settle how a chosen *pickable* names the Category it places —
     today the placement machinery resolves a chosen SkillTree; under
     concrete pickables the tree is a Pickable, and the mapping from
     pickable to skills Category must be stated (candidate: the
     pickable's own home `category`). Gates Skill Trees only.

**1. Author the target content beside the old** — scripted from the map
   (a management command or data migration in the system's PR, so the
   rehearsal and prod get identical rows): the slot type, pickables
   (payload modifiers moved from the old kind rows verbatim — scope and
   conditions unchanged), picklists from the menu collections, slots
   with their labels and, for Skill Trees, their own placement
   modifiers. Inert: nothing grants the slots yet.

**2. Switch the carrier** — the offering carrier's `offers a choice`
   modifier is deleted and an `adds the slot` modifier put in its place.
   One content edit flips the system for every gang at once.

**3. Rewrite the picks** — the column mapping above, in the same
   migration, with a printed per-gang report (the 0061 pattern).

**4. Estate diff — the "very carefully".** Before merging each system's
   PR: run the whole thing against the local prod mirror, render every
   production gang's cards and sheets before and after, and require the
   diff to be empty apart from the choice rows' own addresses and
   wording. A harness script rides the first PR and is reused by all.

**5. Retire that system's old content** — the old kind rows, the menu
   collections (now duplicated by picklists), the offer hiddens' spare
   modifiers, in the same PR once the diff is clean. Cross-system code
   retirement (dropping the kinds from `OFFERABLE_KINDS`,
   `ENTRY_ASSIGNABLE_FIELDS`, the Assignment columns, the models) is a
   final PR after the last system, with the column drops one deploy
   later than the code that stops reading them.

## Order of battle

| # | system | why here | size |
|---|---|---|---|
| 1 | Cawdor Paths | the pilot: every mechanism, two pickables, 26 picks | S |
| 2 | Specialisation | simplest shape, biggest volume — proves the rewrite at scale (939 picks, 358 gangs) | M |
| 3 | Variants | retires the "None" affiliation for `min_picks=0` + the None row (82 picks say nothing) | M |
| 4 | Chaos God | two slots, one type (granted by the Chaos Corrupted pickable; built into Chaos Helot Cult's hidden) | S |
| 5 | Outcast Affiliation + Clan House | the chain: Clan House pickable grants the House slot | M |
| 6 | Outcast Archetype | gang slot (leader-carried, assigned to gang) + bearer slot (Champion), one slot type; Wyrd payload | M |
| 7 | Venator Skill Trees | four slots of one type, `allows_repeats` off, per-slot placements — needs phase 0's check | L |
| 8 | Venator Gang Legacy | one bearer slot on twelve profiles; Ironhead Squat finally on a picklist | M |

Chaos God ships with or immediately after Variants (its slot is granted
by the Chaos Corrupted pickable, so the chain crosses the two systems).

## Per-system notes

- **Paths**: hidden "Path" swaps offer → grant. Pickables Fanatic/Pious
  keep their gang-rule modifiers. 26 picks re-anchor.
- **Specialisation**: the Specialist subtype swaps its whole-kind offer
  for the slot grant; the picklist lists all eight. The Subjugator
  narrow list revives as a second picklist + profile-granted slot with a
  profile-carried removal of the general one — the exact pattern the
  probe suite proves. The orphan hiddens and the one hand-given
  assignment are cleaned up here.
- **Variants**: slot `min_picks=0`, granted by the seven gang types
  (anchored on each gang's founding assignment). The "None" affiliation
  is not migrated; its 82 picks are **deleted** in the rewrite (an open
  optional choice says the same thing), with the report naming each.
- **Outcast Affiliation**: gang slot granted by the founding hidden;
  Clan House pickable carries "adds the House slot" (gang) — chained
  choice, already proven in the sandbox. Aranthian's rank condition is
  corrected to Leaders and Champions as part of the payload move
  (maintainer's ruling; the report says so loudly).
- **Archetype**: one slot type, two slots — "the gang's archetype"
  granted by the four Leader profiles with `assigned_to=gang`, and the
  Champion's own bearer slot. `allows_repeats` stays on (a Champion may
  deliberately re-pick the gang's archetype). Champion payload rows keep
  their bearer reach; leader rows their all-models reach.
- **Skill Trees**: one slot type, `allows_repeats` off, four slots each
  carrying their own placement modifiers (the long `is_profile` lists
  move over verbatim; simplifying them to rank subtypes is content
  cleanup for later, not this migration).
- **Gang Legacy**: bearer slot granted by a modifier shared across the
  twelve profiles. Later, per the rulebook, this system grows the
  family-keyed picklists and — the one anticipated **built-in** case —
  profiles whose legacy arrives already settled take the slot as a
  built-in with a `default_pickable` instead of the grant.

## What the rewrite must not touch

- Ledger and ratings: picks are free; every touched gang asserts
  reconciled, before and after.
- The stored carriers (hiddens, founding rows, memberships): they stay,
  as the anchors they already are.
- n23: nothing here reads or writes the other edition.

## Rollback

Each system's deploy is one migration: content swap + pick rewrite. The
reverse migration restores the offer modifier and maps pick columns
back (the mapping is bijective; the report records every row id). The
"None" deletion is the one lossy step — its reverse recreates the picks
from the report's row list, so the report is retained as an artefact.

## Open items

- Phase 0's placement check (gates Skill Trees only).
- The estate-diff harness: build with the pilot, reuse throughout.
- Content corrections riding along: Aranthian ranks (system 5), Ironhead
  Squat wiring (system 8), dead-content pruning (each system cleans its
  own).
