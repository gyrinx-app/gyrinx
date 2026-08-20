# Finishing the conversions — what is left, and in what order

Measured against production, 2026-08-20, read-only. The four conversions
have all run; this is everything they left behind and the order it can
be cleared in.

## What is actually left

| | count |
|---|---|
| Emptied kind rows (Archetype 12, SkillTree 6, Specialisation 8) | 26 |
| — of those, still carrying anything | 1 (Ironhead Squat) |
| Archived assignments naming an old kind | 399 |
| Live assignments naming an old kind | 4 (doubled-click spares) |
| Menu collections left standing | 3 |
| Detached fossil offers | 1 |
| Unreachable offer (general hidden, never held by anything) | 1 |

**The columns are closed.** No live route creates a new row of any old
kind: the archetype fossil is carried by nothing, the general
Specialisation hidden has never been held by any assignment and its
granter is detached, and every other offer became a slot grant. The
four live rows are spares from a click that landed twice, anchored on
a subtype whose question is now a slot.

## The order

Four things can start at once. Everything else is one chain behind
them.

### Wave 1 — start together, no ordering between them

1. **The double-submit fix.** The only item still *making* mess: a
   click landing twice writes a second identical answer. Nothing else
   waits on it, and every day it stays costs another spare.
2. **The archived-pick sweep.** A console operation rewriting the 399
   archived assignments onto their pickables, as the Paths conversion
   did for its own. **This is the gate**: the kinds cannot be retired
   while anything names them, so start it early even though it lands
   last. Needs the conversion machinery, so it must precede wave 4.
3. **The timeout revert.** The Cloud Run request timeout and the task
   ack deadline move together or not at all — a run outliving its
   deadline is redelivered while the first copy works. Conversions now
   finish in single-digit seconds.
4. **Squat legacies** (content, in the admin). Re-offer Ironhead Squat
   as a Gang Legacy pickable and grant the slot to the three Squat Hunt
   profiles, which carry no legacy question. This also empties the last
   archetype row still carrying anything, which wave 2 wants.

### Wave 2 — after the sweep has run in production

5. **The library cleanup.** One more one-shot operation, the pilot
   retirement's shape: delete the 26 emptied kind rows, the three menu
   collections, the detached fossil offer, the general hidden and its
   detached granter. Refuses if anything still names them, which is
   why the sweep comes first.

   The four spares belong to this decision. They are a duplicate line
   on four gangs' pages; archiving them removes it. That is a page
   change on four gangs, and it is a fix rather than a regression —
   but it is a change, and it should be named rather than slipped in.

### Wave 3

6. **Re-sync the content mirror from production.** After 4 and 5, so
   the mirror inherits the tidy library rather than the old one.

### Wave 4

7. **Retire the conversion modules and their console operations.**
   Slug registered with `view=None`, code deleted, the way the wargear
   merge went. Waits on the mirror: until then every local database
   forks unconverted and needs the conversions as its route across.

### Wave 5 — the big one, planned separately

8. **Drop the three kinds and their columns.** This is not a tidy-up;
   it is a change across 21 files and every parallel registry the
   library keeps: `ASSIGNABLE_FIELDS` and the Assignment columns,
   `OFFERABLE_KINDS`, the ingest sheets and their four tables, the
   specs and authoring pages, collection entries, the selector
   algebra, card building, history, sample data — plus a migration
   dropping three columns and three tables. Startup checks enforce the
   registries agreeing, so a half-done version does not boot.

   Worth doing, but worth its own plan and its own smoke test on a
   fork, and it must be last: it needs the sweep (no data), the
   library cleanup (no rows) and the retirement (no code) all done.

## The critical path

    archived sweep → library cleanup → mirror re-sync → retire the
    conversions → drop the kinds

The double-submit fix, the timeout revert and the Squat content hang
off nothing and can land in any order alongside it.

## One judgement worth making early

Retiring the kinds means rewriting 399 archived assignments — history
rows the later conversions deliberately left alone. The precedent
exists (Paths rewrote its archived picks so the retirement could
land), and the alternative is keeping three dead kinds in the
authoring menus, the ingest sheets and the card code for ever. The
recommendation is to do it, but to decide it deliberately before wave
1 starts, because the sweep is only worth building if the kinds are
going.
