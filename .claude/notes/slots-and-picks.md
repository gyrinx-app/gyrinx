# Slots and Picks

A choice a holder makes from a curated list of options, where new domains of
choice are authored, never coded. Supersedes the Hidden-carrying-an-offer
pattern; first use is Gang Legacy. Migrating the existing chosen kinds
(Affiliation, Archetype, SkillTree, Specialisation) is deliberately out of
scope for the first build — the sandbox proves they *could* migrate.

Vocabulary: it is always a **choice**, never a question. A slot's **label**
is what the card calls its choice row. A built-in naming a slot and its
starting pickable is a **slot-with-default**.

## The types

| Type | Summary | Fields of its own | Behaviour |
|---|---|---|---|
| **Slot type** | The domain of a choice: Gang Legacy, Affiliation, Archetype. | name, plural, allows repeats | A top-level entry in the content library: its authoring page lists its pickables, picklists and slots. Ties slot, picklist and pickables together; a mismatch is refused at authoring time. |
| **Pickable** | One option: Cawdor. A named value that carries modifiers. | slot type — plus the shared assignable set (name, annotation, modifiers…) | Never draws a row of its own; it appears only under an assigned slot's choice row. **Without its slot present it shows nothing and its modifiers do not run.** Arrives chosen, or given, or as a slot-with-default's starting value — never as a bare built-in (the authoring form refuses one in words). |
| **Picklist** | A flat, ordered list of pickables of one slot type. | name, slot type; members with an optional label override | No sections, no placement, no prices. The options behind a choice, nothing else. |
| **Slot** | A named use of a slot type: (type, picklist, config). | slot type, picklist, **label**, min picks, max picks, **assigned to** (bearer or the gang — where the pick lands), **hidden**, position | An assignable. Its assignment puts the choice on its host, and the card draws its label with the pick(s) or a Choose control. The choice row draws **only on the host's card** — broadcast applies modifiers and never draws rows. A hidden slot draws nothing at all: the bundle mechanism, replacing the Hidden kind's second job. |
| **Pick** | Not a type — the chosen pickable's assignment. | `chosen_for` → the slot's **assignment** (not the slot row), so repeated slots of one type stay independent | Host per the slot's *assigned to*; cause = the slot's assignment, so removing the slot removes the pick and everything the pickable gives. On the ledger free; carries provenance like any assignment. |

Built-ins may name **a slot** (the choice arrives open) or **a
slot-with-default** (arrives already chosen, changeable by the ordinary
rechoose). A built-in naming a bare pickable is refused: a pickable without
its slot is invisible and inert, so building one in can only be a mistake.

## Rules

- A slot, its picklist, and every member share one slot type; authoring
  refuses a mismatch.
- Choosing writes an ordinary assignment: assignable = the pickable, host
  per the slot's *assigned to*, cause = the slot's assignment, `chosen_for`
  = the slot's assignment. Resolution reads `chosen_for`; nothing is
  inferred by kind-matching.
- The number of picks a slot holds sits between its min and max. Under-min
  is a note on the card ("Gang Legacy — 0 of 1 chosen"), never a refusal.
  The picker stops offering at max.
- Where a slot type refuses repeats: the picker marks options already
  chosen for another slot of that type on the holder, and the card notes a
  duplicate ("Agility is chosen for both skill tree 1 and skill tree 3").
  Marks and notes, never locks — the one hard refusal in the app remains
  the founding budget.
- The narrowing informs and never polices: an owner may still hand over an
  off-list pickable of the right slot type.
- Scopes gain one condition: **has this pickable** — "models with the
  Cawdor pick" — one condition serving every slot type ever authored.
  Effects gain nothing: a pickable's payload is ordinary gives, and a
  pickable may give a further **slot** (the chained choice: picking Clan
  House opens the House choice; un-choosing retracts the chain through
  cause).
- Scopes must be able to say **except**: the Outcast archetype's gang-wide
  payload reaches every model *except* Champions. The condition grammar
  carries a spoken negation for this ("every model except Champion").

## Example A — Gang Legacy, with a default

Slot type *Gang Legacy* (repeats: no). Eight pickables — Cawdor, Escher,
Goliath, Orlock, Van Saar, Delaque, Ironhead Squats, Ogryn — each carrying
one modifier: *gives* that house's equipment list *to the bearer*. Picklist
*Gang Legacies*, all eight. One Slot: (*Gang Legacy*, *Gang Legacies*,
label "Gang Legacy", 1..1, assigned to bearer). Hunter profiles carry the
Slot in their built-ins; the Ironhead Squats profile carries the
slot-with-default (Slot, Ironhead Squats).

The exact option lists, and which profiles carry which slot or default,
are the maintainer's to state before the scenario suites pin them.

Kaustos, hired plain, chooses Cawdor:

    [Hunter profile]    host = the gang   cause = —               (the hire)
    [Gang Legacy slot]  host = Kaustos    cause = the membership
    [Cawdor]            host = Kaustos    cause = the slot's assignment
                        chosen_for = the slot's assignment
    (no row)            House Cawdor Equipment List — computed give,
                        on his equip page at that list's own prices

Grendel, hired from the Squats profile, arrives with the pick already
made — same rows, [Ironhead Squats] written at hire. Changing it is the
ordinary rechoose: the pick is replaced, the slot stays.

## Example B — the Affiliation shape (grounded in prod's Outcast content)

Slot type *Affiliation*. Pickables shaped like the live content — Aranthian
carrying *gives the Aranthian Equipment List to Champion, Ganger and
Leader models*. Picklist *Affiliations*. One Slot: (*Affiliation*,
*Affiliations*, label "Affiliation", 1..1, **assigned to the gang**),
built into the **gang type** — exactly where prod's Outcast built-ins
carry the Affiliation choice today. The choice row draws on the gang's
card only; the pick, gang-hosted, applies its scoped gives to the ranks
it names; no member card grows a row.

Chained: a pickable may give another Slot (Clan House opening a choice of
House), so making the first choice opens the second, and un-choosing
retracts the chain through cause.

## Example C — the Archetype shape (sandbox proof, not a migration)

Slot type *Archetype* (repeats: no). Two Slots over one type:

- (*Archetype*, *Outcast Archetypes*, label "Archetype", 1..1, **assigned
  to the gang**) — built into the leader profile. The choice row draws on
  the leader's card (he is the host); the pick lands on the gang. Its
  payload is scoped **to every model except Champions** — the spoken
  negation the condition grammar carries.
- (*Archetype*, *Champion Archetypes*, label "Archetype", 1..1, assigned
  to bearer) — built into a champion profile. Same type, personal reach.

## Out of scope

- Migrating Affiliation, Archetype, SkillTree, Specialisation. The sandbox
  suites prove the shapes; the migrations come later, one kind at a time.
- Replacing Hidden's bundle job in existing content (hidden slots make it
  possible; nothing moves yet).
- Any change to purchase-time option groups, which keep the word "pick"
  for their own act. On these pages the act is *choose*; the noun Pick
  names the resulting assignment.

## Phasing

0. This document.
1. Fix the noted defects in the existing choice machinery that this build
   subsumes: same-kind resolution inference, the duplicate note's
   gang-card-only reach, the picker not marking taken options.
2. The types, wiring, engine and authoring; Gang Legacy end to end.
3. Sandbox suites for Examples A, B, C, grounded in the rulebook text.
4. Later, separately: migrations of the existing chosen kinds; retiring
   the replaced wirings; the broadcast-machinery clarity work (queued as
   its own conversation).
