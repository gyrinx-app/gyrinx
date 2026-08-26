# Finishing the conversions — the plan, and where it has got to

n26's hand-built choice systems have all been moved onto slots and
picks. This is the tidying that follows: what is left, the order it can
be done in, and the decisions already taken. Written to be picked up
cold.

**Nothing here names a player, a gang or an assignment id.** The counts
are shapes; every operation finds its own rows by query. The repository
is public.

## Where it stands

**The three retired kinds are gone from production.** Verified there on
2026-08-23: no Archetype, SkillTree or Specialisation row remains, and
nothing anywhere names one — no assignment, no menu entry, no offer.

| | |
|---|---|
| The five conversions (Paths, Specialisation, Skill Trees, Gang Legacies, Archetypes) | run |
| The gang legacy slot pilot | retired |
| The archived-answers sweep | run — 399 answers, 169 gangs |
| The spares a doubled click left | cleared — 4 answers, 3 gangs |
| What the conversions left standing | deleted — 26 kind rows, 22 menu entries, 4 menus, 6 modifiers, 1 marker |
| The content mirror | re-synced from the tidy library |
| The conversion code | retired — eight slugs kept, ~7,000 lines gone |
| A superuser may delete player data in the admin | merged |
| A doubled click no longer answers a question twice | merged |
| The authoring menu no longer offers the retired kinds | merged |
| The foundations page stops planting specialisations | merged (#2306) |
| The sandbox suites move onto slots and picks | merged (#2307) |
| The Archetypes ingest sheet and specialist-only restriction | PR #2310 |
| The three models, their columns and their tables | PR — see below |

**Wave 5, stage 4** drops the shape the kinds used to fill:
`Archetype`, `SkillTree` and `Specialisation`, three `Assignment`
columns, two `CollectionEntry` columns, six `usable_by_specialisations`
tables, three `_modifiers` tables, and their entries in every parallel
registry. Rehearsed on a fork of the content mirror — which still held
the 26 orphan rows — with every other library count identical
afterwards and eleven authoring pages rendering 200. Production holds
none of those rows, so its migration is pure schema.

Two things stay on purpose: the eight conversion slugs registered in
`n26/maintenance.py` with `view=None`, which name past `Backfill` rows,
and the `SlotType` rows called Archetype, Skill Tree and Specialisation
— those are the *new* system, and are what made the deletion safe.

Three things were kept on purpose and are named on the deletion's own
page: the two markers profiles are built with, and the marker a live
profile still asks through.

## What the conversions left

Measured against production on 2026-08-22, before any of it was cleared.
Kept as the record of what the three operations above actually faced:

- **26 emptied kind rows** — 12 Archetype, 6 SkillTree, 8 Specialisation.
  One archetype still carries a modifier (the house legacy the menu
  never offered).
- **399 archived assignments** naming an old kind, across 169 gangs.
  The sweep is for these.
- **4 live assignments** naming Specialisation. These are spares from a
  doubled click, on three owners' gangs — one fighter has two. Each
  draws a phantom line in its fighter's gear list, named after the
  specialisation, beside a correctly settled choice row. They carry no
  money and no rating, nothing hangs off them, and the skill they grant
  is drawn once regardless. **Decision taken: clear them.** Removing
  them removes four wrong lines and changes nothing else.
- **4 menu collections** holding 22 entries, **1 detached fossil
  offer**, and the general Specialisation Offer hidden — never held by
  any assignment, so no route creates a new row of any retired kind.
  Note the two markers whose names differ only in case: one of them
  *is* held. Two placements aim at a menu from markers that profiles are
  built with; only the placements are dead.

## The order

### Wave 1 — done bar the timeout revert

1. ~~The double-submit fix.~~ Merged. It was a genuine race: the picker
   replaced what stood, but decided that from the page it had drawn, so
   two answers in flight together each found nothing to replace.
2. ~~The archived-answers sweep.~~ Merged, and merged again with the
   rewording it has to own up to. This is the gate: the kinds cannot be
   retired while rows name them.

   Its first run **refused**, which is the proof working. 34 of the 399
   answers move a word: dropped gang legacies, which sit in the
   archetype column because that column holds two unrelated systems, so
   their history calls the house an "archetype" where the pick says
   "gang legacy". That is the truthful word and the one the same gang's
   *kept* legacies already use, so the sweep now declares the rewording
   and counts it on the page before anybody agrees to the run, and
   refuses every other word that moves.
3. ~~The authoring menu retirement.~~ Merged.
4. **The timeout revert** — not started. The Cloud Run request timeout
   and the task ack deadline move together or not at all. Raised for a
   conversion that took eighteen minutes; conversions now take seconds.
5. ~~Squat legacies.~~ Done, and it was already done before this plan
   named it: the Ironhead Squat and Ogryn pickables and the six built-ins
   that answer them were authored on 2026-08-19. Neither is in the House
   Legacies picklist, which is right — a Squat or Ogryn crew's legacy is
   not chosen, it arrives with the profile.

   What remained was one leftover: the old Archetype row still carried
   the equipment-list modifier, which the *pickable* also carried. Nothing
   named the row and nothing was at risk, but the deletion refuses a kind
   row that carries anything. Detaching the modifier from the archetype
   (the authoring page still resolves; only the menu retired it) left the
   modifier on the pickable and the row deletable.

### Wave 2 — the library cleanup, run

Two operations rather than one, because they carry different risks and
the second could not run until the first had. Both have now run.

6. ~~Clear the spares.~~ Run: 4 answers on 3 gangs, in 11 seconds.

   Each was a live answer a doubled click left beside the one that
   settled the question, drawing a line on a model's gear list named
   after the question rather than after anything owned. Found by query:
   live, not `removes`, naming an old kind, with a settled sibling on
   the same anchor, carrying no money and no worth, nothing hanging off
   it.

   Alone among these operations it *means* to change a page, so it names
   each line beforehand and proves the pages afterwards equal the pages
   before minus exactly those. Which lines go is settled per model and
   name, not per row: one model carries two spares of one name and so
   draws two identical lines, and a page drawing more of a name than
   there are spares to account for means something owned shares it.

7. ~~Delete what is left.~~ Run: 26 kind rows, 22 menu entries, 4 menus,
   6 modifiers and 1 marker, in 182 seconds, proving 107 gangs unmoved.
   Library only, so the proof was that no page moves at all.

   What it left, and why — each said on its own page:
   - the two markers profiles are **built with**. Nobody holding a
     marker is not the same as nothing naming it; only what hands a
     marker over or takes it away goes with it;
   - an offer whose carrier somebody holds, being a question drawn on
     their card, and any menu it still asks from.

   Both had to run after the sweep: deleting a kind row refuses while
   anything names it, and each operation says so by name rather than
   running out of turn.

### Wave 3 — run

8. ~~Re-sync the content mirror from production.~~ Done 2026-08-23:
   38,010 objects, and the mirror now holds the tidy library — five slot
   types, no offers of a retired kind, none of the fossil menus.

   Two things worth knowing for the next sync. The mirror was five
   migrations behind, which is the documented trap and would have failed
   the import; migrate it first. And `loaddata_overwrite` clears only the
   models the fixture names, so the 26 emptied kind rows survived the
   import as orphans — nothing references them, and the wave 5 migration
   drops their tables, so they are left where they are.

### Wave 4 — run

9. ~~Retire the conversion modules and their console operations.~~ Done
   2026-08-23. Eight slugs now registered with no view, the way the
   wargear merge went, so a historical record still reads as a name;
   about 7,000 lines of module and test code deleted, along with the
   `n26_convert` command and the two conversion templates.

   It was checked against the re-synced mirror first: every conversion,
   the sweep and the clearing all read `nothing_here` there, so the code
   really was dead before it went. The one that did not was the pilot
   retirement, which searches by the name "Gang Legacy" — the name the
   *real* slot type now wears. It refused, correctly, because the real
   pickables carry modifiers and the pilot's were hollow. Retiring it
   removes that edge rather than relying on the guard.

### Wave 5 — planned separately

10. **Drop the three kinds and their columns.** Across 21 files and every
   parallel registry the library keeps: `ASSIGNABLE_FIELDS` and the
   Assignment columns, `OFFERABLE_KINDS`, the ingest sheets and their
   four tables, the specs and authoring pages, collection entries, the
   selector algebra, card building, history, sample data — plus a
   migration dropping three columns and three tables. Startup checks
   enforce the registries agreeing, so a half-done version will not
   boot. Nothing stands in the way now: 6, 7 and the sweep left no rows or data, and 8 and 9 have taken the code and the mirror with them.

### After the programme

11. **Gangless models.** Deleting a gang leaves its models behind,
    belonging to nobody and reachable by nothing. The design log records
    that a miniature library — models independent of a gang — was
    considered and dropped, so these are residue of a rejected concept
    rather than intent, even though a test pins the behaviour. Agreed to
    fix after wave 1: delete a gang's models with it, and rewrite that
    test.

## Decisions taken, and why

- **Conversions delete nothing.** Every hard problem in the early
  attempts came from retiring old rows, which is tidiness rather than
  the switch. Tidiness is waves 2 and 5, deliberately separate.
- **A conversion is not a migration.** A migration running live code
  inherits a dependency on every column that code will ever read, and
  the pin needed to say so contradicts the recorded history of a
  database that already ran it. They run from the console after deploy.
- **Repeats are refused per system, not globally.** Skill Trees refuse
  them (the game ranks four different trees); Archetypes allow them (a
  Champion may hold what the gang holds, and ten do). The test is what
  the page said before.
- **The pickables of one system may need a qualifier.** Two names were
  already taken by another slot type's pickables. A qualifier is
  author-facing only and never reaches a player.
- **Deletion in the admin is a superuser's, one at a time.** Writing
  stays refused of everyone; batch delete is gone from the changelists,
  since a column of ticks over ledger events is the same power without
  the page that spells out its cost.

## The discipline these ran on

The full version is in `backfill-lessons.md`. The four that earned
themselves here:

- **Prove the thing that can actually change.** The conversions compare
  pages; the sweep compares histories, because an archived answer draws
  no page. Comparing both would have cost ten minutes of transaction
  for a check that cannot fail.
- **Measure before choosing.** Folding a gang's story costs 287ms;
  building its pages costs 1458ms. That measurement decided the sweep's
  design.
- **Rehearse at the library's real shape.** Running the whole chain on a
  fork of the mirror caught two things no test had: a crash from
  assuming a model names its profile directly, and a marker rule that
  would have deleted markers profiles are built with — stopped only by
  the database's own protection. Both were invisible in a sandbox built
  by hand, because a hand-built world has only what the test remembered
  to put in it.
- **Ask every field, not the ones you remember.** A reverse-relation
  scan misses everything declared `related_name="+"`, which this library
  uses throughout; the first survey read as "nothing references these"
  and was wrong. Scan forward from every model instead.
- **Reproduce the failure your fix fixes.** The double-submit fix was
  nearly shipped against three tests that passed on the unfixed code —
  sequential posts are serialised, so they proved nothing. Only real
  concurrency showed the bug.
- **Say what you leave.** An operation that bounds its own coverage puts
  the remainder on its page, so the next step is not taken in ignorance.

## Traps worth remembering

- `manage prodshell` pipes into IPython, which silently swallows
  multi-line loops and function definitions. Use single-line statements,
  or `exec(open(...).read())` in one line.
- A startup check catches an unregistered background task; the test
  suite cannot, because the development backend skips the registry.
- The shared console page takes its wording from the operation. Two
  operations proving different things must not share one promise.
- `Pickable` names are unique per pack **and qualifier**, not per slot
  type, so a lookup by name alone can match two things.
