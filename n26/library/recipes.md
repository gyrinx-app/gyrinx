# Recipes

How to build specific rulebook setups out of the library's pieces. Each
recipe is a set of steps to follow in the authoring pages — the things to
create, and how to join them. A recipe is added here once the way to
author its setup is settled, so this page grows with the library.

Where a step is not yet possible, the recipe says so.

## A weapon that grants wargear

To make slashing claws grant a grapnel launcher and a drop rig:

1. Create the **weapon** and the two **wargear** items, or open their
   existing entries.
2. On the weapon's page, create a **modifier**. Select **The model
   carrying it** and **Gives something**.
3. Set **Kind** to **wargear**, select the grapnel launcher, and save.
4. Add a second modifier with the same scope and effect, selecting the
   drop rig.

The model's card shows both items while it holds the claws, including
when the claws themselves are granted. The wargear adds zero rating and
cannot be sold or moved independently. Its modifiers apply; its built-in
items and option sets require an assignment. Two grants of the same
wargear give two copies.

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
section. To show a different name, give the collection one section,
marked default, with the name you want.

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

## Gang archetypes

Use this recipe when an archetype replaces a house's fighter list, such as an Escher Chem Cult. You will create a house hire collection, an archetype hire collection, and an optional choice on the gang. You will add modifiers to the archetype's pickable to replace the house's lists.

Prepare the content using a test gang type and test gang before adding it to a house used by players. The Outcast **Archetype** is a separate choice; create a **Gang Archetype** slot type for this setup.

### Create the house's hire collection

Live content is available to players. Staged content is available only to staff and players with staged-content access. Prepare the new content as staged wherever the authoring pages offer that setting.

1. Create a **collection** named "Escher Gang List". Leave **Prices its entries** on.
2. Add a **section** named "Gang List" and mark it as the default. This name makes a fighter collection the main hire list. Capitalisation does not affect its meaning.
3. Add an **entry** for every fighter available to an ordinary Escher gang. Select the existing fighter entries from the library. Leave the price override blank to use the fighter's reference price, or enter this list's price.
4. Add the completed collection to your test gang type's **built-in items**. Found a test gang and check its hire page. It should offer exactly the listed fighters under their rank headings, at the listed prices.

A gang without a visible main hire collection uses the fighter entries filed under its gang type. Once the gang has a live collection with a live default Gang List section, the collection determines which fighters appear on that main list. A fighter added to the house later also needs an entry in the collection.

### Create each archetype's hire collection

1. Create "Chem Cults Gang List" as a second **collection**, with **Prices its entries** on and a default section named "Gang List".
2. Add an **entry** for every fighter the archetype hires. A fighter available on both lists needs an entry in each collection. Set any archetype-specific price on the entry in the archetype collection.
3. Create a **slot type** named "Gang Archetype" and turn **Allows repeats** off. Create this once, then reuse it for every house and archetype in this setup.
4. Create a **pickable** named "Chem Cults" belonging to that slot type.
5. On the Chem Cults pickable, add a modifier with scope **The gang carrying it** and effect **Takes something away**. Select Escher Gang List.
6. Add a second modifier to the pickable with the same scope and effect **Gives something**. Select Chem Cults Gang List.

Add both modifiers to replace the house's hire collection. Giving the archetype list without taking the house list away leaves two main lists. The hire page then shows each under its collection name.

Keep existing fighters filed under their current gang types while preparing the collections. Before filing archetype-only fighters under their house, check that the house's gangs have received their main hire collection. Otherwise, ordinary gangs without a main hire collection can hire those fighters through their gang type. Include those fighters only in the archetype's collection.

### Add the optional choice to the gang

Do this once per house. Further archetypes need a collection and pickable of their own, then a member in the house's existing picklist.

1. Create a **picklist** named "Escher Gang Archetypes", using the Gang Archetype slot type. Add Chem Cults as a member. Include only archetypes available to Escher; other houses use their own picklists.
2. Create a **slot** named "Escher Gang Archetype" using the Gang Archetype slot type and Escher Gang Archetypes picklist. Set **Label** to "Gang archetype", **Min picks** to 0, **Max picks** to 1, and **Assigned to** to **the gang**. Leave **Hidden** off.
3. On the test gang type, add a modifier with scope **The gang carrying it** and effect **Gives something**. Select the Escher Gang Archetype slot. The gang sheet now has a Gang archetype choice.

