# The skills surface on a miniature (n26)

Design note. Nothing here is built.

## The problem

A fighter's relationship with skills is fully expressed in content and fully
computed onto the card, and none of it reaches the UI beyond a single founding
pick.

What exists today:

- Skills are homed in set categories (`Skill.category`), and a `Collection`
  named "Skills & Powers" declares the tiers as its schema — Primary,
  Secondary, Other, with Other marked `is_default` (`standard_content.py`,
  `SKILL_TIERS`).
- A profile's **grid** is a set of `PlacesCategory` modifiers, one per
  (skill set, tier), carried by the profile. That is the per-entry access
  table, expressed as ordinary modifiers.
- `placements_for(computed, collection)` folds those off the computed card,
  scoped to one collection, lowest section position winning a conflict
  (`n26/core/browse.py:241`).
- `regrouped_by_placement(view, placements, fallback=…)` resections a browsed
  collection by those placements.
- `offered_by(slot, computed)` builds a founding pick out of exactly that
  machinery, then keeps one tier — "a shop with one section showing, not a
  second mechanism".
- The founding pick is an `OffersChoice`, drawn as a choice row on the card
  with a Choose control, answered by `Operation.choose`, which writes the
  answer as a free assignment caused by the carrier.

What is missing:

- **A fighter cannot see the sets they have access to**, only the one skill a
  founding offer let them pick.
- **A fighter cannot take an additional skill at all.** There is no operation
  for it and no screen.
- **The standard "Skills & Powers" collection is a schema with no contents.**
  It has three sections and zero entries and zero selectors, so browsing it
  today returns an empty view. This is the first thing that has to change and
  it is content, not code.

One consequence worth stating plainly: because that collection is empty, it
holds nothing of any family, so the newly built `containing(Family.GEAR)`
filter on the equip screen excludes it for the *wrong reason* right now
(emptiness). Once it is filled with skills, it is excluded for the right one.

## The recommended design

### 1. Standing access is the grid

**A fighter has access to a MODEL-family collection exactly where their
computed card places categories into that collection's sections.** No grant,
no built-in, no access table. The grid *is* the access, the same way a card is
the access to an equipment list.

Expressed against what exists:

```
learnable_for(miniature, computed) =
    for each collection in Collection.objects.containing(Family.MODEL):
        if placements_for(computed, collection):  ->  it is theirs
```

The `containing(Family.MODEL)` half is the queryset method built for the equip
screen; this is the second caller it was written for. It matters because a
placement into a *gear* collection's schema is possible in principle and must
not open a learn screen.

The edge cases, tested against the rule:

- **A profile with no grid.** No placements, so no access, so no Skills screen
  and no button. Recommended over "give them the default tier": the default
  section is where *unplaced categories fall for someone already browsing*; it
  is not a grant. Handing every gridless model the whole skill library is the
  same failure the equip strip was just fixed for — showing the reader the
  library rather than their own. The consequence is real and should be stated:
  a profile whose grid has not been authored has no Skills screen, silently.
  That failure is visible and cheap, and the fix is content.
- **A Venator-style tree pick.** `PlacesCategory.the_chosen` places whatever
  category the carrier's answered choice is homed in. Unanswered, no placement
  happens — so a Venator gang has no Primary until it picks its sets, and the
  screen appears when they do. That is the correct behaviour and it falls out
  of the rule rather than being coded.
- **Powers.** Powers are MODEL family and share the same collection and the
  same schema — the Wyrd subtype places the powers family into Secondary. So
  the *access* rule does not surface powers on everyone: nobody without that
  placement has the powers family placed. **But the browse does.**
  `regrouped_by_placement` deliberately keeps every unplaced category under
  the fallback tier ("inform, not police"), so a fighter with any Primary set
  would see the powers family, and every other house's sets, under "Other".

  Recommendation: **the learn view drops the unplaced tier.** Keep the
  fallback everywhere it already earns its place (the equip screen, and the
  roll-12 "any set your Type may use" pick, which wants exactly that), and
  narrow the learn view to the sections the fighter has placements into. One
  call — `narrow(placed, sections=[names of their placed sections])` — or a
  flag on `regrouped_by_placement` if it reads better. No model change.

