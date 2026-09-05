# N26 Core Types

How the parts of Gyrinx N26 fit together.

The four things to remember:

1. **To control who gets a thing, control where it lands — there is no per-type switch.** For something gang-wide, build it into the gang type, or use a slot whose pick is assigned to the gang. For something on one model, build it into the profile, or pick "the bearer". There is no "make this broadcast" setting on a pickable or a rule. Reach follows entirely from the **host**, so you aim content by choosing how it arrives.

2. **Behaviour comes from modifiers attached to carriers — and modifiers are shared, so edit with care.** A rule or a pickable starts as a name. Its attached modifiers define its behaviour (scope plus effect, with conditions ANDed). Two practical consequences: attach a modifier to the content it should affect; and before editing an existing modifier, check its carriers, because the change applies everywhere it is attached. Know the two effect families: computed effects (gives, takes away, stat changes, counter contributions, choices, placements, limits) come and go with their carrier and are safe to rework; written effects (brings a model, moves a counter) happen once, and removing the carrier does not reverse them.

3. **Being in a collection and being offered from a section of it are two separate authoring acts.** Entries and selectors decide **membership** of the collection. **Placement** decides whether a particular category appears in a section. If you narrow a choice to "from section: Primary" and the skill's category has not been placed into Primary for that fighter, it is not offered: it is in "Other". So a working "choose a Primary skill" needs both halves authored: the content in the collection, and a placement putting its category in that section for the right models.

4. **Use qualifiers and help text.** Every assignable has a qualifier, which is internal and tells two same-named things apart. Library help text is shown next to objects in most places. Use both to make things clearer.

## Assignment

**An assignment has three components**: *what* is held (an **assignable** — a weapon, a skill, a pickable…), *who it is assigned to* (the **host**), and the source of the assignment (its **cause**). Removing the cause also removes the assignment. Every item on a card, from a hired fighter's profile to a granted rule, is an assignment.

An **assignable** is usually very simple: a piece of data that, once assigned, can carry modifiers. Some have extra configuration. Rules, skills and pickables are all assignables.

The **host** is the specific object the assignment sits on: a model, the gang, a parent item (a scope fitted to a gun), or the stash. The host decides *reach*: an assignment hosted on a model is that model's; an assignment hosted on the gang is **broadcast** to every member's card.

The **cause** is the action that created a particular assignment. It answers "why is this here?" Cause drives one important behaviour: **removal cascades down the cause chain**. Remove an assignment and everything caused by it (and caused by *those*, recursively) is removed too. It is also where provenance comes from: the card can show "came with X" because the assignment records its cause.

A **modifier** is attached to a specific assignable (for example the Aranthian pickable), which we call the **carrier**. It states who it reaches (**scope**) and what it does (**effect**). Conditions limit the scope. They are ANDed across conditions and any-of within a single condition, so an effect applies only in certain contexts.

Modifiers are shared by design: one modifier can be attached to any number of carriers, and editing the modifier changes it everywhere it is carried.

Effects are split by when they happen:

- **computed** ones (gives, takes away, changes a stat, adds to a counter, offers a choice, places a category, draws the pick, notes a limit) are worked out again on every read and disappear with their carrier
- **written** ones (brings a model, moves a counter) run once at arrival and are not undone by removal.

We use **carrier** as a library-side word for one specific piece of *content*, because it "carries" a modifier. A power maul carries its "+1 Strength" modifier; the Clan House pickable carries a grant of the house slot. Carrier is an authoring word: edit the carrier's modifier and it changes everywhere that carrier appears.

**Bearer** is the thing a modifier affects. The maul's modifier reads "+1 Strength *to its bearer*" — whoever holds a *specific* maul, with no name attached.

So: you buy a power maul for Vex. The purchase writes one assignment — **assignable**: the maul, **host**: Vex, **cause**: the purchase. The maul's assignment points at its underlying **assignable**, which is a **carrier** of a **modifier**, which now applies to its **bearer**, Vex. When the maul **assignment** is reassigned, the same assignment gets a new host, and the modifier follows the maul, not Vex.

