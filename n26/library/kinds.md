# N26 Core Types

Fact-based specs: a summary under fifteen words, the fields a type has of
its own, and its behaviour — reach and how it arrives.

## Assignment

**An assignment has three components**: *what* is held (an **assignable** — a weapon, a skill, an affiliation…), *who it is assigned to* (the **host**), and *what brought it* (its **cause** — remove the cause and the assignment goes too). Nothing gets onto a card any other way; everything from a hired fighter's profile to a granted rule is one of these assignments.

An **assignable** is typically very simple: an piece of data that, once assigned, can carry modifiers. Sometimes they have extra configuration. Affiliation, Rule and Skill are all assignables.

The **host** is the specific object the assignment sits on: a model, the gang, a parent item (a scope fitted to a gun), or the stash *only*. Host decides *reach*: a assignment hosted on a model is that model's; a assignment hosted on the gang is **brodcast** to every member's card.

The **cause** is then the action that brought a particular assignment into existence, answer "why is this here?" Cause powers one important behaviour: **removal cascades down the cause chain**. Remove an assignment and everything caused by it (and caused by *those*, recursively) goes too. It's also where provenance comes from — the card can say "came with X" because the assignment knows its cause.

A **modifier** is attached to a specific instance of an assignable (e.g. Aranthian Affiliation) which we call the **carrier**, asserting who it reaches (**scope**), and what it does (**effect**). Conditions limit the scope — AND-ed across conditions, any-of within a single condition — to allowlist modifier effects only in certain contexts.

Modifiers are shared by design: they can attach on any number of specific assignables ("carriers"), and editing the modifier.

Effects are split by when they happen:

- **computed** ones (gives, takes away, changes a stat, offers a choice, places a category, notes a limit) are re-derived on every read and vanish with their carrier
- **written** ones (brings a model, moves a counter) run once at arrival and are never undone by removal.

We use **carrier** as a library-side word for one specific piece of *content*, typically becuase they "carry" a modifer. A power maul carries its "+1 Strength" modifier; the Clan House affiliation carries a choice of affiliation from Clan Houses. Carrier is about authoring — edit the carrier's modifier and it changes everywhere that carrier appears.

**Bearer** is use to describe the thing being affected by a modifier. The maul's modifier says "+1 Strength *to its bearer*" — whoever holds a *specific* maul, no name attached.

So: you buy a power maul for Vex. The purchase writes one assignment — **assignable**: the maul, **host**: Vex, **cause**: the purchase. The maul's assignments points at its underlying **assignable**, which is a **carrier** of a **modifier** which now applies to its **bearer** — Vex. When the maul **assignment** is reassigned, at which point the same row gets a new host and the modifier follows the maul, not Vex.

Often the host and the bearer coincide. But when the Outcast Leader picks an Archetype, the resulting chosen Archetype is assigned *to the gang*. When the gang is the the host, every model sees it (and become the bearer), even though the Leader was the one asked:

1. Leader's Profile (asignable) carries a modifier that offers an Archetype choice ("will be assigned to" = "the gang")
2. Choice made → one assignment row: assignable = the archetype, host = the gang, cause = the Leader
3. Gang-hosted ⇒ broadcast to every model (but hidden, just used to apply modifiers)
4. On each model, the archetype is the carrier of its modifiers, and they resolve against it as the bearer

## Hiring

Hiring is a gang-hosted assignment which points at a specific profile, and which
materialises its built-ins onto the new model ("minature" below, internal terminology):

What the hire operation actually does, in order:

1. Writes a membership assignment: an assignment pointing at a profile, hosted on the gang, with the credits-paid information on it
2. Creates the Miniature, pointing back at that assignment. The model shown in the Gan is this pairing: a membership assignment plus a name.
3. Sets "miniature root" on the membership assignment, pointing at the miniature. The assignment is hosted on the gang — the fighter is assigned to the gang — but the profile on the assignment sets their base rating,
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

Typically chosen; the offers-a-choice modifiers say "bearer:, so it reaches is the one model that picked it.

### Gang type

*A kind of gang — Escher, Ironhead Squats — assigned to the gang at founding.*

Fields of its own: an icon (stored artwork, drawn inline so it takes the text's colour; addresses resolve only against this site's storage).

Assignable for the same reason a profile is: founding is a gang-hosted assignment naming the type. That gives the gang's built-ins something to be caused by (the house list arrives this way), and gives gang-wide modifiers a carrier. Mostly overrides and extras — the fighter entries are profiles, and each entry's skill access rides that profile. Its pricing fields stay at zero; nobody buys a gang type.

### Hidden

*A carrier for effects that draws no row of its own.*

Fields of its own: none. Its name is authored to be read on the pages that explain things; its kind is never said.

The bundle mechanism: some printed rules are a side effect with no item behind them (the Arachni-Rig's guns each knock a point off Attacks), so the option's set includes a hidden carrying the modifier. Being its own kind is the point — no sweep reaches it and the card draws nothing. Both givable and takeable-away, so one take-away can cancel a whole bundle.

### Profile

*A fighter or vehicle entry — the thing a model is hired as.*

Fields of its own: **profile type** (Fighter or Vehicle — a closed set; Leader, Champion and Ganger are subtypes, not types), **gang type** (every profile belongs to one), and **offered for hire** (unticked for a model nobody hires directly — mostlys that means pet; a adds-a-model effect can still bring it in). It also takes option sets. Its statline shape follows its profile type. Its price is the fighter alone, to which its built-in sets' prices add at hire time.

### Collection

*A named list of content: an equipment list, a trading post, a menu.*

One field of its own: **prices its entries** — turned off for a menu, where nothing is for sale and the entries are simply choices.

It holds things two ways: manual **entry** (hand-picked rows, optionally at this list's own price) and **selectors** (sweeps like "every weapon", at their usual prices); an entry always beats a selector for the same item.

Collections arrive built into something (a profile's list, a gang type's) or given by a modifier. Reach: held by the gang, every fighter may browse it; held by or given to one model, theirs alone.

Collections contain "sections" too — but these are not the same kind of Section as listed below, so let's call them "collection section" for a bit.

> Tom note: we are very likely to rename "collection sections" to Tiers, or possibly rename the "Section" object

Within a collection, when displayed, items are grouped by collection section and Category:

- Membership is entries and sweeps — *placement* has nothing to do with whether a *thing is in the collection*.
- Where it appears: when a fighter's view of a collection is built, everything unplaced falls into the collection's own default section (part of its schema, so its name and position are content too), or a code-level "Other", drawn last. So browsing Skills & Powers, an unplaced set ("category") is there, under Other.
- But narrowing excludes it: a Primary-narrowed picker (e.g. used by the "offers a choice" modifier, by setting that the choice comes "from section") only shows categories *placed* within that section. An unplaced skill category lives in Other, not Primary, so it isn't offered. Same for the skills square on the edit page: that surface is the *fighter's* view — their placements — so a collection that hasn't been placed for them isn't shown.

---

## Core types & concepts

Hiding under a lot of the above is some shared underpinnings, which I've made reference to but might benefit from some more explaination.

### Assignable

*The shared shape of everything a gang, model or item can carry.*

Not a thing itself — pretty much every type above is "an assignable". The
shared fields: name; annotation (printed in brackets after the name);
qualifier (tells two same-named things apart for authors — a player never
sees it); author help; price; Trade Point price; an exclusive flag
(equipment-list only, never at the Trading Post); a home category (where
it sorts in any list); built-ins (what arrives free with it); its
modifiers.

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
