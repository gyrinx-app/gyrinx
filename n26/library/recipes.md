# Recipes

How to build specific rulebook setups out of the library's pieces. Each
recipe is a set of steps to follow in the authoring pages — the things to
create, and how to join them. A recipe is added here once the way to
author its setup is settled, so this page grows with the library.

Where a step is not yet possible, the recipe says so.

## Corrupted gangs

Genestealer Cult, Chaos and Malstrain corruption are one build with
different contents. A corruption is a choice the player makes once for
the gang, and all of its effects come from modifiers attached to the
chosen pickable.

### The choice

Use a **slot type** for this gang-level choice. Follow the same six steps
as a Gang Legacy, and assign the slot to the gang.

1. Create a **slot type** named "Variant" — what is being chosen — and
   give it a plural. Turn *allows repeats* off. Everything below is
   built on its page.
2. Add a **pickable** for each corruption — "Genestealer Cult
   Corrupted", "Chaos Corrupted", "Malstrain Corrupted".
3. Add a **picklist** named "Variants" containing those three.
4. Add a **slot** labelled "Variant", taking 0–1 (most gangs leave it
   empty), assigned to the gang.
5. Create a **hidden** item if the gang type should carry the choice
   without showing a line of its own on the card. Otherwise skip this
   step and attach the modifier to the gang type directly.
6. On that hidden item or gang type, create a **modifier**: targets the
   gang, *gives* the Variant slot.

Every gang of those types now shows an open "Variant" choice on its
sheet. Most players leave it empty. Players who use it make one pick,
and the chosen pickable's modifiers provide the effects described below.

### What a corruption grants

Each effect is a modifier carried by the corruption's pickable: *gives*,
*brings a model*, or *moves a counter*. Do not add these as built-in
items. Pickables are chosen rather than bought or hired, so built-in
items would never be assigned.

**New fighters to hire.** Create the profiles — Aberrant, Abominant,
Helot Cult Witch, Chaos Spawn, Brood Scum. Create a collection listing
them at their prices. On the pickable: targets the gang, *gives* the
collection.

Once a gang carries that collection, its hire page shows a section named
after the collection. The section lists exactly those fighters at the
prices the collection states: the price written on an entry is the price
the gang is charged. A gang without the corruption does not see that
section.

**The Wyrd upgrade.** Create a "Wyrd" **subtype** carrying two modifiers:
*offers a choice* of power from the right Wyrd Powers list, and *puts a
category into a section*, placing Wyrd Powers in the Primary section.
List the subtype in the corruption's collection at 35 credits. A player
can buy it for their Leader at hire or later. The app does not enforce
when the book allows the purchase.

**Familiars.** Create the familiar as **wargear**, usable by Leaders and
Champions, and put it in a collection. On the pickable: targets models
that are Leaders or Champions, *gives* that collection.

**Extra Arm on Prospects.** Create a **wargear** named "Extra Arm" at 20
credits, usable by Prospects, carrying *gives* the Extra Arm rule. List
it in the corruption's collection.

**A god to dedicate to (Chaos).** Create a **slot type** named "Chaos
God" and turn *allows repeats* off. Add a pickable per god, a picklist of
the four, and a slot labelled "Chaos God", taking 0–1 and assigned to
the gang. On the Chaos Corrupted pickable: targets the gang, *gives*
that slot. Attach each god's effects to that god's pickable.

**Post-cycle actions (Chaos).** Create each action as a **rule**. On the
pickable: targets the gang, *gives* the rule. They appear on the gang's
card.

**Counts and bans.** Each is one modifier on the pickable. For "0–2
Aberrants": targets the gang, *notes a limit*, set to 2, naming the
Aberrant profile. The gang's sheet shows nothing until a third Aberrant
is hired, and then shows that the roster is over the limit. For "no
Brutes, Hangers-on or Pets from your own list": the same again, naming
the subtype, with the limit set to 0. The sheet then reads "none
allowed". A limit of 0 is how a ban is written. For "up to one Familiar
each": targets models that are Leaders or Champions, naming the familiar,
with the limit set to 1. That limit is counted per model, and its note
appears on the fighter's own card, which is what "each" means. None of
the three blocks anything. A player can hire and buy what they like, and
the sheet shows where they have gone past the book.

