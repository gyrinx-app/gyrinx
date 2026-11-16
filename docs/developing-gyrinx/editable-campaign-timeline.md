# Editable campaign timeline

An arbitrator arranges a campaign directly on its timeline. Persisted future
cycles remain planned entries that can be changed. Stable cycle identities
retain battle and action references while visible positions change.

## Required behaviour

- Add, edit, move, duplicate and remove future cycles and whole phase blocks.
- Give each phase occurrence its own identity, even when its rules and name
  match another occurrence. Duplicate a block together with its cycles.
- Number active phase occurrences and cycles consecutively using 01, 02, 03.
- Protect current and recorded activity through actual references, rather than
  treating every database record as protected history. Ordinary field corrections
  remain arbitrator actions; structural moves and removals protect used positions.
- Record explicit customisations, including cleared dates and empty text.
  Structural edits preserve customisations and validate the complete date order.
- Show an explicitly arranged timeline followed by a muted generated repeat
  tail. Viewing previews writes nothing. Inserting a cycle pushes the tail back
  without consuming a generated pattern position.
- A fixed schedule has an editable finite set of planned entries. Converting a
  seven-cycle pattern after position 15 completes that pass at 21. State the
  resulting endpoint before saving. Removing unused 16–21 then ends at 15.
- Keep Settings on its own URL-backed page for length and date defaults.
  Keep phase and cycle construction on the timeline.
- Show fixed credits and dice with their multiplier as one reward expression.
- Preserve feature-flag permissions, existing identities, attribution,
  transition receipts, optional dates, and exact uncertain-command retries.

Automatic advancement and additional campaign management modes are outside
this change. No existing schedules are reset or discarded.

## Data boundaries

`CampaignPhase` holds a campaign-owned rules definition. A phase occurrence is
an ordered campaign block that references those rules. Editing one occurrence
copies its definition when necessary so other blocks and the repeat pattern
retain their own rules.

`CampaignCycle` represents both a planned entry and a used cycle. Its identity
is permanent; its active position is editable. An occurrence owns the cycle's
place in the phase structure. Explicitly added and cloned entries need no
invented pattern source. Existing generated sources remain audit data.

The repeat cursor counts consumed generated positions independently of the
number and order of concrete entries. A manual insertion consumes no pattern
position. A single locked schedule command validates the whole proposed
candidate, persists it and records one durable result for retry.

## PR sequence

1. **Timeline data foundation:** occurrence identity, field provenance and
   additive migration preserving all existing values.
2. **Editable timeline:** pure editing operations and atomic persistence together
   with their React authoring surface. Keep the display and command contracts
   in the same PR. Include simple Settings, separate repeating-pattern editing,
   fixed endpoint feedback, permissions, attribution and exact retry recovery.
3. **Reward expression refinement:** connect fixed credits, dice and
   multipliers into one expression using the existing form primitives.

Every PR receives a task-focused feature review, the repository's rendered
three-pass design refinement where applicable, focused local checks, visual
evidence for visible changes, and a current-head CI/review cycle. The stack is
left ready for human review and remains unmerged.

## Acceptance examples

Editing Cycle 6 may persist 2–6; it does not remove them from the editable
planned timeline. Removing an unused entry closes the active numbering gap and
preserves all surviving identities. Editing a later entry and then an earlier
one retains both changes.

A repeating prefix of 15 cycles can accept Market week at 16. Its generated
continuation starts at 17 without losing the first pattern slot. Reordering a
block keeps its identity and children. A cloned block receives new identities.

After conversion to fixed at 21, removing unused 16–21 makes the endpoint 15.
No replacement preview silently recreates those deleted cycles. Current and
recorded references survive every accepted structural change.
