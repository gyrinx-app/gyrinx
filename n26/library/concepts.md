# N26 Core Types

This should give you a solid grounding in how Gyrinx N26 fits together.

If you take nothing else away:

1. **To control who gets a thing, control where it lands — do not look for a per-type switch.** Want it gang-wide? Build it into the gang type, or have a slot whose pick is assigned to the gang. Want it on one model? Build it into the profile, or pick "the bearer". There is no "make this broadcast" setting on a pickable or a rule — reach is entirely a consequence of the **host**, so you aim content by choosing its arrival route.

2. **Behaviour comes from modifiers attached to carriers — and modifiers are shared, so edit with care.** A rule or a pickable starts as a name; its attached modifiers define its behaviour (scope + effect, conditions ANDed). Two practical consequences: attach a modifier to the content it should affect; and before editing an existing modifier, check its carriers, because the change applies everywhere it is attached. Know the two effect families: computed effects (gives, takes away, stat changes, counter contributions, choices, placements, limits) come and go with their carrier and are safe to rework; written effects (brings a model, moves a counter) happen once and removal will not reverse them.

3. **Being in a collection and being offered from a section of it are two separate authoring acts.** Entries and sweeps decide **membership** of the collection; **placement** decides whether a particular category appears. If you narrow a choice "from section: Primary" and the skill's category hasn't been placed into Primary for that fighter, it will not be offered — it's sitting in "Other". So a working "choose a Primary skill" needs both halves authored: the content in the collection, and a placement putting its category in that section for the right models.

4. **Use qualifiers and help text**. Assignables come with a qualifier is that is internal, for telling twins apart and disambiguation, and library text shows up next to objects in most places. Use it to make things clearer.

## Assignment

**An assignment has three components**: *what* is held (an **assignable** — a weapon, a skill, a pickable…), *who it is assigned to* (the **host**), and the source of the assignment (its **cause**). Removing the cause also removes the assignment. Every item on a card, from a hired fighter's profile to a granted rule, is an assignment.

An **assignable** is typically very simple: a piece of data that, once assigned, can carry modifiers. Sometimes they have extra configuration. Rules, skills and pickables are all assignables.

The **host** is the specific object the assignment sits on: a model, the gang, a parent item (a scope fitted to a gun), or the stash *only*. Host decides *reach*: an assignment hosted on a model is that model's; an assignment hosted on the gang is **broadcast** to every member's card.

The **cause** is then the action that brought a particular assignment into existence, answering "why is this here?" Cause powers one important behaviour: **removal cascades down the cause chain**. Remove an assignment and everything caused by it (and caused by *those*, recursively) goes too. It's also where provenance comes from — the card can say "came with X" because the assignment knows its cause.

A **modifier** is attached to a specific instance of an assignable (e.g. the Aranthian pickable) which we call the **carrier**, asserting who it reaches (**scope**), and what it does (**effect**). Conditions limit the scope — AND-ed across conditions, any-of within a single condition — to allowlist modifier effects only in certain contexts.

Modifiers are shared by design: they can attach on any number of specific assignables ("carriers"), and editing the modifier changes it everywhere it is carried.

Effects are split by when they happen:

- **computed** ones (gives, takes away, changes a stat, adds to a counter, offers a choice, places a category, draws the pick, notes a limit) are re-derived on every read and vanish with their carrier
- **written** ones (brings a model, moves a counter) run once at arrival and are never undone by removal.

We use **carrier** as a library-side word for one specific piece of *content*, typically because they "carry" a modifier. A power maul carries its "+1 Strength" modifier; the Clan House pickable carries a grant of the house slot. Carrier is about authoring — edit the carrier's modifier and it changes everywhere that carrier appears.

**Bearer** is used to describe the thing being affected by a modifier. The maul's modifier says "+1 Strength *to its bearer*" — whoever holds a *specific* maul, no name attached.

So: you buy a power maul for Vex. The purchase writes one assignment — **assignable**: the maul, **host**: Vex, **cause**: the purchase. The maul's assignment points at its underlying **assignable**, which is a **carrier** of a **modifier** which now applies to its **bearer** — Vex. When the maul **assignment** is reassigned, the same assignment gets a new host and the modifier follows the maul, not Vex.