Often the host and the bearer are the same. But when the Outcast Leader settles the gang's Gang Legacy slot, the pickable they choose is assigned *to the gang*. When the gang is the host, every model sees it (and becomes the bearer), even though the Leader was the one who chose:

1. The Leader's Profile (assignable) carries a modifier adding the Gang Legacy slot, which lands on the gang
2. The choice is made. One assignment is written: assignable = the pickable, host = the gang, cause = the Leader
3. Gang-hosted, so broadcast to every model (but hidden, used only to apply modifiers)
4. On each model, the pickable is the carrier of its modifiers, and they resolve against that model as the bearer

## Hiring

Hiring is a gang-hosted assignment which points at a specific profile, and which
materialises its built-ins onto the new model ("miniature" below is internal terminology):

What the hire operation does, in order:

1. Writes a membership assignment: an assignment pointing at a profile, hosted on the gang, with the credits-paid information on it
2. Creates the Miniature, pointing back at that assignment. The model shown in the gang is this pairing: a membership assignment plus a name.
3. Sets "miniature root" on the membership assignment, pointing at the miniature. The assignment is hosted on the gang — the fighter is assigned to the gang — and the profile on the assignment sets their base rating.
4. Materialises the built-ins: the stub gun and the house list become free assignments, hosted directly on Vex (not the gang), caused by the membership. Delete Vex and the cascade removes his kit with him.

> Note from Tom: I'm not convinced that steps 1-3 above are the simplest way we could do this, but it is how it works now.

The relationships after one hire, spelled out:

- `membership.gang = gang` ("host")
- `membership.miniature_root = mini` ("whose membership is this?")
- `mini.membership = membership` (the model)
- `profile_role.role = primary`
- equipment assignments: `miniature = mini` (host), `caused_by = membership` (lifecycle), `reason = default`, `paid = 0`
- a ledger entry sits on the membership too, carrying the original price (or an override), which provides the rating contribution

> Note: much of the code and docs call an assignment a "row", which is confusing and should not be copied. If referring to an assignment, say assignment.

---

## Assignable types

### A gang-level choice (slot type)

*Who the gang sides with, which god it follows, or which corruption it has — chosen once, as a pick.*

Do not author a new kind for this. Create a **slot type** (Affiliation, Chaos God, Variant, or a new name), its **pickables**, a **picklist**, and a **slot** assigned to the gang. Grant that slot from a hidden built into the gang type, or from the gang type itself. Attach ordinary modifiers to each pickable to define its effects. For example, a pickable can open equipment lists to some ranks, or grant another slot while the pick remains assigned.

The slot type's name is the word the card and the history use. The slot's label is the wording of the choice on one card. See **Slot type** below.

### Rule (special rule)

*A named special rule on a card; its text stays in the book.*

Fields of its own: none — but its annotation is part of its identity, so variants of a rule share one printed name. We store the name, never the wording (copyright). A rule that also *does* something the app can work out carries ordinary modifiers.

