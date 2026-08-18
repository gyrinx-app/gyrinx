# Archetype today — what the column holds, and why

Written before the Archetype conversion, from the content mirror, the
production database (read-only), `n26/design/outcasts.md`, and the
sandbox suites. Counts are production, 2026-08-18.

## The headline

The `archetype` column holds **two unrelated systems** that happen to
share a kind: the Outcast archetypes (the system the kind was built
for) and the Venator "House Legacies" (a different concept that
borrowed the kind because it was there). 164 live picks across 69
gangs, split almost exactly in half — 83 Outcast, 81 Venator.

A third implementation is also standing: the **Gang Legacy slot type**
(the slots-and-picks pilot), with 2 pickables, 2 gangs holding the
slot, 2 answers — and **its pickables are empty**: no modifiers, no
linked category. A gang that answered the pilot slot got nothing;
a gang that answered the archetype offer got the house equipment list.

## System 1 — Outcast archetypes (the designed one)

Five heavy rows — Brawler, Gunslinger, Mastermind, Survivor, Wyrd —
each carrying its whole printed table as 10–11 modifiers:

- fixed `PlacesCategory` rows per rank ("Brawler: Leader models —
  Combat is Primary"), hung off the shared rank subtypes so every
  profile variant receives them;
- the Champion rows scoped **bearer-only** ("(own pick)") — inert in
  the gang's radiated copy, active only on a Champion who picked it
  personally;
- Wyrd additionally grants the Wyrd subtype per rank and places Wyrd
  Powers under Primary.

This is the deliberate design (`design/outcasts.md`, decided
2026-08-06): where a Venator skill-tree slot carries the meaning and
the pick contributes one datum, an Outcast archetype token **knows its
whole payload** — no indirection, one carrier per printed archetype,
the whole table aboard.

### The leader/champion behaviour, precisely

Two offers, two hosts:

1. **The gang's archetype.** "Chosen when a Leader is recruited": the
   Leader *profile* carries the offer, and the answer lands **on the
   gang** (`will_be_assigned_to="gang"` was added for exactly this).
   The pick is a gang row *caused by the Leader's own assignment*, so
   it radiates to every fighter through the ordinary broadcast and
   **dies with the Leader** through the caused-by cascade. This
   superseded an earlier gang-built-in-slot draft, deliberately: the
   cascade is what makes "chosen when a Leader is recruited" data
   rather than prose. 35 live picks sit on gangs this way.
2. **A Champion's own archetype.** "All models except Champions;
   Champions may choose a different Archetype": the Champion profile
   carries its own offer landing on the **bearer**. The token's
   bearer-only rows are what a Champion gets from their personal pick.
   48 live picks — Champions answer more often than Leaders.

### The wart in system 1

There are **four Outcast Leader profiles** ("Leader 1"–"Leader 4", all
135cr — the printed list's four builds), and the gang-archetype offer
is **duplicated four times, one copy per profile**. Four identical
modifiers saying "chooses the gang's Archetype". Meanwhile the
archetype *tables* hang off the one shared Leader subtype. So the
content already knows the right factoring for the payload but not for
the question. Contrast the Venator side, where one offer modifier is
shared across all twelve profiles — the same authoring decision made
both ways in one library.

Four copies means four questions that are really one: each Leader
profile's line asks its own copy, and only the cascade's practical
shape (one Leader hired) keeps a gang from being asked twice. A gang
that hires two Leaders (owner freedom — nothing polices it) gets two
live archetype questions.

## System 2 — Venator "House Legacies" (the borrowed kind)

Seven light rows — Cawdor, Delaque, Escher, Goliath, Ironhead Squat,
Orlock, Van Saar — each carrying exactly one modifier: *adds that
house's equipment list to the bearer*. That is the entire payload
("really all it gives is access to an equipment list").

One offer modifier, shared by all **twelve** Venator hunt profiles
(House Hunt Leader 1–4, House Hunt Champion 1–4, House Hunter 1–4),
labelled **"Gang Legacy"**, narrowed to the "House Legacies" menu,
landing on the **bearer** — each fighter takes their own legacy.
81 live picks. (Ironhead Squat has never been picked.)

Why it is an Archetype: when this was authored the Gang Legacy concept
had no kind of its own, `Archetype` was the nearest chosen-carrier
kind, and the label override ("Gang Legacy") papered over the name.
The card says "Gang Legacy: Van Saar" while the database says
Archetype — the vocabulary and the storage disagree.

There is also **one fossil**: a detached duplicate of the offer
("House Hunt Leader 1: offers a choice of archetype from House
Legacies") that no carrier holds. It does nothing on any page.

## System 3 — the Gang Legacy slot pilot (standing, hollow)

`SlotType "Gang Legacy"` (repeats refused), picklist "All Gang
Legacies" with **two** pickables (Cawdor, Ironhead Squat), one slot,
nothing granting it — the two gangs holding it were assigned the slot
directly. Both answered. **The pickables carry no payload**: no
equipment-list grant, no linked category. The two pilot answers
display a choice that does nothing the archetype twin would do.

## What was decided (2026-08-18, after discussion)

- **The pilot retires, nothing reuses it** — a dedicated audited
  maintenance operation deletes it whole (the admin refuses the
  cascade and the UI cannot; this is the sanctioned backfill route).
  The Gang Legacy conversion refuses while any pilot remnant stands.
- **The conversion builds fresh Gang Legacy machinery** from the offer
  and its menu — which lists **six** houses, not seven: Ironhead Squat
  was never offered (its pilot pickable was evidently the start of
  Squat legacies on the new system). Re-offering Squat legacies is
  content work after conversion, as is extending the new slot grant to
  the three Squat Hunt profiles, which today carry no legacy question.
- **Outcast Leader offers stay per-profile** when that half converts.
- **The gang's archetype reaches every fighter except Champions; a
  Champion's own pick affects only them.** The content already builds
  this (bearer-only Champion rows) and any conversion preserves it by
  moving modifiers wholesale.
- History turns out to change nothing: these picks stand as their own
  acts and never draw a kind word, pinned by the story tests.

## The original proposal (superseded above)

Two systems, so **two conversions** — and they are different shapes:

1. **House Legacies → the Gang Legacy slot type**, finishing what the
   pilot started: seven pickables (created from the archetype rows,
   moving their one equipment-list modifier each), the picklist grown
   from 2 to 7, the twelve profiles' one shared offer swapped for a
   grant of a per-model slot, 81 picks rewritten. The two hollow
   pilot pickables must gain their payload (or be replaced), and the
   two pilot answers must end up indistinguishable from converted
   ones. This also retires the vocabulary lie: the thing called
   "Gang Legacy" on cards stops being an Archetype underneath.
2. **Outcast archetypes → an "Archetype" slot type.** The tokens'
   payloads move to pickables wholesale (the modifiers move; the
   bearer-only Champion rows ride along unchanged). Two slots: the
   gang's (granted by the Leader — see below) and the Champion's
   personal one. The pick-lands-on-gang and dies-with-the-Leader
   behaviour must survive conversion exactly: the rewritten pick keeps
   its `caused_by` (the Leader's line), so the cascade is untouched.

The **fix-while-migrating** candidate for the leader wart: the four
per-profile offer copies become **one** slot grant carried by the
shared Leader subtype — the same factoring the tables already use.
That changes where the question is anchored (subtype assignment vs
profile assignment), so the existing 35 gang picks' `caused_by` would
need re-anchoring — or the four copies become four grants of the
*same* slot (no re-anchoring, wart preserved but harmless: same slot,
same question). The second is the conversion-safe choice; the first
is the content fix. Decide before building.

Open questions:

- Does the Champion's personal slot and the gang's slot share one
  "Archetype" slot type (repeats allowed — a Champion may legitimately
  duplicate the gang's archetype) or two types? One type, repeats
  allowed, looks right — the doubled-pick note must not fire when a
  Champion picks what the gang has.
- The chosen-mode machinery is untouched here — no `the_chosen`
  placements read archetype picks, so no linked categories are needed:
  every payload is ordinary modifiers on the pickable.
- The Venator slot is per-model ("Gang Legacy" on each hunt fighter);
  its grant rides the twelve profiles (or their shared subtype, if one
  exists — check before building).
