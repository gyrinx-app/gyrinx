# Converting Affiliation onto slots and picks

An evaluation, not a plan to run. Measured from production on
2026-08-27, read-only. The other four chosen kinds have already moved;
Affiliation is what is left. The how — one flip per system, then a
batched check — is
[`affiliation-conversion-plan.md`](affiliation-conversion-plan.md).

**It should move.** Not as one slot type named Affiliation covering
everything the kind currently holds — as three systems, the same split
Gang Legacy and Archetype already took. The kind is a bucket. The
systems are distinct. Converting them as one Affiliation would keep the
vocabulary lie the slots work existed to retire.

n23 is out of scope. Nothing here reads or writes it.

## Why it was considered, and why it was dropped

Slots and picks shipped as #2177 with this as a known later job:

> Content authors were repurposing Affiliation as a general-purpose
> labelled assignable because every new named-value type cost an
> engineering change.
>
> Migrating the existing chosen kinds (Affiliation, Archetype,
> SkillTree, Specialisation) is out of scope here by design.

A survey on the `chosen-kinds-plan` branch (never merged) then mapped
**eight** authored systems across those four kinds. Affiliation the
kind was four of them: Cawdor Paths, Variants, Chaos God, and Outcast
Affiliation (with a Clan House chain). The other four sat on Archetype,
SkillTree and Specialisation.

What actually ran was five conversions, then the programme was declared
done:

| # | system | kind it sat on | ran? |
|---|---|---|---|
| 1 | Cawdor Paths | Affiliation | yes — the pilot, #2214 |
| 2 | Specialisation | Specialisation | yes |
| 3 | Variants | Affiliation | **no** |
| 4 | Chaos God | Affiliation | **no** |
| 5 | Outcast Affiliation + Clan House | Affiliation | **no** |
| 6 | Outcast Archetype | Archetype | yes |
| 7 | Venator Skill Trees | SkillTree | yes |
| 8 | Venator Gang Legacy | Archetype (hack) | yes |

#2287 then deleted the conversion machinery (~7,000 lines) with the
claim that every hand-built choice system had moved. Affiliation stayed
on the authoring menu as the remaining chosen-carrier kind; the
sandbox's stand-in after the other three retired; the recipes' word for
a gang-level choice (corruption, a god, an alliance).

Three reasons that skip was the right call *then*, and are weaker now:

1. **Variants was next, and Variants deletes.** The original order put
   Variants after Specialisation. Specialisation's first attempt retired
   old rows and failed; the standing rule became *delete nothing*.
   Variants' original write-up deleted the "None" affiliation's picks
   (82 live then, **187 now**) in favour of `min_picks=0`. That is the
   one lossy step in the whole map, and it sat on the far side of a
   lesson just learned the hard way.
2. **The three leftover systems chain.** Chaos Corrupted is a Variant
   pick that offers Chaos God; Clan House is an Affiliation pick that
   offers a house. Converting one without the others leaves a chain
   half on each machinery. Paths, Specialisation, Skill Trees, Gang
   Legacy and Archetype were each a closed system.
3. **The kinds they wanted gone were the borrowed ones.** Archetype had
   been used for Gang Legacy; SkillTree and Specialisation were
   retiring. Affiliation is the honest kind for Outcast affiliation, so
   keeping it as a generic chosen-carrier looked cheaper than splitting
   it.

What has changed: the engine is proven, the other kinds are gone, and
Affiliation is now the last `OffersChoice` chosen-carrier (skill and
power remain, and should — they are not labelled-assignable hacks).
Every new gang-level choice still has to be an Affiliation or a new
coded kind. That is the situation slots were built to end.

## What is there

18 live Affiliation rows, 0 archived, one pack. Four menus, seven
offers, 410 live picks on 359 gangs, 101 archived picks. Every live
pick is gang-hosted and has `caused_by` set. No pickable already uses
any of these names, and no slot type is named Affiliation, Variant, or
Chaos God.

The 51 gangs that hold two live affiliations are all chains — Clan
House plus a house, or Chaos Corrupted plus a god — not doubled
answers.

### System 1 — Outcast Affiliation (the original)

Hidden **"Affiliation"** built into gang type **Outcast** (116 live
assignments; 119 live foundings). Gang-scoped offer, label
"Affiliation", menu *Affiliations*: Clanless, Clan House, Mutant,
Aranthian. The pick lands on the gang.

| pick | live | payload |
|---|---|---|
| Clan House | 25 | offers Clan House from *Clan House* / Clan Houses |
| Mutant | 23 | Mutations list to Champion or Ganger or Leader |
| Clanless | 19 | nothing (Trade Points are still parked) |
| Aranthian | 12 | Aranthian list to Champion or Ganger or Leader, *and* to the gang alone |

