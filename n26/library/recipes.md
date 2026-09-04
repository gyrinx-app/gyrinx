# Recipes

How to build specific rulebook setups out of the library's pieces. Each
recipe is a set of steps to follow in the authoring pages — the things to
create, and how to join them. A recipe is written here the day we settle
how its setup is authored, so this page grows with the library.

Where a step is not yet possible, it says so plainly.

## Corrupted gangs

Genestealer Cult, Chaos and Malstrain corruption are one build with
different contents: a corruption is a choice the gang makes once, and
all of its effects come from modifiers attached to the chosen pickable.

### The choice

Use a **slot type** for this gang-level choice. Follow the same six steps
as a Gang Legacy, assigning the pick to the gang.

1. Create a **slot type** named "Variant" — what is being chosen — and
   give it a plural. Turn *allows repeats* off. Everything below is
   built on its page.
2. Add a **pickable** for each corruption — "Genestealer Cult
   Corrupted", "Chaos Corrupted", "Malstrain Corrupted".
3. Add a **picklist** named "Variants" holding those three.
4. Add a **slot** labelled "Variant", taking 0–1 (most gangs leave it
   empty), assigned to the gang.
5. Create a **hidden** if the gang type should carry the question
   without drawing a line of its own, or skip this and attach the grant
   to the gang type directly.
6. On that hidden or gang type: targets the gang, *gives* the Variant
   slot.

Every gang of those types now shows an open "Variant" question on its
sheet. Most players never make that choice. Players who use it make one
pick. The chosen pickable's modifiers provide the effects described
below.

### What a corruption grants

Each effect is a modifier carried by the corruption's pickable: *gives*,
*brings a model*, or *moves a counter*. Do not add these as built-in
items. Pickables are chosen rather than bought or hired, so built-in
items would never be assigned.

**New fighters to hire.** Create the profiles — Aberrant, Abominant,
Helot Cult Witch, Chaos Spawn, Brood Scum. Create a collection listing
them at their prices. On the pickable: targets the gang, *gives* the
collection.

Once a gang carries that collection, its hire page grows a section named
after the collection, holding exactly those fighters at exactly the
prices the collection states — a price written on an entry is what the
row asks and what the gang is charged. A gang without the corruption
sees no such section.

**The Wyrd upgrade.** Create a "Wyrd" **subtype** carrying two modifiers:
*offers a choice* of power from the right Wyrd Powers list, and *puts the
Wyrd Powers category into* the Primary section. List the subtype in the
corruption's collection at 35 credits. A player buys it for their Leader
whenever suits — at hire or later; the book's timing is theirs to honour.

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
pickable: targets the gang, *gives* the rule. They print on the gang's
card.

**Counts and bans.** Each is one modifier on the pickable. For "0–2
Aberrants": targets the gang, *notes a limit*, set to 2, naming the
Aberrant profile — the gang's sheet says nothing until a third one is
hired, and then it says the roster is over. For "no Brutes, Hangers-on or
Pets from your own list": the same again with the limit set to nought,
naming the subtype, and the sheet reads "none allowed" — nought is how a
ban is written. For "up to one Familiar each": target models that are
Leaders or Champions, name the familiar and set the limit to 1; that one is
counted per model and its note lands on the fighter's own card, which is
what "each" means. None of the three refuses anything. A player hires and
buys what they like, and the sheet says where they have gone past the book.

**Losing the gang's own special rules.** This wants a small change to the
gang types themselves, once, and then it is one step per corruption. On
each gang type, create a **hidden** item named for it — "Escher gang
rules" — and put it in the gang type's built-in items. Move the house's
special rules onto it: one *gives* modifier per rule, aimed at the gang.
That is the whole of it — what the gang holds reaches its fighters, so a
rule that improves their weapons or shifts a characteristic does so from
there, and only a rule you want printed on each fighter's card as well
needs a second *gives* aimed at the model. The rules are then granted
rather than built in, so there is a single thing standing behind the lot.
On each corruption's pickable, add *takes something away* naming that
hidden item: aimed at the gang, which is where the item sits, and aimed at
the model too if the fighters' own cards were given rules of their own.
Everything the hidden item was handing out goes with it, and drop the
corruption and it all comes back. Starting Skills and Skill Access live on
the fighter entries, so they are untouched either way.

## A Gang Legacy

> Draft, for review. The shape below is the authoring one; everything in
> square brackets is a fact about the rules rather than about the app,
> and is still to be filled in.