Leave the slot empty for an ordinary Escher gang. You do not need a pickable for this option.

### Replace the equipment lists

Skip this section if the archetype uses the house's existing equipment lists. Otherwise, create the archetype's equipment collection and add the items and prices it offers. For a fighter with its own list, such as a Chem Cult Death-Maiden, create that equipment collection too.

Check the collections in the house fighters' built-in items and the collection available to the stash. These are the collections the modifiers must remove. If a fighter already has a separate house equipment list, remove that list for that fighter rather than leaving it alongside the replacement.

Add the following pairs of modifiers to the archetype's pickable:

1. **All fighters:** use scope **All models in the gang** for both modifiers. **Takes something away** names the house equipment collection; **Gives something** names the archetype's equipment collection.
2. **The stash:** use scope **The gang carrying it** for both modifiers, with the same two equipment collections.
3. **A fighter with its own list:** use scope **All models in the gang** for both modifiers. Add an **Is profile** condition and select the library fighter in **Profiles**, not its collection entry. **Takes something away** names the archetype's general equipment collection; **Gives something** names the fighter's equipment collection.

The fighter and stash swaps need separate pairs. Changing only the gang's collection changes stash access and leaves the fighters' equipment lists unchanged. Fighters keep equipment they already own.

### Check the content before making it available

Entries can be staged from the authoring pages. Staff and players with staged-content access can preview them. Collections and their sections also support staging, although their authoring forms do not offer a staging control.

**Put all required content live before adding the house collection to the real gang type.** Open **Staged content** from the library index and use **Put live** for this setup's new fighters, equipment, collection entries, pickables and picklist members. Review the list before using **Put everything live**, because it also releases other authors' staged work. Slots, picklists and modifiers have no staging control; test them before attaching them to a live gang type. A live main collection with all its entries staged or archived gives players an empty hire list. A staged collection is hidden from players without staged-content access, so it does not replace their gang-type fallback.

Check these steps on your test gang:

1. Leave Gang archetype empty. Check the house's fighters, prices, fighter equipment lists and stash equipment list.
2. Select Chem Cults. Check that its fighters replace the house list and excluded fighters disappear. Fighters on both lists should use the archetype's prices.
3. Hire a fighter whose price differs between the lists. Check the amount paid and the fighter's rating.
4. If equipment lists change, check an ordinary fighter, a fighter with its own list, and the stash.
5. Clear the archetype. Check that the house's hire and equipment lists return and hired fighters keep their equipment.
6. Check the gang sheet. The archetype choice should appear; the main hire collections should not.

When those checks pass, add the house collection to the real gang type's built-in items and add the modifier that gives its archetype slot. Check both a newly founded gang and an existing active gang. On each hire page, check the offered fighters and collection prices, then select the archetype and check the replacement. The main hire collection is hidden on the gang sheet, so that sheet cannot confirm access. If an existing gang has not updated, ask a maintainer to check the built-in update. Archived gangs need the maintainer's **Built-ins backfill** before they can rely on the new collection. Finish these checks before changing where archetype-only fighters are filed.

If you archive the main hire collection, gangs can again hire fighters listed under their gang type. The collection stays hidden on the gang sheet. Check the gang type's fighter entries before using this fallback: it can include fighters that the collection excluded.

## A Clan House Outcast gang

An Outcast gang chooses one of the six Clan Houses when it is created,
and for campaign purposes counts as a gang of that House. Two gang-level
choices are involved: the Clan House the Outcast player picks, and the
hidden **Gang supertype** slot every gang carries. A Clan House gang
type arrives with its supertype already picked. The Clan House pick
fills the supertype slot.

1. Create a **slot type** named "Gang supertype" and a **pickable** for
   each House — Goliath, Escher, Orlock, Van Saar, Delaque, Cawdor.
   These pickables carry no modifiers of their own. A rule reaches them
   through a *has pickable* condition instead.