Often the host and the bearer coincide. But when the Outcast Leader answers the gang's Gang Legacy slot, the pickable they choose is assigned *to the gang*. When the gang is the host, every model sees it (and becomes the bearer), even though the Leader was the one asked:

1. The Leader's Profile (assignable) carries a modifier adding the Gang Legacy slot, which lands on the gang
2. Choice made → one assignment row: assignable = the pickable, host = the gang, cause = the Leader
3. Gang-hosted ⇒ broadcast to every model (but hidden, just used to apply modifiers)
4. On each model, the pickable is the carrier of its modifiers, and they resolve against it as the bearer

## Hiring

Hiring is a gang-hosted assignment which points at a specific profile, and which
materialises its built-ins onto the new model ("miniature" below, internal terminology):

What the hire operation actually does, in order:

1. Writes a membership assignment: an assignment pointing at a profile, hosted on the gang, with the credits-paid information on it
2. Creates the Miniature, pointing back at that assignment. The model shown in the gang is this pairing: a membership assignment plus a name.
3. Sets "miniature root" on the membership assignment, pointing at the miniature. The assignment is hosted on the gang — the fighter is assigned to the gang — but the profile on the assignment sets their base rating.
4. Materialises the built-ins: the stub gun and the house list become free assignments, hosted directly on Vex (not the gang!), caused by the membership. Delete Vex and the subtree cascade takes his kit with him.

> Note from Tom: I'm not convinced that steps 1-3 above are the simplest way we could do this, but it is how it works now.

So the relationships after one hire, spelled out:

- `membership.gang = gang` ("host")
- `membership.miniature_root = mini` ("whose membership is this?")
- `mini.membership = membership` (the model)
- `profile_role.role = primary`
- equipment assignments: `miniature = mini` (host), `caused_by = membership` (lifecycle), `reason = default`, `paid = 0`
- a ledger entry sits on the membership too, carrying the original price (or an override) to provide rating contribution

> Note: much of the code and docs call an assignment a "row" which is very confusing and should not be copied. If referring to an assignment, say assignment.

---

## Assignable types

### A gang-level choice (slot type)

*Who the gang sides with, which god it follows, or which corruption it has — chosen once, as a pick.*

Do not author a new kind for this. Create a **slot type** (Affiliation, Chaos God, Variant, or a new name), its **pickables**, a **picklist**, and a **slot** assigned to the gang. Grant that slot from a hidden built into the gang type, or from the gang type itself. Attach ordinary modifiers to each pickable to define its effects. For example, a pickable can open equipment lists to some ranks or grant another slot while the pick remains assigned.

The slot type's name is the word the card and the history use. The slot's label is the question on one card. See **Slot type** below.

### Rule (special rule)

*A named special rule on a card; its text stays in the book.*

Fields of its own: none — but its annotation is part of its identity: a rule in variants share one printed name. We store the name, never the wording (copyright). A rule that also *does* something the app can work out carries ordinary modifiers.

