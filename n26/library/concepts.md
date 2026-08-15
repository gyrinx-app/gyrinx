# N26 Core Types

This should give you a solid grounding in how Gyrinx N26 fits together.

If you take nothing else away:

1. **To control who gets a thing, control where it lands — don't look for a per-type switch.** Want it gang-wide? Build it into the gang type, or have a choice whose "will be assigned to" field is "the gang". Want it on one model? Build it into the profile, or pick "the bearer". There is no "make this broadcast" setting on an archetype or a rule — reach is entirely a consequence of the **host**, so you aim content by choosing its arrival route.

2. **Behaviour is always a modifier on a carrier — and modifiers are shared, so edit with care.** A rule, an archetype, an affiliation are just names; everything they do rides them as modifiers (scope + effect, conditions ANDed). Two practical consequences: to make content do something, attach the modifier to the thing that should carry it; and before editing an existing modifier, check its carriers — the change lands everywhere it's attached. Know the two effect families: computed effects (gives, takes away, stat changes, choices, placements, limits) come and go with their carrier and are safe to rework; written effects (brings a model, moves a counter) happen once and won't undo — author those as one-way doors.

3. **Being in a collection and being offered from a section of it are two separate authoring acts.** Entries and sweeps decide **membership** of the collection; **placement** decides whether a particular category appears. If you narrow a choice "from section: Primary" and the skill's category hasn't been placed into Primary for that fighter, it will not be offered — it's sitting in "Other". So a working "choose a Primary skill" needs both halves authored: the content in the collection, and a placement putting its category in that section for the right models.

4. **Use qualifiers and help text**. Assignables come with a qualifier is that is internal, for telling twins apart and disambiguation, and library text shows up next to objects in most places. Use it to make things clearer.

## Assignment

**An assignment has three components**: *what* is held (an **assignable** — a weapon, a skill, an affiliation…), *who it is assigned to* (the **host**), and *what brought it* (its **cause** — remove the cause and the assignment goes too). Nothing gets onto a card any other way; everything from a hired fighter's profile to a granted rule is one of these assignments.

An **assignable** is typically very simple: a piece of data that, once assigned, can carry modifiers. Sometimes they have extra configuration. Affiliation, Rule and Skill are all assignables.

The **host** is the specific object the assignment sits on: a model, the gang, a parent item (a scope fitted to a gun), or the stash *only*. Host decides *reach*: an assignment hosted on a model is that model's; an assignment hosted on the gang is **broadcast** to every member's card.

The **cause** is then the action that brought a particular assignment into existence, answering "why is this here?" Cause powers one important behaviour: **removal cascades down the cause chain**. Remove an assignment and everything caused by it (and caused by *those*, recursively) goes too. It's also where provenance comes from — the card can say "came with X" because the assignment knows its cause.

A **modifier** is attached to a specific instance of an assignable (e.g. Aranthian Affiliation) which we call the **carrier**, asserting who it reaches (**scope**), and what it does (**effect**). Conditions limit the scope — AND-ed across conditions, any-of within a single condition — to allowlist modifier effects only in certain contexts.

Modifiers are shared by design: they can attach on any number of specific assignables ("carriers"), and editing the modifier changes it everywhere it is carried.

Effects are split by when they happen:

- **computed** ones (gives, takes away, changes a stat, offers a choice, places a category, notes a limit) are re-derived on every read and vanish with their carrier
- **written** ones (brings a model, moves a counter) run once at arrival and are never undone by removal.

We use **carrier** as a library-side word for one specific piece of *content*, typically because they "carry" a modifier. A power maul carries its "+1 Strength" modifier; the Clan House affiliation carries a choice of affiliation from Clan Houses. Carrier is about authoring — edit the carrier's modifier and it changes everywhere that carrier appears.

**Bearer** is used to describe the thing being affected by a modifier. The maul's modifier says "+1 Strength *to its bearer*" — whoever holds a *specific* maul, no name attached.

So: you buy a power maul for Vex. The purchase writes one assignment — **assignable**: the maul, **host**: Vex, **cause**: the purchase. The maul's assignment points at its underlying **assignable**, which is a **carrier** of a **modifier** which now applies to its **bearer** — Vex. When the maul **assignment** is reassigned, the same assignment gets a new host and the modifier follows the maul, not Vex.