**Losing the gang's own special rules.** This needs a small change to
each gang type, made once, and then one step per corruption. On each
gang type, create a **hidden** item named for it — "Escher gang
rules" — and put it in the gang type's built-in items. Move the house's
special rules onto it: one *gives* modifier per rule, targeting the
gang. What the gang holds reaches its fighters, so a rule that improves
their weapons or changes a characteristic works from there. Only a rule
you also want printed on each fighter's card needs a second *gives*
targeting the model. The rules are then granted rather than built in, so
one item stands behind all of them. On each corruption's pickable, add
*takes something away* naming that hidden item: targeting the gang,
which is where the item sits, and targeting the model too if the
fighters' cards were given rules of their own. Everything the hidden
item granted goes with it. Remove the corruption and it all comes back.
Starting Skills and Skill Access live on the fighter entries, so they
are not affected either way.

## A Gang Legacy

> Draft, for review. The steps below are the authoring steps. Everything
> in square brackets is a fact about the rules rather than about the
> app, and is still to be filled in.

A gang legacy is a choice a fighter makes once. Each pickable opens an
equipment list to the fighter who picks it. The same six steps build any
slot type. This one is written out because it uses all of them.

1. Create a **slot type** named "Gang Legacy" — what is being chosen —
   and give it a plural, so a page can name several of them. Set *allows repeats* to [whether one gang may hold the same
   legacy twice]. Everything below is built on its page.
2. Add a **pickable** for each legacy: [the legacies the rules give].
3. On each pickable's page, attach a **modifier**: targets the model,
   *gives* that legacy's equipment list. The list is an ordinary
   collection at its own prices, so a fighter who picks a legacy buys
   from that list at that list's prices. [Anything else a legacy grants
   — something scoped to a rank, something reaching the gang — is a
   further modifier on the same pickable.]
4. Add a **picklist** containing the pickables a fighter may pick from.
   Add more than one where [different fighters are offered different
   legacies]. A slot type may have as many picklists as it needs, and a
   fighter is offered only the one their slot uses.
5. Add a **slot** per picklist, labelled "Gang Legacy", taking [how many
   picks], assigned to [the bearer, or the gang where the pick belongs
   to the gang and applies to every member].
6. Build the matching slot into each fighter entry that may take one.
   An entry with no legacy carries no slot, and its card shows no Gang
   Legacy line.

A fighter hired from an entry carrying the slot arrives with an open
"Gang Legacy" line on their card. Clicking it shows that picklist.
Picking a legacy opens the legacy's equipment list on the fighter's
equip page and changes nothing else. The pick is free and adds nothing
to the gang's rating.

A picklist with one pickable is still a choice: the line stays open
until the player picks, and nothing is picked for them.

To have an entry arrive with its legacy already picked, build the slot
in and name a **starting pick** beside it. The player can change it
afterwards the way they would change any pick.

Two things this build cannot do yet. A gang cannot be given something
because one of its fighters holds a legacy — a condition checks what a
model has, never what any model in the gang has. And a picklist cannot
be limited to a particular moment. It is open whenever the fighter's
equip page is.

## An item one list restricts

Some lists print a restriction beside an item that other lists print
without one: the Goliath equipment list has "Heavy rock saw (Forge-born
only)", while the Genestealer Cult and Corpse Grinder lists offer the
same saw to anyone. The restriction belongs to that one list's entry.

1. List the item on the collection as usual — one entry, at the price
   the list charges.
