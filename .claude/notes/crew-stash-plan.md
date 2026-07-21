# Stash items in crew selection — plan

Source: maintainer's expert-call notes (2026-07-21). Follows the crew
setup/eligibility work (PR #2017 + follow-ups).

## Requirements (from the notes)

1. Stash items come in two kinds:
   - **Optional** — items you may choose to bring to a fight (with or without a
     linked fighter card).
   - **Always brought** — equipment that is effectively part of the gang in
     every battle (Iron Automaton). Flagged in the **content library**
     ("always enabled for crew"); the tick box is auto-enabled and hidden — no
     way to untick, no confusion.
2. Crew edit becomes **three tabs**: 1. Set up · 2. Choose fighters · 3. Stash.
   Stash is its own screen partly so that ticking an item never needs dynamic
   updates of the fighter list.
3. Stash items appear as **their own section in the crew table** (below
   Fighters, above Extras).
4. **Equipment-linked fighter cards** (gun emplacement): equipment with a
   fighter link, NOT a true crew member. Shown as a fighter-like row pulling
   its credit rating from the stash equipment — "3 fighters + gun emplacement".
5. Stash selection **can change after the crew is locked** (gang terrain etc.
   get chosen after the random draw), so the Stash tab must work on locked
   crews — and stash value must stay OUT of the frozen rating snapshots.
6. **Print**: forward the linked cards' IDs so they render alongside the crew's
   fighter cards.

## Design

- `ContentEquipment.crew_always_brought` (bool, admin-set) — the content flag.
- `CrewStashItem` (AppBase): `crew` FK + `assignment` FK
  (ListFighterEquipmentAssignment on the gang's stash), unique together.
  Represents "this stash item is brought to this battle". No lock gating.
- Always-brought items are **computed, not stored**: any stash assignment whose
  equipment carries the flag is in every crew's stash section automatically
  (mirrors the always-included fighters pattern). The Stash tab lists them
  ticked-and-disabled (display only).
- Receipt gains a `stash` section: one row per brought item —
  `{name, rating (assignment cost), child fighter?, always_brought}` — included
  in the live Total but never in `rating_selected` / `rating_played` (those
  freeze fighters only; stash stays live because it's editable post-lock).
- Tabs: draft crews show Set up / Choose / Stash; locked crews keep a Stash
  entry point (tab bar shows Stash alone → render as a single action link on
  the crew page instead if it looks odd).
- Print: `?crew=` already narrows to crew fighters; add the child fighters of
  brought stash items to the printed set.

## Increments

1. Content flag + `CrewStashItem` model + handler helpers (+ migrations).
2. Stash tab (view/form/template; works on draft AND locked).
3. Crew table stash section (+ totals; equipment-linked rows read like
   fighters).
4. Print forwarding.

## Open points (validate during build)

- Stash assignment cost: use the assignment's cost_int (matches how the stash
  values gear).
- GANG_TERRAIN category fighters: excluded from crew eligibility (they're not
  fighters you select) — confirm current behaviour.