Often the host and the bearer coincide. But when the Outcast Leader picks an Archetype, the resulting chosen Archetype is assigned *to the gang*. When the gang is the host, every model sees it (and becomes the bearer), even though the Leader was the one asked:

1. Leader's Profile (assignable) carries a modifier that offers an Archetype choice ("will be assigned to" = "the gang")
2. Choice made → one assignment row: assignable = the archetype, host = the gang, cause = the Leader
3. Gang-hosted ⇒ broadcast to every model (but hidden, just used to apply modifiers)
4. On each model, the archetype is the carrier of its modifiers, and they resolve against it as the bearer

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

### Archetype

*A way of leading the gang, chosen once; its whole meaning rides as modifiers.*

Fields of its own: none — only the shared set. The card prints it under its own "Archetype" heading.

Chosen, not bought: refuses built-ins (nothing would ever hand over items built into it), arrives free through an offered choice, leaves when the thing that offered it leaves. Reach: whatever the offer's landing spot gives it — the whole gang for the Outcast shape, one model for a Champion's personal pick.

### Affiliation

*Who the gang sides with, chosen once when the gang is created.*

Fields of its own: none. Same chosen-not-bought shape and built-ins refusal as archetype.

Its payload is usually access — equipment lists opened to some ranks — so its gives are typically scoped ("to Leaders and Champions") while the affiliation itself rides gang-wide. It may itself offer the next choice (Clan House: "choose one of the six Houses"), which simply computes into another open slot on the gang.

### Rule (special rule)

*A named special rule on a card; its text stays in the book.*

Fields of its own: none — but its annotation is part of its identity: a rule in variants share one printed name. We store the name, never the wording (copyright). A rule that also *does* something the app can work out carries ordinary modifiers.

Normally it arrives built into something (a profile's kit, a gang type) or given by a modifier. Reach: built into a profile, it hits the model's card; when given to the gang, every member's card. The card prints rules apart from skills, under their own heading.

Author note: we actually, mostly, don't want broadcast for gang rules. Instead we'd want to attach modifier which hits the models.

### Specialisation

*The field a Specialist picks, which grants them its skill.*

Fields of its own: none. The granting is an ordinary give riding it — being pickable is the only new thing about it.

Typically chosen; the offers-a-choice modifiers say "bearer", so it reaches the one model that picked it.

### Gang type

*A kind of gang — Escher, Ironhead Squats — assigned to the gang at founding.*

Fields of its own: an icon (stored artwork, drawn inline so it takes the text's colour; addresses resolve only against this site's storage); **starting credits** (a founding-budget override for gangs of this type); and **foundable** (whether a player may create one — off for a type that exists to be hired from or fought).

Assignable for the same reason a profile is: founding is a gang-hosted assignment naming the type. That gives the gang's built-ins something to be caused by (the house list arrives this way), and gives gang-wide modifiers a carrier. Mostly overrides and extras — the fighter entries are profiles, and each entry's skill access rides that profile. Its pricing fields stay at zero; nobody buys a gang type.

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

*What a model has learned (skills) or manifests (powers), each homed in its set.*

Fields of their own: none. A skill's set is its home category — the same catalogue every collection shares — and its D6 number in the book is its position within that category. A power is the same shape: its home is a category too, so it appears in the same fighter-sectioned views as the skill sets with no special casing (the book's own move: Wyrds treat the powers list as a Secondary Skill Set). A power's annotation carries what the book prints in brackets — "(Free), Continuous Effect" — never rules text.

Both print on the card under their own headings. They arrive built in, given by a modifier, or chosen through an offered choice, and reach whoever holds them.

### Other types