A gang legacy is a choice a fighter makes once, each pickable opening an
equipment list to whoever picks it. The same six steps build any slot
type; this one is worth writing down because it uses all of them.

1. Create a **slot type** named "Gang Legacy" — what is being chosen —
   and give it a plural, so a page can say several of them. Set *allows
   repeats* to [whether one gang may hold the same legacy twice].
   Everything below is built on its page.
2. Add a **pickable** for each legacy: [the legacies the rules give].
3. On each pickable's page, attach a **modifier**: targets the model,
   *gives* that legacy's equipment list. The list is an ordinary
   collection at its own prices, so a fighter who picks a legacy buys
   from that list at that list's prices. [Anything else a legacy grants
   — something scoped to a rank, something reaching the gang — is a
   further modifier on the same pickable.]
4. Add a **picklist** holding what a fighter may choose from. Add more
   than one where [different fighters are offered different legacies]:
   a slot type may have as many picklists as it needs, and a fighter is
   offered exactly the one their slot draws on.
5. Add a **slot** per picklist, labelled "Gang Legacy", taking [how many
   picks], assigned to [the bearer — or the gang, where the pick is the
   gang's and is broadcast to every member, whoever was asked].
6. Build the matching slot into each fighter entry that may take one.
   An entry with no legacy carries no slot at all, and its card asks
   nothing.

A fighter hired from an entry carrying the slot arrives with an open
"Gang Legacy" row on their card. Clicking it offers that picklist;
picking one opens the legacy's equipment list on their equip page and
changes nothing else. The pick is free and adds nothing to the gang's
rating.

A picklist with one pickable on it is still a choice: the row stays open
until the player picks, and nothing is written for them.

To have an entry arrive with its legacy already settled, build the slot
in and name a **starting pick** beside it. The player changes it
afterwards the way they would change any choice.

Two things this build cannot do yet. A gang cannot be given something
for one of its fighters holding a legacy — a condition reads what a
model has, never what anyone in the gang has. And a picklist cannot say
that it is only for a particular moment; it is open whenever the
fighter's equip page is.

## An item one list restricts

Some lists print a restriction beside a line that other lists print
plainly: the Goliath equipment list's "Heavy rock saw (Forge-born only)",
where the Genestealer Cult and Corpse Grinder lists offer the same saw to
anyone. The restriction belongs to that one list's offer.

1. List the item on the collection as usual — one entry, at whatever
   price the list charges.
2. On that entry, name what the book names in the bracket: *offered to
   fighter entries* for "(Forge-born only)", *offered to subtypes* for a
   line the list offers only to Leaders and Champions. Leave it blank on
   every other list that offers the item.

The saw still shows on the list for everyone, marked for the fighters the
list does not offer it to, and an owner may buy it for them anyway.
Nothing is refused — the list says.

Three places a restriction can go, and which one to reach for:

- **On the entry**, as above: one list narrows one of its lines.
- **On the item**, for what is true of it wherever it is listed — a
  saddle no model without a mount can use, however many lists offer it.
  The item's own page asks the same question as *usable by*, and every
  list that offers the item honours the answer.
- **A whole list of its own**, for when the book gives a rank its own
  list rather than restricting lines one at a time. Create the
  collection, and give it to those models with a modifier; every line in
  it is then theirs alone, with nothing to narrow.

## A model with a rolled statline

The Chaos Spawn's Warped Monstrosity: the book rolls a D6 for each of
seven characteristics, and 1, 2–5 or 6 decides the number. The dice
happen at the table; the roster takes the result as hire options.

1. Give the profile the middle band (2–5) as its own printed statline,
   leaving the unrolled columns blank — the card shows a dash.
2. For each rolled characteristic, add an **option group** named for it —
   "Warped Monstrosity: Strength" — with three options: *rolled 2–5*,
   which adds nothing (the printed number stands), and *rolled 1* and
   *rolled 6*.
3. For the 1 and 6 options, create a **hidden** item — "Strength rolled
   6" — carrying a modifier that targets the model and *changes a stat*,
   set to the rolled band's number. Put it in that option's set.

At hire the player picks what they rolled, group by group, and each
shifted cell on the card names what set it. Nothing is enforced: a group
left on 2–5 keeps the printed number, and the card just says.

## One power from a family, as a Primary pick

The Master of Shadow's Master of Whispers, the Psyrender, a bought Wyrd —
one build: a model knows one power of the player's choice from a named
family, and may select more of that family as if they were Primary skills.

1. Create a **category** for the family — "Psychoteric Whispers" — under
   the Wyrd Powers section, and file every power in the family there. A
   power left with no category falls into the collection's default
   section, where no Primary offer can reach it.
2. Have one **collection** — "Skills & Powers" — whose selectors sweep
   *every skill* and *every power*, with the sections every grade is
   written in terms of: Primary, Secondary, and one marked default for
   everything unplaced. Sweeping rather than listing means a power
   authored later joins the surface with no entry to write.
3. On the carrier, create two **modifiers**, both targeting the model:
   *puts the category into a section*, the family into **Primary (Skills
   & Powers)**; and *offers a choice* of **power** from **Primary (Skills
   & Powers)**. The carrier is a **rule** for something a fighter entry
   always has — put the rule in the entry's built-in items — a
   **subtype** for something bought or granted, or the **fighter entry**
   itself.
4. Leave the offer's label blank. Blank derives "Primary power" and files
   the question in the card's **Powers** row, beside the powers the model
   already knows. Any other wording gives the question a row of its own,
   headed by exactly what was written.

The two modifiers are one thing, and the order to think of them in is
placement first: the offer narrows to whatever is Primary *for this
model*, and the placement is what puts the family there. **An offer with
no placement behind it is a question with nothing on it** — the player
clicks Choose and lands on an empty page. The reverse is a real setup
rather than a mistake: place the family and offer nothing, and the model
may select powers from it whenever they like, but was never handed the
founding one.

## The Lasting Injury and Lasting Damage tables

> Draft, for review.

A model taken out of action rolls on a table and keeps the result for
good. There are four tables: the book's Lasting Injury and Lasting
Damage tables (D66), the Spyrer Hunting Rig Glitches a Spyrer's suit
takes instead of injuries (D66), and the delegation injuries an
alliance's models roll (D6). Each is a slot type of its own, so a
fighter can never be handed vehicle damage — and the app never rolls:
the dice are the table's, and a player adds the result they rolled.

1. On **Foundations**, create the **lasting effect tables**. One press
   makes all four tables whole: a slot type each with *allows repeats*
   set — a second Eye Injury is a second Eye Injury — every result at
   its band, and a standing choice each. Each table's own page shows
   every roll covered. (Several results sit on more than one table at
   the same rolls; a pack holds one pickable per name, so the later
   twins arrive with a qualifier, which players never see.)
2. Standard content carries names and numbers only, so finish the
   results that change a number by hand. On each of the ten injury and
   damage results that worsen a characteristic, attach a **modifier** —
   targets the model, worsens that characteristic by one. On each of the
   ten Spyrer glitch results (rolls 51 to 64), attach two: one that
   worsens the characteristic, and one that *moves a counter* — the
   Glitch Count, up by one. A result that changes no number needs
   nothing — the card says the model has it, and the rest is played at
   the table.
3. Put each table's choice on the gang types rather than on the
   entries. Create a **modifier**: reaches *all models in the gang*,
   narrowed to those that *are a Fighter*, and *gives* the Lasting
   Injury choice. Create its twin for vehicles and Lasting Damage. Then
   on the gang types page tick every gang type and attach each one.
   Every fighter in every gang of those types has its empty row from
   that moment — gangs founded long ago included, because nothing is
   written on any model. A gang type created later needs the same two
   attachments.
4. Spyre Hunters are the exception. On that gang type, take the
   fighters' Lasting Injury modifier off and attach two in its place,
   both reaching *all models in the gang* that *are a Fighter*: one
   narrowed to models that have the **Spyrer** subtype, giving the
   Spyrer Hunting Rig Glitches choice; the other narrowed to models
   that do *not* have it, giving Lasting Injury as before. A Spyrer's
   card then asks under Hunting Rig Glitches and never under Lasting
   Injuries.
5. A delegation's models roll on the D6 table. Giving them the
   Delegation Lasting Injuries choice needs a way to reach exactly
   those models; naming their entries one by one on the modifier is the
   only way today, and which entries count is not yet settled.

Taking one of those modifiers off a gang type takes the row off every
card at once, and leaves what players had already picked where it is,
as plain lines they can remove.

The player's picker then lists the results in roll order with their
bands leading, so someone who rolled 24 scans to "21-26" and adds Out
Cold.