2. On that entry, set what the book names in the bracket: *offered to
   fighter entries* for "(Forge-born only)", or *offered to subtypes*
   for an item the list offers only to Leaders and Champions. Leave both
   blank on every other list that offers the item.

The saw still shows on the list for everyone. It is marked for the
fighters the list does not offer it to, and an owner can still buy it
for them. Nothing is blocked: the list shows the restriction.

A restriction can go in three places:

- **On the entry**, as above, when one list restricts one of its items.
- **On the item**, when the restriction is true wherever the item is
  listed — a saddle that only a mounted model can use, however many
  lists offer it. Set *usable by* on the item's own page, and every
  list that offers the item applies it.
- **A whole list of its own**, when the book gives a rank its own list
  rather than restricting items one at a time. Create the collection
  and give it to those models with a modifier. Every item in it is then
  offered only to them, with nothing to restrict.

## A model with a rolled statline

The Chaos Spawn's Warped Monstrosity: the book rolls a D6 for each of
seven characteristics, and a result of 1, 2–5 or 6 decides the number.
The player rolls at the table and records the result as hire options.

1. Give the profile the middle band (2–5) as its printed statline,
   leaving the columns the book does not roll blank — the card shows a
   dash for those.
2. For each rolled characteristic, add an **option group** named for it —
   "Warped Monstrosity: Strength" — with three options: *rolled 2–5*,
   which changes nothing (the printed number stands), *rolled 1*, and
   *rolled 6*.
3. For the 1 and 6 options, create a **hidden** item — "Strength rolled
   6" — carrying a modifier that targets the model and *changes a stat*,
   set to that band's number. Put it in that option's set.

At hire the player picks what they rolled, group by group. Each changed
cell on the card names what changed it. Nothing is enforced: a group
left on 2–5 keeps the printed number, and the card shows the result.

## One power from a family, as a Primary pick

The Master of Shadow's Master of Whispers, the Psyrender and a bought
Wyrd are one build: a model has one power of the player's choice from a
named family, and may select more powers from that family as if they
were Primary skills.

1. Create a **category** for the family — "Psychoteric Whispers" — under
   the Wyrd Powers section, and file every power in the family
   there. A power with no category falls into the collection's default
   section, which no Primary offer can reach.
2. Have one **collection** — "Skills & Powers" — whose selectors include
   *every skill* and *every power*. Give it the sections the grades are
   written in terms of: Primary, Secondary, and one marked default for
   everything not placed. Using selectors rather than entries means a
   power authored later joins the collection with no entry to write.
3. On the carrier, create two **modifiers**, both targeting the model:
   *puts a category into a section*, placing the family in **Primary
   (Skills & Powers)**; and *offers a choice* of **power** from
   **Primary (Skills & Powers)**. The carrier is a **rule** for
   something a fighter entry always has — put the rule in the entry's
   built-in items — a **subtype** for something bought or granted, or
   the **fighter entry** itself.
4. Leave the offer's label blank. A blank label reads "Primary power"
   and puts the choice in the card's **Powers** line, beside the powers
   the model already has. Any other label gives the choice a line of its
   own, headed by that label.

The two modifiers work together, and placement comes first: the offer is
limited to whatever is Primary *for this model*, and the placement is
what puts the family there. **An offer with no placement behind it is a
choice with no options** — the player clicks Choose and lands on an empty
page. The reverse is a valid setup rather than a mistake: place the
family and offer nothing, and the model may select powers from it at any
time but is not given a first one.

## The Lasting Injury and Lasting Damage tables

> Draft, for review.

A model taken out of action rolls on a table and keeps the result
permanently. There are four tables: the book's Lasting Injury and
Lasting Damage tables (D66), the Spyrer Hunting Rig Glitches table a
Spyrer's suit rolls on instead of injuries (D66), and the delegation
injuries table an alliance's models roll on (D6). Each is a slot type of
its own, so a fighter can never be given vehicle damage. The app never
rolls. The player rolls at the table and adds the result they rolled.

