# Recipes

## Stage and launch fighter progression

Open **Foundations → Fighter progression** and choose **Prepare for testing**.
This creates the standard advancement definitions and two staged preview rules:

- **Fighter progression** grants progression to eligible models in a test gang.
- **Outcast leader progression** also covers an elevated Leader whose source
  profile would normally be excluded from XP.

Assign the first rule to a test gang. For an Outcast test, assign both. The rules
grant action access; they do not change XP or grant past advancements. Open a test
model's edit page. If it has no XP counter, choose **Track XP** to open one at 0.
Then increase its XP through a rank threshold. Starting XP is not earned XP and
grants no free advancement.

The supplied content includes these promotions:

- A prospect that earns an advancement at 13 XP or above chooses a specialisation
  instead of rolling. The result replaces Prospect with Ganger and Specialist,
  grants the specialisation's skill, and adds 15 rating.
- A ganger that earns an advancement at 37 XP or above rolls normally and also
  becomes a Champion with Inspiring. Other subtypes remain. The starting Primary
  skill offer does not grant another skill for this promotion.
- A Corpse Grinder Initiate may keep its rank and roll instead. If promoted,
  it keeps weapons only if every equipped weapon profile has Melee. Other weapons
  move to the gang's stash.

When a promotion is due, resolve earlier earned advancements first. The promotion
is part of one earned use, not a second use. A completed result can be corrected
until a later advancement depends on it. Correction does not move equipment back
from the stash.

For profile-level testing, choose **Apply to staged content**. This attaches
progression only to staged profiles and gang types. To launch, choose **Review
live rollout**, check the named targets and exclusions, then **Apply content
setup**. The confirmation expires after 30 minutes or when the target list changes.
Existing models gain access through their profiles; future hires receive an XP
counter where one was missing. Existing starting XP values are preserved.

The standard recipes exclude Hired Guns, Dramatis Personae and alliance
delegations. Vehicles and other eligible profiles remain included. The Outcast
exception uses a modifier on the gang type that grants progression only to
leaders.

After applying the content, review **Initialise fighter action allowances** in
admin maintenance for models that already earned XP. That separate operation
uses recorded counter history; review its reported problems before running it.
Applying content does not create or rewrite player counter history. Run the
content setup again after importing new profiles into the default content pack.

### Author a promotion

Open the **Resolve advancement** definition from its outcome. Under **Promotions**,
select the starting subtype, minimum earned threshold and result slot. A
replacement promotion offers the slot's results instead of a roll. An additional
promotion uses a slot with exactly one result and applies it after the normal
advancement. Promotion slots use a choice table, without dice.

The results are ordinary pickables. Their modifiers add and remove subtypes,
grant skills or offer a skill selection. Set the rating contribution on each
pickable. Use **Optional profiles** for profiles that may decline a replacement
promotion. For equipment changes, set both **Stash weapons for** and **Keep weapon
trait**. **Requires rule** limits a promotion to models carrying that rule.

The supplied promotions require the **Promotion** rule, granted by the setup.
This keeps preparation from changing models with manually authored advancement
access. Prepare for testing restores the supplied promotion definitions and
preview rules. It also repairs shared content, including the starting-skill
offer; those repairs affect models already using that content. Use separate
definitions for house rules you want to preserve.

## Bind other fighter actions

First create **Fighter actions and advancement table** under Foundations. This
creates the reusable actions, outcomes, advancement slot and table, and the
standard XP rank table. It does not guess which house rules or profiles use
them.

For a custom campaign-wide progression rule, add three **Adds assignable** modifiers
that reach every model: **Advancement**, **Standard fighter ranks**, and the
**Advancement** slot. The slot supplies the recorded 2D6 question, the rank
table supplies the XP thresholds, and the action supplies the earned use.
Add the **Promotion** rule too if the supplied promotions should apply.