### 2. Where it shows: two rows, doing two jobs

The card already carries both halves and they are not the same statement:

- The **Skills row** (`card.skills`) says what this fighter has, granted and
  chosen alike, told apart by provenance.
- A **choice row** says a question is open and unanswered. Folding a founding
  pick into Skills would make an obligation look like a possession the fighter
  happens to lack.

So: leave both. What is missing is only the way *out* of the card to the
collection.

Recommendation: **the control goes in the card's `actions` slot, beside
Equip** — not into the Skills row. The card's own contract says it is
read-only about the fighter and carries no controls over statlines, weapons or
skills; `actions` is a slot the *page* fills, which is exactly why Equip lives
there. A "Skills" button next to "Equip" is symmetric, discoverable, absent
from print sheets and previews for free, and needs no change to the card's
stance.

The card gains one computed value — the href, or empty when the fighter has no
access — computed in the view, per the project rule that display logic is
Python.

Alternative considered: a Learn control inside the Skills row. Closer to the
thing it changes, but it puts a write control on a structure that documents
itself as having none, and it has to be suppressed on every read-only
rendering by hand.

### 3. What taking an additional skill writes — needs a decision

**This is the honest answer: the write path needs a new operation and a
costing decision from the maintainer. It cannot be papered over.**

Why nothing existing fits:

- `Operation.choose` requires an anchor assignment whose assignable carries a
  matching `OffersChoice`, and raises when there is none. An additional skill
  has no offer and no carrier, so `choose` is not merely inconvenient here —
  it refuses.
- `Operation.buy` takes a browsed line and charges credits. Since every
  assignable is priced and a collection entry may override, a priced skills
  collection would technically work through the till today. That would decide
  the costing question by accident, in credits, which is not what the game
  says.

Two things must be settled:

**What anchors the row.** Two candidates:

- *Caused by the placement's carrier* — the assignment that placed the set
  (typically the fighter's profile). Mirrors `choose`; the skill vanishes if
  the carrier does.
- *Nothing* — a plain assignment on the miniature. Recommended. A skill a
  fighter learned is something they earned, not a consequence of a row that
  happens to still be there; a Legacy profile being removed should not
  unlearn it. `Reason.REWARD` is the existing vocabulary for it.

**What it costs.** n23 charges XP. In n26, XP is a `Counter` whose value moves
only through `Operation.tally`, and `tally` has no caller outside tests —
there is no XP spend, no affordability refusal for counters, and no
advancement table. Building one is its own programme: it needs a boundary
refusal in the shape of `NotEnoughCredits`, a story for how a counter
reconciles (credits are recomputed from the ledger; counter values are not),
and the advancement content itself.

Recommendation: ship **free and recorded** first — `op.learn(miniature,
skill)`, a zero-paid `Reason.REWARD` assignment with a ledger entry, rating
contribution equal to the skill's reference price (zero for every core skill,
so the default is no rating change and content can decide otherwise). Treat
XP spending as a separate piece of work with its own decision. This matches
the standing stance — inform, never police; owners may do anything — and it
does not quietly commit the edition to a currency.

### 4. The browsing screen: generalise the choose page, not the till

Recommendation: **reuse the choose page's machinery, addressed a second way.**

- `build_choice_offer(slot, computed)` already flattens a placement-resectioned
  view into groups of pickable options with notes, marks the current answer,
  and knows nothing about what kind of thing is being picked. The choose
  template already draws that shape.
- The equip page is a till: price boxes per row, a Buy per row, Trade Point
  columns, the `_charge` contract, the price-tampering defence. Every one of
  those is wrong for a skill and would have to be suppressed. "Buy semantics
  swapped for learn semantics" is most of the page.
- What the choose page cannot do is exist without a slot: its address is
  `<card>:<carrier>:<offer>` and `_find_slot` 404s when no computed slot
  matches. So the generalisation is a second address for the same shape —
  "browse this collection, for this fighter" — resolving through
  `placements_for` + `regrouped_by_placement` + the section narrowing above,
  and a POST that calls `learn` instead of `choose`.

