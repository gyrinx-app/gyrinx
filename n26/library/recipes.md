# Recipes

How to build specific rulebook setups out of the library's pieces. Each
recipe is a set of steps to follow in the authoring pages — the things to
create, and how to join them. A recipe is written here the day we settle
how its setup is authored, so this page grows with the library.

Where a step is not yet possible, it says so plainly.

## Corrupted gangs

Genestealer Cult, Chaos and Malstrain corruption are one build with
different contents: a corruption is a choice the gang makes once, and
everything it does rides the chosen item as ordinary modifiers.

### The choice

1. Create an **affiliation** for each corruption — "Genestealer Cult
   Corrupted", "Chaos Corrupted", "Malstrain Corrupted".
2. Create a **collection** named "Corruptions" and switch off *Prices its
   entries* — it is a menu, not a shop. List the three affiliations in it.
3. Create a **modifier**: targets the gang, *offers a choice* of
   affiliation from that menu, labelled "Corruption". Attach it to every
   gang type that can be corrupted.

Every gang of those types now shows an open "Corruption" question on its
sheet. Most players never answer it. The ones who do pick one affiliation,
and everything below hangs off that pick.

### What a corruption grants

Each of these is a modifier carried by the corruption's affiliation.

**New fighters to hire.** Create the profiles — Aberrant, Abominant,
Helot Cult Witch, Chaos Spawn, Brood Scum. Create a collection listing
them at their prices. On the affiliation: targets the gang, *gives* the
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
Champions, and put it in a collection. On the affiliation: targets models
that are Leaders or Champions, *gives* that collection.

**Extra Arm on Prospects.** Create a **wargear** named "Extra Arm" at 20
credits, usable by Prospects, carrying *gives* the Extra Arm rule. List
it in the corruption's collection.

**A god to dedicate to (Chaos).** Create an affiliation per god, and a
menu collection listing the four. On the Chaos affiliation: targets the
gang, *offers a choice* from that menu, labelled "Dedicated to". Anything
one god means rides that god's affiliation the same way.

**Post-cycle actions (Chaos).** Create each action as a **rule**. On the
affiliation: targets the gang, *gives* the rule. They print on the gang's
card.

**Counts and bans.** Each is one modifier on the affiliation. For "0–2
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
special rules onto it: one *gives* modifier per rule, aimed at the gang
where the rule prints on its sheet and at the model where every fighter
has it. The rules are then granted rather than built in, so there is a
single thing standing behind the lot. On each corruption's affiliation,
add *takes something away* naming that hidden item — aimed at the gang
and at its models, the same two aims the *gives* modifiers use. Everything
the hidden item was handing out goes with it, and drop the corruption and
it all comes back. Starting Skills and Skill Access live on the fighter
entries, so they are untouched either way.

## An item one list restricts

Some lists print a restriction beside a line that other lists print
plainly: the Goliath equipment list's "Heavy rock saw (Forge-born only)",
where the Genestealer Cult and Corpse Grinder lists offer the same saw to
anyone. The restriction belongs to that one list's offer.

1. List the item on the collection as usual — one entry, at whatever
   price the list charges.
2. On that entry, name what the book names in the bracket: *offered to
   fighter entries* for "(Forge-born only)", *offered to subtypes* for a
   line the list offers only to Leaders and Champions, *offered to
   specialisations* for "(Gunner specialist only)". Leave it blank on
   every other list that offers the item.

The saw still shows on the list for everyone, marked for the fighters the
list does not offer it to, and an owner may buy it for them anyway.
Nothing is refused — the list says.

Three places a restriction can go, and which one to reach for:

- **On the entry**, as above: one list narrows one of its lines.
- **On the item**, for what is true of it wherever it is listed — a
  saddle no model without a mount can use. This one is not yet
  authorable on these pages: it arrives with a spreadsheet import.
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