Normally it arrives built into something (a profile's kit, a gang type) or given by a modifier. Reach: built into a profile, it reaches the model's card; given to the gang, every member's card. The card prints rules apart from skills, under their own heading.

Author note: we mostly do not want broadcast for gang rules. Instead, attach a modifier that reaches the models.

### Gang type

*A kind of gang — Escher, Ironhead Squats — assigned to the gang at founding.*

Fields of its own: an icon (stored artwork, drawn inline so it takes the text's colour; addresses resolve only against this site's storage); **starting credits** (a founding-budget override for gangs of this type); and **foundable** (whether a player may create one — off for a type that exists to be hired from or fought).

Assignable for the same reason a profile is: founding is a gang-hosted assignment naming the type. That gives the gang's built-ins something to be caused by (the house list arrives this way), and gives gang-wide modifiers a carrier. Mostly overrides and extras — the fighter entries are profiles, and each entry's skill access rides that profile. Its pricing fields stay at zero; nobody buys a gang type.

### Campaign type

*A kind of campaign — Territory campaign, Dominion, Law & Misrule — assigned to every gang that joins a campaign founded on it.*

Fields of its own: a **description** and its **asset kinds** (see below). The description is written for the arbitrator setting a campaign up: what the gangs fight over, what each starts with, how the campaign runs and how it ends. The set-up screen draws it on the type's card, beside sentences the app composes from the type's kinds, built-ins and modifiers. It is the one field on a campaign type a player reads; the author help stays for authors. Under each kind sit the **assets** of that kind — the list of what a campaign of this type hands out. An asset belongs to one kind, and so to one campaign type; there is no separate list on the type.

Assignable for the same reason a gang type is: joining a campaign is a gang-hosted assignment naming the type. That gives the built-ins every member gang arrives with — a Reputation counter with its opening value, a Settlement — something to be caused by, and gives campaign-wide modifiers a carrier every member's card can find. Its pricing fields stay at zero; nobody buys a campaign type.

Shared types live in the system pack. The one that ships is the **Territory campaign**, the core rulebook's own: gangs fight for control of Territory, every gang keeps a Settlement and starts with one Territory, and each Territory held gives a Boon. The campaign has three phases (Occupation, Downtime, Takeover) and ends with Triumphs. Its kinds are Settlement (held one each) and Territory (changes hands); it has a Settlement asset, and Reputation at 0 and the Settlement built in. An arbitrator's additions to one campaign — a counter, a kind, a label — go on a second campaign type in that campaign's own pack, layered on the shared one rather than copied from it.

**Asset kind** — *a class of asset a campaign type has: Territory, Racket, Settlement.* A row on the campaign type, edited on its page: a label (singular and plural, the plural defaulting to an s), a **mode**, and a position. Its assets are listed under it on the same page, and added there. The mode is on the kind, not the asset, because a whole class behaves one way. **Held one each**: every gang is given one when it joins and keeps it (a Settlement, a home territory). **Changes hands**: the campaign keeps the copies and each copy has one holder at a time (a Territory, a Racket, a Relic). Two kinds of one type cannot share a label, and a kind cannot be removed while any asset is of it.

### Asset

*One thing a campaign has — a Settlement, the Old Ruins territory, a Racket — of one asset kind.*

One entry in the list of what a campaign type hands out. It is made on the type's page, under one of the type's kinds, and that is the only way it belongs to the type. Assets have no listing or create page of their own; an asset's own page, reached from the type's, is where its modifiers and the rest of its fields are edited.

Fields of its own: its **kind** (settled when the asset is made, and fixing both the campaign type it belongs to and how it behaves) and an **income** figure. The income is printed on the card and never collected; nothing moves credits. What holding the asset does for its holder — Reputation while held, a special rule, a free hire — rides it as ordinary modifiers.

Assignable so that an asset of a held-one-each kind can be built into its campaign type and arrive on every member gang, and so that an asset of a kind that changes hands can carry modifiers too. An asset that changes hands is never assigned: the campaign's copy records who holds it.

### Hidden

*A carrier for effects that draws no row of its own.*

Fields of its own: none. Its name is authored to be read on the pages that explain things. Its kind is never shown.

The bundle mechanism: some printed rules are a side effect with no item behind them (each of the Arachni-Rig's guns takes a point off Attacks), so the option's set includes a hidden item carrying the modifier. Being its own kind is the point: no selector reaches it and the card draws nothing. It can be both given and taken away, so one take-away can cancel a whole bundle.

### Profile

*A fighter or vehicle entry — the thing a model is hired as.*

Fields of its own: **profile type** (Fighter or Vehicle — a closed set; Leader, Champion and Ganger are subtypes, not types), **gang type** (every profile belongs to one), and **offered for hire** (unticked for a model nobody hires directly, which mostly means a pet; a brings-a-model effect can still bring it in). It also takes option sets. Its statline shape follows its profile type. Its price is the fighter alone. Its built-in sets' prices are added at hire time.

### Weapon

*A weapon. Always has at least one firing line, the first of which is free.*

Fields of its own: **slots** (weapon slots used on a card; asterisked weapons take 2) and a **statline shape** (SR, LR, Str, AP, L — set once on the weapon; every firing line reads it from there).

A weapon's firing lines are assignables in their own right (WeaponProfile): the unnamed first line *is* the weapon, a named line is an ammo type, and buying one is an assignment hung off the weapon's assignment, so a stashed or reassigned weapon keeps its lines. Traits live on the lines, not the weapon. A weapon-level question ("has the Melee trait?") is derived from them.

**Weapon accessories** — sights, suspensors, focusing crystals — are their own type. They are assigned to a *weapon* rather than a model, hang off that weapon's assignment, and their effects land on its firing lines. The book's bracket restrictions ("Las Weapons Only", "Weapons Marked With * Only") are stored as data on the accessory. They are shown at browse and attach time and block nothing.

### Wargear

*Equipment that is not a weapon — armour, grenades, pets, field gear.*

Fields of its own: none — the shared set. It takes option sets (plain talons or razor-sharp). Carried by a model and priced like anything else. A thing that fits onto a weapon is not wargear; that is a weapon accessory.

### Skills and Powers

*What a model has selected (skills) or manifests (powers), each with a home category.*

Fields of their own: none. A skill's set is its home category — the same catalogue every collection shares — and its D6 number in the book is its position within that category. A power is the same shape: its home is a category too, so it appears in the same fighter-sectioned views as the skill sets with no special casing (the book does the same: Wyrds treat the powers list as a Secondary Skill Set). A power's annotation carries what the book prints in brackets ("(Free)", "Continuous Effect"), never rules text.

Both print on the card under their own headings. They arrive built in, given by a modifier, or chosen through an offered choice, and reach whoever holds them.

### Other types

- **Subtype** — *a model subtype: Leader, Ganger, Specialist, Mounted, Wyrd.* No fields of its own. Prints in the card's type line, and is what scopes match on ("Champion or Leader models").
- **Trait** — *a weapon trait: Melee, Rapid Fire (1), Knockback (6+).* The parameter is the annotation, so Knockback (5+) and Knockback (6+) are two traits. Lives on firing lines, never on the weapon itself.
- **Skill tree** — *"Agility" as a thing a gang can pick.* Most gangs never need one: a fixed skill set is just a category. Venators pick four and rank them. A fact a gang owns has to be an assignment, and an assignment can only point at an assignable, so this type fills that gap. Everything else about the set (its skills, where it sits for a fighter) belongs to the category. Chosen, so it takes no built-ins.
- **Counter** — *a named tally a model keeps: XP, Kill Count.* The definition is content. Who has one is an ordinary assignment (XP arrives through fighter built-ins, with its opening value on the set's member: the 61 in "Starting XP 61"). The running value is player-side and is changed only by tallying, which writes ledger events. A modifier can also add to a counter ("Adds to a counter"), which raises the reading for as long as its carrier is held and writes nothing down. A reading is then the tallied value plus whatever contributes to it, and a counter with contributions but no assignment still has a reading. **Drawn** off means the counter exists only for conditions to check: it appears on no card and no fighter page. The point of counters is that effects depend on values: "when XP is at least 5" reveals a promotion choice the moment the threshold is crossed, computed like everything else.

### Collection

*A named list of content: an equipment list, a trading post, a menu.*

One field of its own: **prices its entries** — turned off for a menu, where nothing is for sale and the entries are simply choices.

It contains things in two ways: manual **entries** (hand-picked items, optionally at this list's own price, and optionally narrowed to who *this list* offers the item to — the "(Forge-born only)" case) and **selectors** (rules like "every weapon", at their usual prices). An entry always beats a selector for the same item.

Collections arrive built into something (a profile's list, a gang type's) or given by a modifier. Reach: held by the gang, every fighter may browse it; held by or given to one model, that model alone.

Collections contain "sections" too — but these are not the same kind of Section as listed below, so this page calls them "collection sections".

> Tom note: we are very likely to rename "collection sections" to Tiers, or possibly rename the "Section" object

When a collection is displayed, its items are grouped by collection section and Category:

- Membership is entries and selectors — *placement* has nothing to do with whether a *thing is in the collection*.
- Where it appears: when a fighter's view of a collection is built, everything unplaced falls into the collection's own default section (part of its schema, so its name and position are content too), or a code-level "Other", drawn last. So when browsing Skills & Powers, an unplaced set ("category") is there, under Other.
- But narrowing excludes it: a Primary-narrowed picker (for example the "offers a choice" modifier with its choice set to come "from section") only shows categories *placed* within that section. An unplaced skill category is in Other, not Primary, so it is not offered. The fighter's own skills screen narrows this way too: it is the *fighter's* view, so a set nobody placed for them is not on it.
- The skills box on the edit page does not narrow. It draws every set the library holds, under two tabs: the sets a fighter's placements name (plus any they already hold something in) and, a click away, all of them. The placements sort that listing rather than shorten it. An owner settling what a model *is* may take a skill from any set, and a skill already held from an unplaced set could be removed nowhere else.

### Slot type

> Draft, for review.

*What is chosen: Gang Legacy, Affiliation, Clan House, Chaos God, Variant — and new ones are authored.*

Fields of its own: a **plural** (what several of them are called, so a page can say "Gang Legacies"), and **allows repeats** (whether one holder may pick the same pickable for two slots of this type).

A slot type puts a name on one or more slots, and groups pickables. It is not an assignable: nothing holds a slot type. Its slots, picklists and pickables all name it, and the authoring pages do not accept a mismatch: a picklist of one slot type cannot sit behind another type's slot. Which slot type something belongs to is set when it is created and never changed afterwards. Something in the wrong slot type is created again in the right one. Its page is where the whole slot type is built: its pickables, its picklists, and its slots.

### Pickable

> Draft, for review.

*A value that goes into a slot.*

Fields of its own: the **slot type** it belongs to, and an optional **linked category** — plus the shared assignable set, so whatever the pickable means is carried as ordinary modifiers.

One thing offered in a slot: a specific value, of a particular slot type, that carries behaviour as ordinary modifiers. It never draws a line of its own: it appears under its slot's choice line when chosen. Without its slot it shows nothing and does nothing, so it arrives chosen, given, or as a slot's starting value, never as a bare built-in. The authoring form does not accept one. Reach: whatever its own modifiers say, from wherever the pick landed.

The linked category is used for categorisation decisions: a rule that places "the chosen set" reads the pick's linked category to find which category it means. This is how a Skill Tree pick stands for the set it names: picking the Agility tree files the Agility category under whichever tier the placing rule names. Most pickables link nothing.

### Picklist

> Draft, for review.

*A flat, ordered list of pickables that the player picks from.*

Fields of its own: a **slot type** and a **name**; and, where the list is a roll table, the **dice** it is rolled on and how a roll **selects** its entry. Each pickable on it carries its place in the order and, where this list calls it something else, a wording of its own. On a roll table it also carries the **band** of rolls that lands on it, "51" or "21-26".

A set of pickables available in a slot. One slot type throughout, no headings and no prices — where a collection is a catalogue, this is a menu. One slot type may have several picklists, which is how a limited selection of the pickables is offered in certain situations: what a leader picks from and what a champion picks from could be two lists of one slot type. Not an assignable; a slot names it.

A roll table is a picklist that names its dice and how a roll finds its entry — the one entry whose band contains the roll, or every entry at or below it. The die is a closed set — D3, D6, D66 or 2D6 — so every roll it can produce is known. A band is plain numbers even on a D66, where "31-46" spans rolls that can never come up. A lookup is only ever made for a roll that did. The bands are authored; the player's pick screen rolls the die, or takes a roll made at the table, and puts the roll in the gang's history before anything is picked for it. The pick that follows names its roll, and a roll is applied once. The entry the roll landed on is shown first, never enforced: the rules substitute results, and the record shows the roll beside whatever was picked.

### Slot

> Draft, for review.

*A fully configured slot containing pickables: a picklist, a label, and how many picks.*

Fields of its own: its **slot type** and **picklist**; the **label** shown on the card; **min** and **max picks**; **assigned to** (whether the pick lands on the bearer or on the gang); **hidden**; and a position among the slots on one card.

One specific, named use of a slot type. Assigning one to a model or gang — built into a profile, given by a modifier, or brought by an option when something is bought — makes the slot appear. The card draws the label with what the player has picked, or what is set by default, or a control to pick, on the holder's own card and nowhere else: a slot the gang holds appears once rather than on every fighter. Picking under the minimum adds a note on the card and blocks nothing (no page prints these notes yet), and the picker stops offering at the maximum. A slot of one pick is settled by picking, and picking again replaces the pick. A slot of several picks is filled a pick at a time, each option on the picker adding or removing its own. A slot of 0 picks shows no choice. **Hidden** makes the slot invisible while the pick still does everything it does: grouped hidden assignables, under one name.

### Picks

> Draft, for review.

*Not a type: the assignment that settles a choice.*

The pick is an ordinary assignment: the pickable, hosted where the slot says it lands, caused by the slot's own assignment and pointing back at it. So removing the slot removes the pick and everything the pickable gave. Two slots of one slot type on one holder stay independent, even where one thing opened both. Nothing is worked out from what kind of thing was chosen. A pick is free and adds nothing to any rating.

A pick the gang holds is broadcast (but not displayed) to every member: a rule reaching "models with the Cawdor legacy" reaches them all, including the fighter who made the pick. A pickable that carries the *draws the pick on the card* effect is displayed after all, on the cards its scope reaches. See below.

Where the slot type does not allow repeats, the picker marks the pickables already picked for another slot, and the card notes when one pickable is picked for two (no page prints these notes yet). Marks and notes, never locks: the narrowing informs, and an owner may still hand over a pickable no picklist offered.

---

## Core types & concepts

The types above share some underpinnings. This section explains them.

### Assignable

*The shared shape of everything a gang, model or item can carry.*

Not a thing itself — almost every type above is "an assignable". The
shared fields: name; annotation (printed in brackets after the name);
qualifier (tells two same-named things apart for authors — a player never
sees it); author help; price; Trade Point price; an exclusive flag
(equipment-list only, never at the Trading Post); a home category (where
it sorts in any list); a position (its order within that category — a
skill's D6 number in its set); built-ins (what arrives free with it);
its modifiers.

### Category

*Where an item always sorts: one named home inside a section.*

Fields: its Section, a name, a position.

Used as a home for an *item* in a collection, so every collection groups it the same way — an autogun is an Auto/Stub Weapon everywhere. The same name may recur under different sections (Primitive Weapons under both Ranged and Close Combat).

A Category points at a Section, which is where the Category is normally organised. A Category's effective section can be changed ("placed") by a modifier.

### Section

*A heading of the catalogue, above categories — "Ranged Weapons".*

Fields: a name and a position. Nothing else.

A real object rather than free text, so two spellings cannot split a collection. Never assigned, never reaches anything.

Who uses it: the gear surfaces — the equip pages group their catalogues by it, and the `?section=` in the equip page's URL names one of these.

Not to be confused with collection sections — e.g. Primary and Secondary in the Skills & Powers collection. See above.

> Tom note: we are very likely to rename "collection sections" to Tiers, or possibly rename the "Section" object

### Built-ins (a set of defaults)

*A named set of things an assignable comes with, free, at arrival.*

Fields: a name and a price — priced absolutely, not as a difference:
plain talons 0, razor-sharp 25. Its members each name exactly one thing
from a deliberately narrow list: weapons, firing lines, wargear,
subtypes, skills, rules, hiddens, collections, counters. Not profiles (a
fighter cannot come with a fighter — that is what brings-a-model is for)
and not chosen kinds.

Pointed at from two places: any assignable's own built-ins, and an
option (razor-sharp talons are an option whose set holds the sharper
claws). Materialised when the holder arrives — hired, founded, or bought
— free, and "caused by" the holder, so removing the holder removes them
too.

A member that is a firing line names which of the set's weapons it
belongs to, and is added from that gun's own line rather than from the
general picker. A set that brings no such weapon can still hold the
line — it then lands on whatever matching gun the acquirer already
holds, which is how an option arms a weapon the built-ins bring.

### Offers a choice (an effect)

*Puts an open choice on the card; the player chooses one thing of a particular assignable type.*

Fields:

- the type it takes (exactly one — offering a choice of skill is not
settled by choosing a power)
- an optional collection section that narrows what a picker shows
- a **label** ("skill tree 1") naming the choice line on the card and deciding which line it files into
- **will be assigned to** — whether the chosen thing lands on the bearer or on the gang.

(A minor third path exists: the code making the choice may name the host explicitly, which beats both — it is how a gang-carried offer that each fighter settles individually lands on the fighter who was clicked.)

> Tom note: we probably want to extend these to support multiple different types

### Draws the pick on the card (an effect)

*Lists the pick carrying it on the cards this modifier reaches.*

No fields: the scope is the whole of what it does. Carried by a pickable, so the line comes and goes with the pick, and it acts only on a pick **the gang** holds. A model's own pick is already shown in the choice line that settled it.

The line is headed by the slot type's name ("Archetype") and holds what was picked. It leads nowhere: the choice is made and changed on the card that offered it, and that card draws its own choice line instead of this.

For an Outcast gang's archetype, picked by the leader and played by every model except the Champions, who pick one of their own.

### Ledger (entry + events)

*The append-only record of every purchase: what was asked, paid, and worth.*

Fields on an entry: list price, discount, paid, Trade Points, **rating contribution** (pinned forever — the "rating" half of the price/rating split), reason (bought, free, granted, default, and so on), and which collection entry priced it.

Append-only. An entry's events must fold back to the entry, and reconcile checks exactly that. Ratings and credits are never adjusted by differences — they are recomputed from this record and repinned. Rating sums the contributions of what models hold; the stash's assignments count in wealth instead.

### Operation

*The only writer of player data; everything else only reads.*

An actual change. Assign, buy, hire, choose, remove, move: each writes the assignment, the ledger entry, and the events together. Settling ends every operation by repinning the stash, the rating, and the credits from the ledger. Spending past the founding budget raises there and unwinds the whole transaction, one of the few hard blocks in the app.

### Gang

*One player's gang: its type, its money, its colour.*

Fields: name, gang type, founding date, starting credits (blank means unlimited, and the Refund control is hidden), credits, colour.

Its rating is what its models are worth, recomputed from the ledger and pinned — never the stash. Its wealth is rating plus credits plus the stash's own pinned worth.

### Miniature

*One model on the roster; the class name avoids Django's "Model"*

A model is a membership assignment naming a profile, plus everything attached to it. Every user-facing word is "model" — the Python class name is the only place "miniature" appears.

### Stash

*The gang's pocket: gear held by nobody, counted in wealth*

Fields: none of its own beyond its link to the gang and its pinned worth. Created at founding.

A host like any other: things can be assigned to it. Its worth is repinned by every operation. Counts towards wealth.
