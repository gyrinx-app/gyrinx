# The Archetype conversion — the plan

The last system on the archetype column, and the last of the four
conversions. Everything below is measured from production, 2026-08-19,
read-only.

## What is there

| | count |
|---|---|
| Live picks | 102 |
| — landing on the gang (a Leader's answer) | 40 |
| — landing on a model (a Champion's own) | 62 |
| Archived picks (stay put) | 73 |
| Gangs reached (holding a carrier profile) | 65 |
| Carrier fighters | 143 |
| Archetypes on the menu | 5 |

The menu ("Outcast Archetypes / Archetypes") lists exactly the five —
Brawler, Gunslinger, Mastermind, Survivor, Wyrd — all live, each
carrying its whole printed table as 10–11 modifiers. The six emptied
house rows and Ironhead Squat are **not** on it and are no part of
this.

Five carried offers, all narrowed to that one menu, all labelled
"Archetype":

- four on the Leader profiles (`Leader 1`–`Leader 4`), each its own
  copy, answers landing **on the gang**;
- one on the Champion profile, answer landing **on the bearer**.

Data is clean: no doubled answers, no pick without an anchor, no
anchor that is not a live profile line, and every pick's host matches
its anchor's kind (40 gang-hosted from Leader anchors, 62
model-hosted from Champion anchors).

## The behaviour that must survive

1. **The gang's archetype reaches every fighter except Champions.**
   The tables hang off the shared rank subtypes; Champions are simply
   not named by them.
2. **A Champion's own pick affects only that Champion.** Each token
   carries bearer-only "(own pick)" rows — inert in the gang's
   radiated copy, live on a Champion who picked personally.
3. **The gang's archetype dies with the Leader.** The pick is caused
   by the Leader's profile line; removing the Leader cascades it away.
   "Chosen when a Leader is recruited" is data, not prose.
4. **A Champion may pick what the gang already has.** Ten do today,
   silently.

All four are carried by the modifiers themselves, so moving them
wholesale preserves them by construction — and each gets a test.

## The shape

```
create slot type "Archetype", allowing repeats
create pickable "Brawler"     (Archetype, qualifier "Archetype"), moving 10 modifiers
create pickable "Gunslinger"  … moving 10
create pickable "Mastermind"  … moving 10
create pickable "Survivor"    … moving 10
create pickable "Wyrd"        … moving 11
create picklist "Archetypes" offering all five
create slot "Archetype", pick landing on the gang        ← the Leaders' question
create slot "Archetype (Champion)", pick landing on the bearer, label "Archetype"
on the "Leader 1" profile: replace its offer with a grant of "Archetype"   ← ×4, one per profile
on the "Champion" profile: replace its offer with a grant of "Archetype (Champion)"
rewrite 102 picks
prove 25 of 65 reached gangs read the same, or refuse
```

Nothing is deleted: the five archetype rows stay (emptied), the menu
collection stays, the one detached fossil offer stays.

### Three decisions inside that

**Two slots, one slot type, repeats allowed.** The two questions are
the same sort of question, so one type. Repeats must be *allowed*:
ten Champions currently hold their gang's archetype and the page says
nothing about it, because an offer never remarks on a repeat. Refusing
repeats risks introducing a note where there is silence today — and
the game permits it anyway. (In practice the note machinery would not
fire either way, since the two questions are asked on different cards;
allowing repeats is the setting that cannot surprise us.)

**The pickables carry a qualifier — "Archetype".** Two of the five
names are already taken: `Brawler` and `Gunslinger` exist as
**Specialisation** pickables, and pickable names are unique per pack
and qualifier. A qualifier is exactly the tool for this (it tells two
same-named things apart in authoring screens and never reaches a
player), so all five take one, uniformly, and the cards go on saying
"Brawler". Without it the plan refuses — the preflight added in #2248
catches the collision before anything is written.

**The four Leader offers stay four.** Per your call: four grants of
the same slot, one per profile, rather than one grant re-anchored onto
the shared Leader subtype. No stored pick moves anchor, so the death
cascade is untouched; the factoring stays as the authors left it.

## What the history says

Nothing changes. The slot type is named "Archetype", so a pick's kind
word reads "archetype" after the conversion exactly as it reads
"archetype" now — identical whether or not these picks draw the word
at all. Pinned by a story test, as every conversion has been.

## Engine work

One addition: `CreatePickable` learns a `qualifier`. Everything else —
`SwapCarrier` (used five times), `CreateSlot(assigned_to="gang")`,
`RewritePick` — already exists and is proven.

The gang-landing slot needs no new machinery: `_choose_for_slot`
already documents the case ("the Leader is asked and the gang holds
the answer") and routes a pick to the gang when the slot says so,
mirroring the offer's `will_be_assigned_to="gang"` exactly.

## The proof

Sandbox tests, following the four suites already in the tree:

- plan wording; deletes nothing; a standing "Archetype" slot type
  refuses; a pickable name collision refuses (the qualifier is what
  clears it); an off-menu pick anchored on a carrier profile refuses;
  an archived menu entry refuses.
- page parity across the shapes: a gang whose Leader answered, a
  Champion who answered differently, a Champion who answered *the
  same*, a gang with two Leaders (one exists), a gang that never
  answered, and an archived re-choice left behind.
- the four behaviours above, asserted per fighter before and after:
  Champions untouched by the gang's archetype; a Champion's own pick
  reaching only them; the Leader's death taking the gang's archetype
  with it; the matching Champion drawing no note.
- rechoosing on the new machinery, both slots.
- story parity, and the kind word reading "archetype".

Then the standing rule: a fork of the content mirror, a population
built at the measured volume above (65 gangs, 143 carrier fighters,
102 picks, including the two-Leader gang and the ten matching
Champions), the real code path run and timed, and **every** reached
gang diffed from outside the run — pages, history, reconcile.

## Console

One new operation, "n26: the Outcast archetypes become picks", on the
same runner, lock, attempt cap and audit record as the other three.
No retirement needed: the field is clear (no "Archetype" slot type,
no "Archetypes" picklist, no slot of either name).

## After it lands

The `archetype` column holds nothing live. Retiring the column itself
— and the emptied Archetype, SkillTree and Specialisation kinds with
it — is a separate piece of work, and the one place where deleting is
finally the point rather than a hazard.