**Chained:** Clan House carries a gang-scoped offer, label "Clan House",
menu of the six houses. Each house opens that house's equipment list to
Champion or Leader, and to the gang alone. 22 live house picks; three
Clan House gangs have not picked a house. **House Goliath has never
been picked.**

The house rows carry qualifier `"Affiliation"` (so the authoring label
reads `House Cawdor — Affiliation`). The printed name is `House
Cawdor`. No pickable collides with that.

⚠ Aranthian's list still names Gangers. The rules say Leaders and
Champions only — flagged in the original survey, still uncorrected.

Fossils, neither held by anyone: a whole-kind Affiliation offer
(unlabelled), and a "Corruption" offer from the Affiliations menu
landing on the bearer.

### System 2 — Variants

One shared modifier **"Offer Variants"**, label "Variant", menu
*Variants*: Chaos Corrupted, Genestealer Cult Corrupted, Malstrain
Corrupted, and **"None"**. Carried by seven gang types (Cawdor, Delaque,
Escher, Goliath, Orlock, Palanite Enforcers, Van Saar) and by a
vestigial hidden **"Variant"** that nothing builds in and nobody holds
(0 live assignments).

`will_be_assigned_to` is **bearer**. That is not a contradiction: the
carrier is the gang type, hosted on the gang, so the bearer *is* the
gang. Every Variant pick in production is gang-hosted. A converted slot
must land the same way — `assigned_to="gang"`, granted by those seven
gang types.

| pick | live | on which types (live foundings in parens) |
|---|---|---|
| None | 187 | Cawdor 38 (177), Escher 34 (255), Enforcers 29 (214), Van Saar 28 (186), Delaque 25 (152), Orlock 17 (135), Goliath 16 (197) |
| Chaos Corrupted | 33 | spread across all seven |
| Malstrain Corrupted | 18 | Goliath 6, the rest 1–3 |
| Genestealer Cult Corrupted | 14 | Enforcers 3, the rest 1–3 |

"None" is 45% of all live affiliation picks, and the explicit
nothing-option the offer cannot otherwise express. An unanswered
optional slot (`min_picks=0`) says the same thing on the page; the
picker already has a None row for optional choices. The original map
deleted these picks. That is still the right page, and it is still the
one step that *means* to change the ledger (187 live, 17 archived).

Payloads, all riding the corruption itself:

- each corruption **gives** its collection to the gang and to all
  models (Chaos and GSC say it twice; Malstrain the same shape)
- each **gives** a hidden that strips the house's special rules
- each **removes** Gang Brutes and Pets (one shared modifier)
- Chaos Corrupted additionally **offers Chaos God** (the chain)

House types do **not** carry Variant in their built-ins. The offer
rides the gang type as a modifier, the same shared-offer pattern Gang
Legacy used across twelve profiles. Cawdor therefore asks two gang
questions: Path (already a slot, granted by hidden "Path") and Variant
(still an Affiliation offer on the gang type).

### System 3 — Chaos God (two doors, one menu)

Menu *Chaos Gods*: Architect of Fate, Blood God, Dark Prince, Plague
Lord. All four carry **no payload**; the pick is a record. Two offers,
both labelled "Chaos God", both `will_be_assigned_to=bearer`, both
landing on the gang in practice:

- granted by **Chaos Corrupted** (the Variant chain) — 28 of the 33
  Chaos Corrupted gangs have picked a god
- hidden **"Chaos God — Helots"** built into **Chaos Helot Cult** (78
  live assignments; 81 live foundings) — 29 god picks, so most Helot
  gangs have not answered

| pick | live | of which on Helot Cult |
|---|---|---|
| Dark Prince | 26 | 9 |
| Architect of Fate | 12 | 11 |
| Plague Lord | 11 | 6 |
| Blood God | 8 | 3 |

One slot type, two slots, same list. Repeats do not arise: a gang is
not both a Helot Cult and a corrupted house.

## The behaviour that must survive

1. **Outcast: founding asks Affiliation; the pick is the gang's.** The
   hidden stays as the anchor. The slot is granted by it, the pick
   keeps `caused_by` the hidden's assignment, and removing the hidden
   (or the gang type) retracts the pick.
2. **Clan House opens a second question, and only while it is the
   pick.** Un-choosing Clan House takes the house slot, the house pick,
   and the house list with it. Already proven in
   `test_outcast_affiliation_shape.py`.
3. **A house list reaches Leaders and Champions, not Gangers.** Move
   the modifiers wholesale. Do not "fix" Aranthian onto this; say it
   on the page if the Ganger reach is kept, or correct it as a named
   content change with a capture exception.