- **Subtype** — *a model subtype: Leader, Ganger, Specialist, Mounted, Wyrd.* No fields of its own. Prints in the card's type line, and is what scopes match on ("Champion or Leader models").
- **Trait** — *a weapon trait: Melee, Rapid Fire (1), Knockback (6+).* The parameter is the annotation, so Knockback (5+) and Knockback (6+) are two rows. Lives on firing lines, never on the weapon itself.
- **Skill tree** — *"Agility" as a thing a gang can pick.* Most gangs never need one: a fixed skill set is just a category. Venators pick four and rank them, and a fact a gang owns has to be an assignment, which can only point at an assignable — this type fills that gap. Everything else about the set (its skills, where it sits for a fighter) belongs to the category. Chosen, so it takes no built-ins.
- **Lasting effect** — *what the Lasting Injury and Lasting Damage tables deal out.* One type for both; the card calls it by the profile type's own word ("Injury" for fighters, "Damage" for vehicles). Recorded on all of a model's cards.
- **Counter** — *a named tally a model keeps: XP, Kill Count.* The definition is content; who has one is ordinary assignment (XP rides fighter built-ins, with its opening value on the set's member — the 61 in "Starting XP 61"); the running value is player-side, changed only by tallying, which writes ledger events. The point of counters is that effects hang off values: "when XP is at least 5" reveals a promotion choice the moment the threshold is crossed, computed like everything else.

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
- But narrowing excludes it: a Primary-narrowed picker (e.g. used by the "offers a choice" modifier, by setting that the choice comes "from section") only shows categories *placed* within that section. An unplaced skill category lives in Other, not Primary, so it isn't offered. Same for the skills square on the edit page: that surface is the *fighter's* view — their placements — so a collection that hasn't been placed for them isn't shown.

### Slot type

> Draft, for review.

*A domain of choice — Gang Legacy, Affiliation, Archetype — and everything authored in it.*

Fields of its own: a **plural** (what several of them are called, so a page can say "Gang Legacies"), and **allows repeats** (whether one holder may pick the same option for two choices of this domain).

Not an assignable: nothing holds a domain. It is what the other three name, and authoring refuses a mismatch between them — a list of Affiliations cannot sit behind a Gang Legacy choice. Which domain an option, a list or a choice belongs to is settled when it is made and not offered again afterwards: moving one would leave a list offering options its choice could not take, and every pick already made answering nothing. Something in the wrong domain is a new one, made in the right one. Its page is where the whole domain is built: its options, its lists, and the choices that draw on them.

### Pickable

> Draft, for review.

*One option a choice offers: Cawdor, Clanless, Brawler.*

Fields of its own: the **slot type** it is an option in — plus the shared assignable set, so whatever the option means rides it as ordinary modifiers.

It never draws a row of its own: it appears under its choice's row as the answer. Without its choice it shows nothing and does nothing — an option nobody was offered is not something the holder has — so it arrives chosen, given, or as a choice's starting value, and the authoring form refuses one built in on its own. Reach: whatever its own modifiers say, from wherever the pick landed.

### Picklist

> Draft, for review.

*The options behind a choice: a flat, ordered list of one domain's options.*

Fields of its own: a **slot type** and a **name**. Each option on it carries its place in the order and, where this list calls the option something else, a wording of its own.

No sections, no placements, no prices — where a collection is a catalogue, this is a menu. One domain may have several: what a leader chooses from and what a champion chooses from are two lists over one domain. Not an assignable; a choice names it.

### Slot

> Draft, for review.

*A choice put on a card: a list of options, a label, and how many picks.*

Fields of its own: its **slot type** and **picklist**; the **label** the card calls the choice by; **min** and **max picks**; **assigned to** (whether the pick lands on the bearer or on the gang); **hidden**; and a position among the choices on one card.

Assigning one is what puts the choice on a card — built into a profile, given by a modifier, or brought by an option when something is bought. The card draws the label with what has been picked, or a control to pick, on the holder's own card and nowhere else: a choice the gang holds is asked once rather than on every fighter. Fewer picks than the minimum is a note on the card, never a refusal, and the picker stops offering at the maximum. A choice of one is answered by picking, and picking again replaces the answer; a choice of several is made a pick at a time, each option on the picker adding or taking back its own — full, it offers the rest again once one has been taken back. A choice of nought asks nothing. **Hidden** draws no choice row at all while what is picked still applies, which is how several things arrive together under one name.

### Picks

> Draft, for review.

*Not a type: the assignment that settles a choice.*

Choosing writes an ordinary assignment — the option, hosted where the choice says it lands, caused by the choice's own assignment and pointing back at it, and naming the choice row it settles. So removing the choice removes the pick and everything the option gave; two choices of one domain on one holder stay independent, even where one thing opened both; and nothing is worked out from what kind of thing was chosen. A pick is free and adds nothing to any rating.

A pick the gang holds is a fact about every model in it: a rule reaching "models with the Cawdor legacy" reaches them all, the fighter who was asked included.

Where the domain takes one option once, the picker marks the options already spent on another choice, and the card says when one option has answered two. Marks and notes, never locks: the narrowing informs, and an owner may still hand over an option no list offered.

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