2. Add a **picklist** of the six, and a **slot** named "Gang supertype",
   taking 1 pick, assigned to the gang, with *hidden* turned on. Hidden
   means the gang sheet never prints a "Gang supertype" line.
3. Build that slot into each of the six Clan House gang types, naming
   the matching House as the **starting pick**. Outcast, Enforcers and
   the rest do not build it in, so those gangs start with no supertype
   pick.
4. The Clan House choice is its own slot type, with its own pickables
   carrying the equipment access and the rest of what the choice gives.
   On each "Clan House: X" pickable, add a **modifier**: targets the gang
   alone, *gives* the Gang supertype slot, **with X picked**. The pick
   control appears once you choose a slot as the kind, and only a hidden
   slot can take one.

A Goliath gang and a Clan House Goliath Outcast gang now both have
Goliath picked for their Gang supertype. Two conditions read it:

- On the gang: *targets the gang alone, where the gang has picked
  Goliath*. Use this for a territory boon for Goliath gangs — "gangs
  that have picked Goliath: adds 10 to Income" — or for a rule that
  prints on the gang sheet only.
- On the models: *targets every model, where the model has picked
  Goliath*. A pick the gang holds is a fact about every model in it, so
  this reaches every fighter in both gangs.

Taking the Clan House pick back takes the supertype pick with it, and
both conditions stop matching. An Escher gang, or a Clanless Outcast
gang that picked no Clan House, never matches either.

Nothing new shows on the gang sheet. The given pick is a fact about the
gang, not a line: it adds nothing to the rating and does not appear in
the history.

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
equip page and changes nothing else. The pick is not paid for, and a
legacy pickable adds nothing to the gang's rating.

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

## Suit Evolution: the Power Boost table

> Draft, for review.

A Spyrer's suit keeps a Kill Count. After a battle, a Spyrer with a Kill
Count of four or more may spend four and roll a D6 for a Power Boost.
Rolls of 1 to 4 raise a characteristic; a 5 or 6 raises one carried
item's augmentation level. Each result raises the model's rating by a
printed figure. The app rolls only when asked, and never checks the Kill
Count: the Power Boost line is on the card whatever the count is, and
the owner decides when to roll.

1. On **Foundations**, create the **Power Boost table**. One click
   creates the slot type with *allows repeats* on, every result at its
   band with the credits it adds to the model's rating, and a standing
   choice of up to twenty picks. The first band contains two results,
   one for Weapon Skill and one for Ballistic Skill, because the book
   lets the player raise either.
2. Give Spyrers a **Kill Count** counter if they do not have one: create
   the counter and build it into each Spyrer entry, starting at 0. The
   Glitch Count is built the same way.
3. Standard content carries names and numbers only, so finish the
   results by hand. On each result that raises a characteristic, attach
   a **modifier**: targets the model, improves that characteristic by
   one (Weapon Skill or Ballistic Skill for the two Combat Neuroware
   results, Initiative, Movement, Save). The characteristic's own
   maximum stops the change. When that happens the book counts the
   result as Hunting Rig Augmentation instead; that is the player's to
   apply. The picker offers every result whatever was rolled.
4. On every result, attach a **modifier** as well: targets the model,
   *moves a counter* — the Kill Count, down by four. It runs once, when
   the result is picked, and taking the result back later does not give
   the four back.
5. On the Spyre Hunters gang type, attach a **modifier**: targets *all
   models in the gang*, narrowed to those that have the **Spyrer**
   subtype, and *gives* the Power Boost choice. Do not narrow it by the
   Kill Count: if the choice disappeared when the count dropped below
   four, every result already picked would go with it.

A Spyrer's card then shows a Power Boost line, and its picker offers to
roll. Rolling writes the roll to the gang's history; picking a result
adds it to the card, takes four from the Kill Count, and raises the
model's rating by the result's figure. Hunting Rig Augmentation raises
no characteristic on its own: the player then opens the augmentation
choice on one of the Spyrer's items and adds a tier there. Rolling again
is a second pick; taking a result back removes its rating and nothing
else.

Clearing all glitches instead of rolling is not yet a single action:
take the glitch results off the card by hand and move the Kill Count
down by four.

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