One mechanism, not two: the shared piece is the offer structure and the
template that draws it; the slot flow and the learn flow become two callers of
it, differing in how they are addressed and what pressing does.

## Genuine alternatives

- **Access as an assignment.** Give fighters a Skills collection through their
  built-ins, the way they get an equipment list, and let the placements only
  *sort* it. Rejected: it duplicates a fact the grid already states, and the
  two would drift — a profile with a grid but no assignment would have tiers
  and no screen. It also reintroduces exactly the access table the placement
  design exists to avoid.
- **Skills as a tab on the equip screen.** Rejected, and the equip work just
  ruled it out in code: a MODEL-family collection is never an equip tab. The
  till's price boxes and Buy contract have no meaning for a skill.
- **A bespoke Skills page instead of a collection view.** Cheaper to write and
  immediately wrong: the sectioning, the usability notes, the "unusable by
  your Type" marks and the roll-12 narrowing all already exist on the browse
  path and would be rebuilt worse.
- **Charge credits now.** Works today with no new operation, since every
  assignable is priced. Rejected as a decision-by-default about the edition's
  economy.

## Staged build plan

1. **Content first.** Give the standard "Skills & Powers" collection its
   contents: a selector sweeping every skill, and one sweeping every power.
   Nothing below is testable end to end until it lists something.
2. **Access.** `learnable_for(miniature, computed)` in `n26/core/access.py`,
   built on `Collection.objects.containing(Family.MODEL)` and
   `placements_for`. Pure read, no new rows.
3. **Browse.** The learn view: resection by placements, drop the unplaced
   tier. A `CollectionView` in, a `CollectionView` out — composes with the
   usability notes as everything else does.
4. **The page.** The second address onto the picker shape, GET only at first.
   A reader can see their sets and what is in them before anything can be
   written.
5. **The write.** `Operation.learn`, free, `Reason.REWARD`, ledger entry,
   rating from reference price.
6. **The card.** The href, computed in the view, and the button in `actions`.

Stages 1–4 are shippable on their own and are the whole of the "it was in the
tests and never reached the UI" complaint.

## What to test

- **Access.** A fighter whose profile has a grid has the collection; one
  without has nothing. A Venator has nothing before their trees are picked and
  the placed sets after. A gear collection with placements into it is never
  learnable.
- **Sectioning.** Two entries with different grids see the same sets under
  different tiers, from one collection and one rule — the assertion the Escher
  sandbox already makes about the founding offer, now made about the whole
  screen.
- **The unplaced tier.** A fighter with a Primary set does not see the powers
  family, nor another house's sets, on the learn screen; the roll-12 narrowing
  still can reach them.
- **Usability.** A skill restricted to Walkers stays in the listing with its
  note, and is not removed — inform, never police.
- **Queries.** The screen is a fixed number of queries as the number of skills
  and sets grows, in the way the equip and hire listings are.
- **The write.** Learning writes one assignment, one ledger entry, no credit
  movement, and survives removal of the profile that placed the set. Reconcile
  stays clean.
- **The card.** No access, no button. Access, a button leading to the screen.
  A print sheet and a preview draw neither.

## Decisions needed from the maintainer

1. **Does learning a skill cost anything yet?** Recommendation: no — free,
   recorded, `Reason.REWARD`, rating from the skill's reference price (zero
   today). XP spending becomes its own piece of work, because it needs a
   counter affordability refusal, a reconcile story for counters, and an
   advancement table, none of which exist.
2. **Does a learned skill survive its profile?** Recommendation: yes — no
   `caused_by`. An earned skill is not a consequence of a row still being
   there.
3. **Does the learn screen show sets the fighter has no tier for?**
   Recommendation: no. Show only their placed tiers, and keep the
   show-everything fallback for the equip screen and the roll-12 pick.
4. **What does a fighter with no grid see?** Recommendation: no Skills screen
   and no button — with the consequence accepted that an unauthored grid is
   silently a missing screen.
5. **Where does the control live?** Recommendation: the card's `actions` slot,
   beside Equip, rather than a control inside the Skills row — the card
   documents itself as carrying no controls over skills.