1. On **Foundations**, create the **lasting effect tables**. One click
   creates all four tables in full: a slot type each with *allows
   repeats* on — a second Eye Injury is a second Eye Injury — every
   result at its band, and a standing choice each. Each table's own
   page shows every roll covered. (Several results appear on more than
   one table at the same rolls. A pack has one pickable per name, so
   the later copies are created with a qualifier, which players never
   see.)
2. Standard content carries names and numbers only, so finish the
   results that change a number by hand. On each of the ten injury and
   damage results that worsen a characteristic, attach a **modifier**:
   targets the model, worsens that characteristic by one. On each of
   the ten Spyrer glitch results (rolls 51 to 64), attach two: one that
   worsens the characteristic, and one that *moves a counter* — the
   Glitch Count, up by one. A result that changes no number needs
   nothing — the card shows that the model has it, and the rest is
   played at the table.
3. Put each table's choice on the gang types rather than on the
   entries. Create a **modifier**: targets *all models in the gang*,
   narrowed to those that *are a Fighter*, and *gives* the Lasting
   Injury choice. Create a matching one for vehicles and Lasting Damage.
   Then on the gang types page, tick every gang type and attach both.
   Every fighter in every gang of those types has its empty line from
   that moment — gangs founded long ago included, because nothing is
   written on any model. A gang type created later needs the same two
   modifiers attached.
4. Spyre Hunters are the exception. On that gang type, remove the
   fighters' Lasting Injury modifier and attach two in its place, both
   targeting *all models in the gang* that *are a Fighter*: one
   narrowed to models that have the **Spyrer** subtype, giving the
   Spyrer Hunting Rig Glitches choice; the other narrowed to models
   that do *not* have it, giving Lasting Injury as before. A Spyrer's
   card then shows a Hunting Rig Glitches line and never a Lasting
   Injuries line.
5. A delegation's models roll on the D6 table instead, and the swap is
   made on the models themselves rather than on the gang types. Create
   a **hidden** item named "Delegation" carrying two modifiers, both
   targeting *the model carrying it*: one *takes something away*, the
   Lasting Injury choice; the other *gives* the Delegation Lasting
   Injuries choice. Then build it into each delegation entry — the
   fighters under the Allies gang type. A delegation model's card then
   shows a Delegation Lasting Injuries line and never a Lasting Injuries
   line, in any gang, and every gang type's own modifiers stay as they
   are. Anything else the alliance rules give a delegation belongs on
   the same hidden item. An entry added to the Allies list later needs
   it built in too.

6. What a result does to the model's standing is a modifier on the
   result too, and Foundations attaches these for you: Grievous Wound
   and the 51–56 injuries put the model **In Recovery**, Critical Injury
   marks it **Critically Injured**, Memorable Death marks it **Dead**,
   and Captured marks it **Captured** and gives it an **Escape** choice —
   a D6 table of its own (Executed, Ransomed, Daring Escape), each result
   setting the status in turn. The card wears the status under the
   model's name; the owner can set it by hand from the card's menu, and
   Clean House on the gang's menu clears every Recovery at the end of a
   cycle. Taking a result off the card does not undo the status.

Removing one of those modifiers from a gang type removes the line from
every card at once. Results players had already picked stay where they
are, as plain lines the player can remove.

The player's picker lists the results in roll order with the band first,
and offers to roll. Clicking Roll rolls the die and writes the roll to
the gang's history before anything is picked; the page comes back showing
the dice and lifts the result the roll landed on to the top, with the
rest of the table beneath it. A player who rolled at the table enters the
number instead and gets the same page, with the record saying the roll
was entered. Adding a result from that page ties the pick to the roll,
and a roll is applied once — a second roll is a second line in the
history, whether or not the first was used. The result the roll landed on
is shown, never enforced: a rule that says a result counts as Out Cold is
followed by adding Out Cold, and the history shows the roll beside it.