4. **Variant is optional and mostly unanswered.** "None" and an open
   `min_picks=0` slot must read the same on every page that currently
   shows "Variant: None". The offer never nagged; the slot must not
   either. Paths taught this — the capture check caught `min_picks=1`
   on the first rehearsal.
5. **A corruption suppresses house rules and opens its own lists.**
   The modifiers move with the pickable in the same transaction as the
   rewrite. Shared modifiers (Brutes/Pets removal, the rules-stripping
   hidden) stay shared.
6. **Chaos Corrupted is what asks the god question.** Helot Cult asks
   it independently via its own hidden. Two grants of one slot type,
   not two types.
7. **Every pick stays gang-hosted.** No affiliation pick has ever
   landed on a model. `assigned_to="gang"` throughout.

## The shape

```
# System 1
create slot type "Affiliation", refusing repeats
create pickables Clanless, Clan House, Mutant, Aranthian
  (move their modifiers; Clan House's offer becomes a grant of the house slot)
create picklist "Affiliations"
create slot "Affiliation", landing on the gang, 1..1
on hidden "Affiliation": replace the offer with a grant of that slot
create slot type "Clan House", refusing repeats
create pickables House Cawdor … House Van Saar (qualifier "Affiliation" if
  a name collides; none does today)
create picklist "Clan Houses"
create slot "Clan House", landing on the gang, 1..1
  granted by the Clan House pickable
rewrite 79 Outcast + 22 house picks

# System 3 — before Variants, both doors
create slot type "Chaos God", refusing repeats
create pickables Architect of Fate, Blood God, Dark Prince, Plague Lord
create picklist "Chaos Gods"
create slot "Chaos God", landing on the gang, 0..1
  on hidden "Chaos God — Helots"
create slot "Chaos God", landing on the gang, 0..1
  on the Chaos Corrupted affiliation (both doors in this run;
  neither nags — the offers did not)
rewrite 57 god picks

# System 2 — last
create slot type "Variant", refusing repeats
create pickables Chaos Corrupted, Genestealer Cult Corrupted, Malstrain Corrupted
  (not None; move modifiers, including Chaos Corrupted's Chaos God grant)
create picklist "Variants"
create slot "Variant", landing on the gang, 0..1
on the seven gang types: replace "Offer Variants" with a grant of that slot
rewrite 65 corruption picks
archive 187 live "None" picks (and 17 archived); pages capture equal
  under a conversion-local comparator
```

Nothing of the old kind is deleted in these runs. The 18 Affiliation
rows, the four menus, the two unattached offers, and the Variant hidden
stay until a later cleanup, the way the other conversions left their
emptied rows.

### Why three slot types, not one

The card already says three different words: Affiliation, Variant,
Chaos God. History currently says "affiliation" for all of them,
because that is the kind column. A pick's kind word after conversion
is the **slot type's name**, not the slot's label — that is how Gang
Legacy stopped being an Archetype in the story.

One Affiliation slot type would leave history untouched and keep the
lie. Three types reword Variant and Chaos God (and Clan House) picks
from "affiliation" to the word the card already uses. That is the Gang
Legacy precedent, and it is the one the archived-answer sweep had to
declare: 34 of 399 answers moved a word, the page said so, and every
other word that would have moved was a refusal.

Declare the rewording on each system's page. Pin it with a story test.
Do not fold Variant into Affiliation to avoid the reword.

## Decisions, taken

Locked in the conversion plan. Short form:

**"None".** Archive the 187 live (and 17 archived) picks, slot
`min_picks=0`. An open optional Variant and a picked None capture
equal under a conversion-local comparator. Preview names every gang
whose stored answer is cleared.

**Aranthian Gangers.** Keep the modifier as authored. Do not silently
fix it inside the rewrite.

**Clan House as its own slot type.** Yes.

**Repeats.** All four types (Affiliation, Clan House, Variant, Chaos
God) refuse them.

**The four Leader-style copies.** There aren't any.

**Runner.** One write per system: create, move modifiers, swap, rewrite
every pick, in one transaction, with the reached gangs locked. Prove a
spread in that transaction and unwind on a diff. Reconcile every reached
gang in that same transaction. No dual-read, no per-gang flag, no
dormant slots.

## Engine work

Nothing new in the player engine. `_choose_for_slot` already routes a
pick to the gang when the slot says so; chained grants already retract
through cause; optional slots already offer a None row; `has_pickable`
already exists (and is the condition Affiliation never had — today
nothing can say "models whose gang picked Malstrain" except by hanging
the behaviour on Malstrain itself).