For Spyrers, follow [An item's augmentation tiers](#an-items-augmentation-tiers)
and [Suit Evolution and Suit Maintenance actions](#suit-evolution-and-suit-maintenance-actions)
below. The action grants belong on the fighters, and each item's tiers belong
on that item. The XP setup above does not create either link.

If a profile should always carry these definitions without a computed rule,
open its built-in set and add the same Action, RankTable, or Slot as a default
member. Use one route for each definition; duplicate routes are collapsed for
access but make the authored source harder to explain.

The five skill advancement results are already configured. Primary and
Secondary results point at those exact Skills & Powers sections. Random results
record a D6 roll; select results let the player pick. The any-skill result
leaves the section blank deliberately.

How to build specific rulebook setups out of the library's pieces. Each
recipe is a set of steps to follow in the authoring pages — the things to
create, and how to join them. A recipe is added once the way to author
its setup is settled.

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
cannot be sold or moved on its own. Its modifiers apply. Its built-in
items and option sets need an assignment. Two grants of the same wargear
give two copies.

## Corrupted gangs

Genestealer Cult, Chaos and Malstrain corruption are built the same way
and differ only in what they contain. A corruption is a choice the player makes once for
the gang, and all of its effects come from modifiers attached to the
chosen pickable.

### The choice

Use a **slot type** for this gang-level choice. Follow the same six steps
as a Gang Legacy, and assign the slot to the gang.

1. Create a **slot type** named "Variant" — what is being chosen — and
   give it a plural. Turn *allows repeats* off. Build the rest of this
   recipe on that slot type's page.
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
can buy it for their Leader at hire or later. The app does not check
whether the book allows the purchase at that point.

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
the sheet says where the roster is over a limit.

**Losing the gang's own special rules.** This needs a small change to
each gang type, made once, and then one step per corruption. On each
gang type, create a **hidden** item named for it — "Escher gang
rules" — and put it in the gang type's built-in items. Move the house's
special rules onto it: one *gives* modifier per rule, targeting the
gang. What the gang holds reaches its fighters, so a rule that improves
their weapons or changes a characteristic works from there. Only a rule
you also want printed on each fighter's card needs a second *gives*
targeting the model. The rules are then granted rather than built in, and
one item carries all of them. On each corruption's pickable, add
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

## Interstitials

Use this recipe to put a heading and an explanation in front of a choice. Founding a gang, hiring a model or making a pick can add a slot to a card. If an interstitial is attached to that slot, the player sees it first. Buying an item and cloning a model do not show one.

Create the slot before you start. You will create an interstitial and attach it to one or more slots.

1. Create an **interstitial**. **Name** is what you call it in the library; players never see it. **Title** is the heading on the screen — leave it blank to use the name. **Description** is the text under the heading.
2. Leave **Skippable** off if the player must make the choice before carrying on. Turn it on if they can leave it and make it later on the gang sheet.
3. Set **Position** to order this screen against others shown at the same time. Ties fall back to the name.
4. Use **Attach a slot** on the interstitial's page, once for each slot the screen is shown for. One interstitial can be attached to several slots, and one slot can show several interstitials.
5. Open **Staged content** from the library index and use **Put live**. A new interstitial is staged. Attachments have no staging control and are live at once.

The screen only appears when the slot is added. A gang that already holds the slot will not see it, so attach the interstitial before those gangs are founded or those models hired.

**Continue** saves every choice on the screen. A choice that is not skippable blocks **Continue** until it has enough picks, and the screen lists what is missing. **Skip** appears only when no choice on the screen is required, and leaves without saving.

## A Clan House Outcast gang

An Outcast gang chooses one of the six Clan Houses when it is created,
and for campaign purposes counts as a gang of that House. This uses two
choices the gang makes: the Clan House the Outcast player picks, and the
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
gang rather than a line on it. It adds nothing to the rating and does
not appear in the history.

## A Gang Legacy

> Draft, for review. The steps below are the authoring steps. Everything
> in square brackets is a fact about the rules rather than about the
> app, and is still to be filled in.

A gang legacy is a choice a fighter makes once. Each pickable opens an
equipment list to the fighter who picks it. The same six steps build any
slot type. This one is written out because it uses all of them.

1. Create a **slot type** named "Gang Legacy" — what is being chosen —
   and give it a plural, so a page can name several of them. Set *allows
   repeats* to [whether one gang may hold the same legacy twice]. Build
   the rest of this recipe on that slot type's page.
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
because one of its fighters holds a legacy: a condition checks what a
model has, never what any model in the gang has. A picklist also cannot
be limited to a particular moment. It is open whenever the fighter's
equip page is open.

## A restriction on one list only

Some lists print a restriction beside an item that other lists print
without one. The Goliath equipment list has "Heavy rock saw (Forge-born
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
for them. Nothing is blocked. The list states the restriction.

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

The two modifiers work together, and placement comes first. The offer is
limited to whatever is Primary *for this model*, and the placement is
what puts the family there. An offer without a placement gives the
player an empty page when they click Choose. A placement without an
offer is a valid setup: the model may select powers from the family at
any time, but is not given a first one.

## An item's augmentation tiers

Use this recipe to enter Spyrer augmentations manually. Start with the Jakara
hunting rig, test both tiers, then repeat for each item. Use the **Modifier
Objects** tab in the [N26 Pre-ingest workbook](https://docs.google.com/spreadsheets/d/19YIkTnsrgQ5E2NVa5dIU4Syk7VPykX9WZZkevzWZclk/edit?gid=1795933652#gid=1795933652)
as a checklist and check its entries against the equipment's rules. Blank cells
do not always mean a tier has no effect.

Write a short, original **Summary** for each tier and, if useful, an
**Introduction** for its slot. These words appear on the player's choice page.
The app does not write them from the modifiers. The modifiers still determine
what the tier does; check that each summary matches them. Do not copy the
book's rules text.

**Do not launch Malcadon hunting rig augmentations yet.** The app cannot upgrade
the tier after the player chooses Ballistic Skill or Weapon Skill. Leave this
rig's augmentation slot unattached. Continue with the Malcadon weapons.

### Reuse the shared definitions

Open **Foundations → Fighter actions and advancement table**. Create missing
definitions there, then reuse the existing **Augmentation** slot type, **Suit
Evolution**, **Suit Maintenance** and **Recruitment augmentation** actions.
Do not create a second set. Foundations supplies the actions and their prices;
you supply each item's tiers and grant the actions to the eligible fighters.

An item's setup has three parts:

| Part | What you enter | Where it belongs |
| --- | --- | --- |
| Pickable | One tier, its summary and all its effects | Augmentation slot type |
| Picklist | That item's tiers, each with a numeric level | Augmentation slot type |
| Slot | The item's current tier and optional introduction | Built into that weapon or rig |

### Prepare a test fighter and gear

Use a staff account. In **Content library → Wargear**, choose **New wargear**
and name it **Jakara recipe test rig**. Leave **Staged** on and create it.
For a weapon test, use **New weapon**, select the **Weapon** statline type,
then **Add weapon profile**. Copy the real weapon's characteristics and traits.
Keep both the weapon and its profile staged.

In **Content library → Profile**, choose **New profile**. Name it **Augmentation
recipe test hunter**, select **Fighter** and **Spyre Hunters**, and leave
**Staged** on. After creating it, enter a statline and save. Under **Add a
built-in**, select **subtype → Spyrer**, then **Add built-in**. Add the test rig
the same way, using **wargear** instead of subtype.

Attaching a modifier or built-in item to live content can affect existing
models immediately. Staging the new tier does not prevent those changes.
Use the test entries until the launch checklist below is complete.

### Build the Jakara hunting rig tiers

From **Content library → Slot type**, open **Augmentation**.

1. Under **Add a pickable**, enter **Tier 1**. Expand **Qualifier and author
   help**, set **Qualifier** to **Jakara hunting rig**, and set **Rating
   contribution** to **0**. Set **Summary** to **Strength +1 while carrying the
   rig.** Click **Add pickable**, then open the new Tier 1.
   The qualifier distinguishes this item's tiers in the library; players see
   only the tier name.
2. On Tier 1, add a **modifier**. Select **The model carrying it** and **Changes
   a stat**, then **Configure new modifier**. Select **S (Strength)**,
   **Improve**, and amount **1**. Name it **Jakara rig: Strength +1** and click
   **Attach modifier**.
3. Add **Tier 2** with the same qualifier and rating contribution. Set its
   **Summary** to **Strength +1 and Attacks +1 while carrying the rig.** Attach the
   Strength modifier from Tier 1 using **Attach an existing modifier → Attach**.
   Add another modifier with **The model carrying it → Changes a stat**:
   **A (Attacks) → Improve → 1**. Name it **Jakara rig: Attacks +1**.
4. Back on Augmentation, add a **picklist** named **Jakara hunting rig tiers**.
   Leave **Dice** blank. Add Tier 1 as a member with **Level 1** and Tier 2 with
   **Level 2**. Leave the roll fields blank. Position only controls display
   order; **Level** controls upgrading.
5. Add a **slot** named **Jakara hunting rig augmentation**, using that picklist
   and the Augmentation slot type. Set **Label** to **Augmentation**, **Mode** to
   **Tier ladder**, **Min picks** to **0**, **Max picks** to **1**, and **Assigned
   to** to **The bearer**. Set **Introduction** to **Pick a tier for the Jakara
   hunting rig.** Leave **Hidden** off.
6. Open your test rig. Under **Add a built-in**, select **Kind → slot**, choose
   **Jakara hunting rig augmentation**, and click **Add built-in**. Leave
   **Default pickable** blank. The slot belongs on the rig, not on the fighter
   or gang.

Only the current tier applies. Tier 2 therefore needs both Strength and Attacks;
it does not inherit Tier 1's modifiers automatically. Keep the rating at 0
unless the rules assign a rating increase to that tier.

### Enter weapon changes and rule-based effects

For each weapon, create its own tiers, picklist and slot using the steps above.
Write a summary for every tier and an optional introduction for the slot.
Use the weapon's name as the qualifier and build the slot into the weapon,
not its firing profile.

- **Weapon stats:** select **The model's weapons → Changes a stat**, then
  **Configure new modifier**. Click **Add a condition**, set **Kind** to
  **is_one_of**, and choose the test weapon under **Weapons**. Select the stat
  below. Use **Set to** for a printed final value, such as Lethality 2 or Armour
  Piercing −2. Use **Improve** for a change
  relative to the base value. This scope reaches every carried copy of that
  named weapon; keep a printed paired weapon as one library weapon.
- **Weapon traits:** select **The model's weapons** and add the same **is_one_of**
  condition. To replace Rapid Fire (2) with
  Rapid Fire (3), add **Takes something away** for the old trait and **Gives
  something** for the new trait. Reuse the existing annotated traits, or create
  the missing trait and its annotation first. Repeat both modifiers on later
  tiers that retain the replacement.
- **Invulnerable saves:** create or reuse a **special rule** named
  **Invulnerable save**, with the save value as its **Annotation**, such as
  **6+**. On the tier, use **The model carrying it → Gives something** and select
  that special rule. Alternatively, enter **Invulnerable save (6+)** under
  **New rule**; the form turns the brackets into an annotation. Do not change
  the fighter's ordinary Save characteristic.
  For Mirror shield, Tier 2 retains the 6+ rule alongside its range change;
  Tier 3 grants only the 5+ version alongside that range change.
- **Rigs with an existing save:** Orrus and Sovereign rigs already grant a save
  before augmentation. If the existing save uses a special rule, each
  upgraded tier also needs **Takes something away** for the base version.
  Check that the card displays only the upgraded save.
- **Conditional benefits:** represent Yeld's cover benefit with a named special
  rule granted to the model by Tier 2, alongside Tier 1's Movement improvement.
  The card records the rule; players apply its condition at the table. Do not
  improve the model's ordinary Save unconditionally.

Use names and annotations for special rules, not copied rules text. These rules
appear on the model's card. They do not automate saving throws.

When a later tier replaces an earlier effect, attach only the final version
of that effect to the later tier. A tier must contain every effect that still
applies, including benefits recorded as special rules.

## Suit Evolution and Suit Maintenance actions

The shared actions already contain their outcomes and prices. Suit Evolution
spends **4 Kill Count** to augment an item or clear glitches. Suit Maintenance
spends **100¢** to clear glitches. Recruitment augmentation uses an earned
recruitment allowance. Granting an action does not spend these resources.

### Give the actions to fighters

1. Open an eligible **fighter entry**, starting with your test entry. Add a
   modifier with **The model carrying it → Gives something**. Click **Configure
   new modifier**, set **Kind** to **action**, select **Suit Evolution**, then
   **Attach modifier**.
2. Add **Suit Maintenance** using **The model carrying it → Gives something**
   again. Reuse these two modifiers on the eligible real Spyrer fighter entries
   only when you are ready to launch.
3. To test Hunt Master's free augmentation, also grant **Recruitment
   augmentation** to your test entry. Use **The model carrying it → Gives
   something** again. Attach it before hiring the test model.
4. Check the fighter's **Kill Count** and **Glitch Count**. Reuse the counters
   already built into the **Spyrer** subtype. If either is missing, ask the
   maintainer to check that shared subtype before continuing. Do not add another
   copy directly to each fighter.

Attach these modifiers to **fighter entries** to limit action access to eligible
fighters. Do not grant these actions or progression rules through the **gang
type**. At launch, grant Recruitment augmentation only to **Spyre Hunt Master**.

### Test one complete item before repeating

Check that the tiers and their **picklist members** are live. If any are staged,
use **Staged content** to put only those entries live. Staged tiers and members
cannot be selected in an action flow, even by staff. Keep the test gear and
fighter entries staged and the augmentation slot unattached to live gear.

Ask the maintainer to confirm counter history is active before hiring the test
models. If it is inactive, the paid flows are unavailable and hiring does not
earn a recruitment use. This is a one-off maintenance task, not an authoring step.

Create a **Spyre Hunters** test gang with enough starting credits for a hire
and 100¢ maintenance. Click **Hire Fighters** and search for your test entry.
An entry without a category appears under **Uncategorised**. Staff can hire
staged profiles. The built-in test gear arrives with the model.

1. Hire a fresh model from the test entry. Check that its
   unselected tier does not add a line to the roster card. The model's edit
   page should have **Choose tier** beside the rig. Check both counters appear
   once. Give the test model **8 Kill Count** and note its Strength and Attacks.
2. On the model's edit page, start **Suit Evolution**, select **Hunting Rig
   Augmentation**, then the rig's **Tier 1**. Review it. Cancel once and check
   that neither the tier nor Kill Count changed.
3. Start again and confirm Tier 1. Check **4 Kill Count** remains, Strength has
   improved by 1, and Attacks is unchanged.
4. Complete a second evolution for Tier 2. Check **0 Kill Count** remains,
   Strength is still only 1 better than the starting value, and Attacks is now
   1 better. The card should show **Jakara hunting rig (Tier 2)** on one line.
5. For a weapon, repeat through every tier and inspect its firing profile and
   traits. For a rule-based benefit, check the special rule and its annotation
   on the card. Check both newly equipped and already-carried items.
6. Separately check **Suit Maintenance** with a non-zero Glitch Count and enough
   gang credits. Confirm that it clears the glitches and charges 100¢. Check a
   newly hired Hunt Master has one recruitment augmentation use and spends it
   only when confirming a result.

If an action is missing, check its fighter-entry modifier and available balance
or allowance. Setting **Usable by** alone does not grant access. If an item is
missing from the selection, check its built-in slot,
**Tier ladder** mode, numeric levels, live pickables and live members. A finished
item at its last tier is not offered again.

### Launch the checked content

Reuse the tiers, picklist and slot you tested; do not create another set. For a
weapon, change each modifier's **is_one_of** condition to name the real weapon
instead of the test weapon. Where the library has separate versions, such as
Jakara and Hunt Master weapons, include every intended version in the condition.

With the content maintainer's approval, attach the tested slot to the real item
and grant the actions to the real fighter entries as above. Keep the test gear
and test fighter entries staged. These attachments change live content.

Check a fresh hire and an existing model after the attachments. If an existing
item has no augmentation line, ask a maintainer to check the built-in update;
do not remove and rebuy the player's equipment. Leave Malcadon hunting rig's
ladder unattached and list it as deferred in the launch notes.

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
   repeats* on, so one model can take the same result twice, every
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
   setting the status in turn. The card shows the status under the
   model's name. The owner can set it by hand from the card's menu, and
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