Normally it arrives built into something (a profile's kit, a gang type) or given by a modifier. Reach: built into a profile, it hits the model's card; when given to the gang, every member's card. The card prints rules apart from skills, under their own heading.

Author note: we actually, mostly, don't want broadcast for gang rules. Instead we'd want to attach modifier which hits the models.

### Gang type

*A kind of gang — Escher, Ironhead Squats — assigned to the gang at founding.*

Fields of its own: an icon (stored artwork, drawn inline so it takes the text's colour; addresses resolve only against this site's storage); **starting credits** (a founding-budget override for gangs of this type); and **foundable** (whether a player may create one — off for a type that exists to be hired from or fought).

Assignable for the same reason a profile is: founding is a gang-hosted assignment naming the type. That gives the gang's built-ins something to be caused by (the house list arrives this way), and gives gang-wide modifiers a carrier. Mostly overrides and extras — the fighter entries are profiles, and each entry's skill access rides that profile. Its pricing fields stay at zero; nobody buys a gang type.

### Campaign type

*A kind of campaign — Dominion, Law & Misrule — assigned to every gang that joins a campaign founded on it.*

Fields of its own: its **asset kinds** (see below) and the **assets** it offers — its catalogue. An asset can be offered by several campaign types.

Assignable for the same reason a gang type is: joining a campaign is a gang-hosted assignment naming the type. That gives the built-ins every member gang arrives with — a Reputation counter with its opening value, a Settlement — something to be caused by, and gives campaign-wide modifiers a carrier every member's card can find. Its pricing fields stay at zero; nobody buys a campaign type.

Shared types live in the system pack. The one that ships is **N26 core**, with Settlement (held one each) and Territory (pooled) as its kinds, a Settlement asset, and Reputation at 0 built in. An arbitrator's additions to one campaign — a counter, a kind, a label — go on a second campaign type in that campaign's own pack, layered on the shared one rather than copied from it.

**Asset kind** — *a class of asset a campaign type deals in: Territory, Racket, Settlement.* A row on the campaign type, edited on its page: a label (singular and plural, the plural defaulting to an s), a **mode**, and a position. The mode is on the kind, not the asset, because a whole class behaves one way. **Held one each**: every gang is given one when it joins, and it is never staked (a Settlement, a home territory). **Pooled**: the campaign holds a pool of them and each has one holder at a time (a Territory, a Racket, a Relic). Two kinds of one type cannot share a label, and a kind cannot be removed while any asset is of it.

### Asset

*One thing a campaign deals in — a Settlement, the Old Ruins territory, a Racket — of one asset kind.*

Fields of its own: its **kind** (which fixes the campaign type it belongs to and how it behaves) and an **income** figure. The income is printed on the card and never collected; nothing moves credits. What holding the asset does for its holder — Reputation while held, a special rule, a free hire — rides it as ordinary modifiers.

Assignable so that an asset of a held-one-each kind can be built into its campaign type and arrive on every member gang, and so that an asset of either kind can carry modifiers. A pooled asset is never assigned: the campaign's token records who holds it.

### Hidden

*A carrier for effects that draws no row of its own.*

Fields of its own: none. Its name is authored to be read on the pages that explain things; its kind is never said.

The bundle mechanism: some printed rules are a side effect with no item behind them (the Arachni-Rig's guns each knock a point off Attacks), so the option's set includes a hidden carrying the modifier. Being its own kind is the point — no sweep reaches it and the card draws nothing. Both givable and takeable-away, so one take-away can cancel a whole bundle.

### Profile

*A fighter or vehicle entry — the thing a model is hired as.*

Fields of its own: **profile type** (Fighter or Vehicle — a closed set; Leader, Champion and Ganger are subtypes, not types), **gang type** (every profile belongs to one), and **offered for hire** (unticked for a model nobody hires directly — mostly that means a pet; an adds-a-model effect can still bring it in). It also takes option sets. Its statline shape follows its profile type. Its price is the fighter alone, to which its built-in sets' prices add at hire time.

### Weapon

*A weapon. Always has at least one firing line, the first of which is free.*

Fields of its own: **slots** (weapon slots used on a card; asterisked weapons take 2) and a **statline shape** (SR, LR, Str, AP, L — set once on the weapon; every firing line reads it from there).

A weapon's firing lines are assignables in their own right (WeaponProfile): the unnamed first line *is* the weapon, a named line is an ammo type, and buying one is an assignment hung off the weapon's assignment — so a stashed or reassigned weapon keeps its lines. Traits live on the lines, not the weapon; a weapon-level question ("has the Melee trait?") is derived from them.

**Weapon accessories** — sights, suspensors, focusing crystals — are their own type: assigned to a *weapon* rather than a model, hanging off that weapon's assignment, their effects landing on its firing lines. The book's bracket restrictions ("Las Weapons Only", "Weapons Marked With * Only") are stored as data on the accessory, informing at browse and attach, policing nothing.

### Wargear

*Equipment that isn't a weapon — armour, grenades, pets, field gear.*

Fields of its own: none — the shared set. It takes option sets (plain talons or razor-sharp). Carried by a model and priced like anything else. A thing that bolts onto a weapon is not wargear; that is a weapon accessory.

### Skills and Powers

*What a model has selected (skills) or manifests (powers), each homed in its set.*

Fields of their own: none. A skill's set is its home category — the same catalogue every collection shares — and its D6 number in the book is its position within that category. A power is the same shape: its home is a category too, so it appears in the same fighter-sectioned views as the skill sets with no special casing (the book's own move: Wyrds treat the powers list as a Secondary Skill Set). A power's annotation carries what the book prints in brackets — "(Free), Continuous Effect" — never rules text.

Both print on the card under their own headings. They arrive built in, given by a modifier, or chosen through an offered choice, and reach whoever holds them.

### Other types

- **Subtype** — *a model subtype: Leader, Ganger, Specialist, Mounted, Wyrd.* No fields of its own. Prints in the card's type line, and is what scopes match on ("Champion or Leader models").
- **Trait** — *a weapon trait: Melee, Rapid Fire (1), Knockback (6+).* The parameter is the annotation, so Knockback (5+) and Knockback (6+) are two rows. Lives on firing lines, never on the weapon itself.
- **Skill tree** — *"Agility" as a thing a gang can pick.* Most gangs never need one: a fixed skill set is just a category. Venators pick four and rank them, and a fact a gang owns has to be an assignment, which can only point at an assignable — this type fills that gap. Everything else about the set (its skills, where it sits for a fighter) belongs to the category. Chosen, so it takes no built-ins.
- **Counter** — *a named tally a model keeps: XP, Kill Count.* The definition is content; who has one is ordinary assignment (XP rides fighter built-ins, with its opening value on the set's member — the 61 in "Starting XP 61"); the running value is player-side, changed only by tallying, which writes ledger events. A modifier can also add to a counter ("Adds to a counter"), which raises the reading for as long as its carrier is held and writes nothing down. A reading is then the tallied value plus whatever contributes to it, and a counter with contributions but no assignment still has a reading. **Drawn** off means the counter is only there for conditions to check: it appears on no card and no fighter page. The point of counters is that effects hang off values: "when XP is at least 5" reveals a promotion choice the moment the threshold is crossed, computed like everything else.

### Collection

*A named list of content: an equipment list, a trading post, a menu.*

One field of its own: **prices its entries** — turned off for a menu, where nothing is for sale and the entries are simply choices.

It holds things two ways: manual **entry** (hand-picked rows, optionally at this list's own price, and optionally narrowed to who *this list* offers the item to — the "(Forge-born only)" case) and **selectors** (sweeps like "every weapon", at their usual prices); an entry always beats a selector for the same item.

Collections arrive built into something (a profile's list, a gang type's) or given by a modifier. Reach: held by the gang, every fighter may browse it; held by or given to one model, theirs alone.

Collections contain "sections" too — but these are not the same kind of Section as listed below, so let's call them "collection section" for a bit.

> Tom note: we are very likely to rename "collection sections" to Tiers, or possibly rename the "Section" object

Within a collection, when displayed, items are grouped by collection section and Category:

- Membership is entries and sweeps — *placement* has nothing to do with whether a *thing is in the collection*.
- Where it appears: when a fighter's view of a collection is built, everything unplaced falls into the collection's own default section (part of its schema, so its name and position are content too), or a code-level "Other", drawn last. So browsing Skills & Powers, an unplaced set ("category") is there, under Other.
- But narrowing excludes it: a Primary-narrowed picker (e.g. used by the "offers a choice" modifier, by setting that the choice comes "from section") only shows categories *placed* within that section. An unplaced skill category lives in Other, not Primary, so it isn't offered. The fighter's own skills screen narrows this way too: it is the *fighter's* view, so a set nobody placed for them isn't on it.
- The skills square on the edit page does not narrow. It draws every set the library holds, under two tabs: the sets a fighter's placements name (plus any they already hold something in) and, a click away, all of them. The placements sort that listing rather than shorten it — an owner settling what a model *is* may take a skill from any set, and a skill already held from an unplaced set could be removed nowhere else.

### Slot type

> Draft, for review.

*What is chosen: Gang Legacy, Affiliation, Clan House, Chaos God, Variant — and new ones are authored.*

Fields of its own: a **plural** (what several of them are called, so a page can say "Gang Legacies"), and **allows repeats** (whether one holder may pick the same pickable for two slots of this type).

A slot type puts a name on one or more slots, and groups pickables. It is not an assignable: nothing holds a slot type. Its slots, picklists and pickables all name it, and authoring refuses a mismatch — a picklist of one slot type cannot sit behind another type's slot. Which slot type something belongs to is settled when it is made and never changed afterwards; something in the wrong slot type is a new one, made in the right one. Its page is where the whole slot type is built: its pickables, its picklists, and its slots.

### Pickable

> Draft, for review.

*A value that goes into a slot.*

Fields of its own: the **slot type** it belongs to, and an optional **linked category** — plus the shared assignable set, so whatever the pickable means rides it as ordinary modifiers.

One thing offered in a slot: a specific value, of a particular slot type, that carries behaviour as ordinary modifiers. It never draws a row of its own: it appears under its slot's choice row when chosen. Without its slot it shows nothing and does nothing, so it arrives chosen, given, or as a slot's starting value — never as a bare built-in; the authoring form refuses one. Reach: whatever its own modifiers say, from wherever the pick landed.

The linked category is consulted for categorisation decisions: a rule that places "the chosen set" asks the pick which category it means, and the link is the answer. This is how a Skill Tree pick stands for the set it names — picking the Agility tree files the Agility category under whichever tier the asking rule says. Most pickables link nothing.

### Picklist

> Draft, for review.

*A flat, ordered list of pickables that the player chooses from.*

Fields of its own: a **slot type** and a **name**; and, where the list is a roll table, the **dice** it is rolled on and how a roll **selects** its row. Each pickable on it carries its place in the order and, where this list calls it something else, a wording of its own — and, on a roll table, the **band** of rolls that lands on it, "51" as readily as "21-26".

A set of pickables available in a slot. One slot type throughout, no headings and no prices — where a collection is a catalogue, this is a menu. One slot type may have several different picklists, which is how a limited selection of the pickables is made available in certain situations: what a leader picks from and what a champion picks from could be two lists of one slot type. Not an assignable; a slot names it.

A roll table is a picklist that names its dice and how a roll finds its row — the one row whose band holds it, or every row at or below it. The die is a closed set — D3, D6, D66 or 2D6 — so every roll it can produce is known. A band is plain numbers even on a D66, where "31-46" spans rolls that can never come up: a lookup only ever asks about a roll that did. Nothing rolls; the bands are authored and the picks are chosen.

### Slot

> Draft, for review.

*A fully configured slot containing pickables: a picklist, a label, and how many picks.*

Fields of its own: its **slot type** and **picklist**; the **label** shown on the card; **min** and **max picks**; **assigned to** (whether the pick lands on the bearer or on the gang); **hidden**; and a position among the slots on one card.

One specific, named use of a slot type. Assigning one to a model or gang — built into a profile, given by a modifier, or brought by an option when something is bought — causes the slot to show up. The card draws the label with what has been picked by the player, or what's set by default, or a control to pick, on the holder's own card and nowhere else: a slot the gang holds is asked once rather than on every fighter. Picking under the minimum adds a note on the card, never a refusal (no page prints these notes yet), and the picker stops offering at the maximum. A slot of one pick is settled by picking, and picking again replaces the pick; a slot of several is made a pick at a time, each option on the picker adding or taking back its own. A slot of nought picks asks nothing. **Hidden** makes the slot invisible while the pick still does everything it does — grouped hidden assignables, under one name.

### Picks

> Draft, for review.

*Not a type: the assignment that settles a choice.*

The pick is an ordinary assignment: the pickable, hosted where the slot says it lands, caused by the slot's own assignment and pointing back at it. So removing the slot removes the pick and everything the pickable gave; two slots of one slot type on one holder stay independent, even where one thing opened both; and nothing is worked out from what kind of thing was chosen. A pick is free and adds nothing to any rating.

A pick the gang holds is broadcast (but not displayed) to every member: a rule reaching "models with the Cawdor legacy" reaches them all, the fighter who was asked included. A pickable that carries the *draws the pick on the card* effect is displayed after all, on the cards its scope reaches — see below.

Where the slot type does not allow repeats, the picker marks the pickables already picked for another slot, and the card notes when one pickable is picked for two (no page prints these notes yet). Marks and notes, never locks: the narrowing informs, and an owner may still hand over a pickable no picklist offered.

---

## Core types & concepts

Hiding under a lot of the above is some shared underpinnings, which I've made reference to but might benefit from some more explanation.

### Assignable

*The shared shape of everything a gang, model or item can carry.*

Not a thing itself — pretty much every type above is "an assignable". The
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

Used as a home for *item* in a collection, so every collection groups it the same way — an autogun is an Auto/Stub Weapon everywhere. The same name may recur under different sections (Primitive Weapons under both Ranged and Close Combat).

A Category points at a Section, which is where the Category typically is organised. A Category's effective section can be changed ("placed") by a modifier.

### Section

*A heading of the catalogue, above categories — "Ranged Weapons".*

Fields: a name and a position. Nothing else.

A real object rather than free text so two spellings can't f(uc|or)k a collection. Never assigned, never reaches anything.

Who uses it: the gear surfaces — the equip pages group their catalogues by it (browse → _sectioned → group_by_home), and the ?section= in the equip page's URL names one of these.

Not to be confused with a collection sections — e.g. Primary and Secondary in the Skills & Powers collection. See above.

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
— free, and "caused by" the holder, so removing the holder takes them
along.

A member that is a firing line names which of the set's weapons it
rides, and is added from that gun's own row rather than from the
general picker. A set that brings no such weapon can still hold the
line — it then lands on whatever matching gun the acquirer already
holds, which is how an option arms a weapon the built-ins bring.

### Offers a choice (an effect)

*Puts an open question on the card; the player chooses one thing of a particular assignable type.*

Fields:

- the type it takes (exactly one — offering a choice of skill is not
settled by choosing a power)
- an optional collection section that narrows what a picker shows
- a **label** ("skill tree 1") naming the choice row on the card and picking which row it files into
- **will be assigned to** — whether the chosen thing lands on the bearer or on the gang.

(A minor third path exists: the code making the choice may name the host explicitly, which beats both — it is how a gang-carried offer that each fighter settles individually lands on the fighter who was clicked.)

> Tom note: we probably want to extend these to support multiple different types

### Draws the pick on the card (an effect)

*Lists the pick carrying it on the cards this modifier reaches.*

No fields: the scope is the whole of what it says. Carried by a pickable, so the line comes and goes with the pick, and it acts only on a pick **the gang** holds — a model's own pick is already the row of the choice that settled it.

The line is headed by the slot type's name ("Archetype") and holds what was picked. It leads nowhere: the choice is made and changed on the card that was asked for it, and that card draws its own choice row instead of this.

For an Outcast gang's archetype, picked by the leader and played by every model except the Champions, who pick one of their own.

### Ledger (entry + events)

*The append-only record of every purchase: what was asked, paid, and worth.*

Fields on an entry: list price, discount, paid, Trade Points, **rating contribution** (pinned forever — the "rating" half of the price/rating split), reason (bought, free, granted, default…), and which collection entry priced it.

Append-only; an entry's events must fold back to the entry, and reconcile checks exactly that. Ratings and credits are never nudged by differences — they are recomputed from this record and repinned. Rating sums the contributions of what models hold; the stash's rows count in wealth instead.

### Operation

*The only writer of player data; everything else just reads.*

Some kind of actual change. Assign, buy, hire, choose, remove, move: each writes the assignment, the ledger entry, and the events together. Settling ends every operation by repinning the stash, the rating, and the credits from the ledger; spending past the founding budget raises there and unwinds the whole transaction — one of few hard refusals in the app.

### Gang

*One player's gang: its type, its money, its colour.*

Fields: name, gang type, founding date, starting credits (blank means unlimited, and the Refund control hides), credits, colour.

Its rating is what its models are worth, recomputed from the ledger and pinned — never the stash. Its wealth is rating plus credits plus the stash's own pinned worth.

### Miniature

*One model on the roster; the class dodges Django's "Model"*

A model is a membership assignment naming a profile, plus everything riding it. Every user-facing word is "model" — the Python class name is the only place "miniature" appears.

### Stash

*The gang's pocket: gear held by nobody, counted in wealth*

Fields: none of its own beyond its link to the gang and its pinned worth. Created at founding.

A host like any other: can be assigned stuff. Its worth is repinned by every operation. Counts towards wealth.