Put back a small `n26.library.conversion` — frozen plan, typed steps,
one apply — not the 7,000-line module #2287 deleted. Console operations
call it through `_run_recorded`. Capture
(`n26.core.capture.gang_state`) is still here.

Authoring already refuses a bare pickable built in. Recipes and
`concepts.md` still teach Affiliation as the way to author a gang-level
choice; those rewrite after the first system lands, not before.

`OFFERABLE_KINDS` still names `affiliation`. It shrinks when the last
offer is gone, in the cleanup, not in the first conversion.
`ENTRY_ASSIGNABLE_FIELDS` still names it for the same reason. The
Assignment column stays until the kind is dropped, the way Archetype's
did.

There is no Affiliation ingest sheet. Nothing to delete there.

## The proof

Sandbox first, then a fork of the content mirror at the measured
volume.

Per system, the suite that already exists is the shape to follow:

- `test_outcast_affiliation_shape.py` already builds system 1 on slots
  and plays it through the pages. Convert the *live* content to match
  that suite; do not rewrite the suite to match a different shape.
- `test_outcast_affiliation_flow.py` and `test_outcast_gang.py` still
  build the old kind. They move onto slots the way #2307 moved the
  Archetype/SkillTree/Specialisation suites — assertions unchanged.
- `test_gang_books.py` builds Chaos corruption as an Affiliation. It
  follows system 2.

Then the standing rule: the write captures a spread and unwinds on any
difference (None equals unanswered Variant under a conversion-local
comparator; Aranthian is not an exception). Every reached gang
reconciles in that transaction, and again on a batched walk after it
commits. On a fork, every reached gang's pages are diffed from outside
the run. History is pinned per system with a same-words test, plus a
declared-rewording test for Variant, Chaos God, and Clan House.

Volume, so the sample can be sized:

| system | live picks | gangs (approx.) | archived |
|---|---|---|---|
| Outcast Affiliation | 79 | 119 foundings, 79 answered | 34 |
| Clan House (chain) | 22 | 22 of the 25 Clan House gangs | 7 |
| Variant (corruptions) | 65 | 65 | 33 |
| Variant "None" | 187 | 187 | 17 |
| Chaos God | 57 | 28 corrupted + 29 Helot | 10 |
| **total live to rewrite** | **223** (plus 187 Nones to clear) | **359** gangs hold at least one | **101** |

Smaller than Specialisation (939) and in the Gang Legacy / Archetype
band. The expensive gang is the one that holds a chain (Clan House +
house, or Chaos Corrupted + god). Prove those shapes; do not prove
every None.

## Order of battle

The conversion plan is the authority on the apply. Short form:

1. **Machinery, no system** — small conversion module, apply helper,
   spread capture, batched reconcile. No Affiliation row is rewritten.
2. **Outcast Affiliation + Clan House.** Independent of the others,
   sandbox already green, no None, no shared-across-types offer. The
   chain is the thing to prove. 101 picks rewritten.
3. **Chaos God, both doors**, before Variants. Empty pickables,
   `min_picks=0` on Helots *and* on the Chaos Corrupted grant (the
   inner offer never nagged either).
4. **Variants**, which moves the already-swapped Chaos God grant onto
   the Chaos Corrupted pickable. The "None" clearing is this system's
   declared ledger change. Shared modifier on seven gang types;
   `SwapSharedCarrier` with `reach=gang_alone`.
5. **Cleanup, later, separate.** Empty the 18 kind rows, the four
   menus, the two fossil offers, the Variant hidden. Drop Affiliation
   from `OFFERABLE_KINDS`, `LEAF_KINDS`, `ENTRY_ASSIGNABLE_FIELDS`,
   recipes, concepts. Then drop the model and the Assignment column,
   the way #2314 dropped Archetype/SkillTree/Specialisation.

Do not convert all three in one operation. One PR and deploy per
system, same as last time.

## What would make this the wrong next step

- Rebuilding the runner for a single leftover kind, if Affiliation is
  going to stay as the generic chosen-carrier on purpose. That is a
  product decision: either authors make new slot types, or they keep
  making Affiliations. The recipes currently teach the latter.
- Folding Variant and Chaos God into one Affiliation slot type to
  "finish the column" without splitting. That ships the conversion and
  keeps the hack.
- Deleting the kind in the same PR as the first rewrite. Every early
  failure came from that.

If the decision is that Affiliation remains the authored chosen-carrier
for new gang-level choices, stop here: the three systems can stay, the
column can stay, and slots are for new domains only. That is a coherent
position. It is also how we got Gang Legacy stored as Archetype.

The recommendation is the split, system 1 first, one flip each. See
[`affiliation-conversion-plan.md`](affiliation-conversion-plan.md).
