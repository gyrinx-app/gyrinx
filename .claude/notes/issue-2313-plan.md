# Spyrer suit evolution and tiered augmentations in n26

Plan for 2313. Written against the worktree `heron-8e7b-spyrer-tiers`, off
main 5d7440c15. Rules paraphrased from the local Spyre Hunting Party
reference; nothing quoted.

Decisions taken before planning (Tom, 2026-09-06): the default is a
cumulative ladder as printed; a player may switch or step back freely (inform,
never police); the Power Boost table belongs to this issue, not 706; the shape
must leave room for paid ladders later without repeating n23's
`ContentEquipmentUpgrade`.

## What the rules ask for

A Spyrer's rig counts kills. **Suit Evolution** is a post-battle act: with
Kill Count at four or more, spend four, then either clear every glitch
(Glitch Count to zero, and the penalties they caused with it) or roll D6 on
the **Power Boost** table and raise the model's credit value by what the
table says. Repeatable while four remain.

Power Boost: 1 raises WS or BS (ceiling 2+, +20); 2 Initiative (2+, +10);
3 Movement (8", +10); 4 armour save (2+, +15); 5-6 **Hunting Rig
Augmentation** — pick one weapon or piece of wargear the Spyrer carries and
raise its Augmentation level by one (+20). A result that would push a
characteristic past its ceiling is taken as an augmentation instead.

Each Spyrer item prints its own Tier 1/2/3 lines: a weapon characteristic set
to a value, a trait added, removed or swapped for the next value up, a
characteristic of the wearer raised, an armour save improved, and twice a
choice between two characteristics. Some items have two tiers, some three. A
Hunt Master's **Experienced Hunter** gives one free level on hire, and the
glitch result **System Downgrade** takes one back.

## 1. How to represent a ladder

**(a) A new library kind** — an `Augmentation` model with ordered rungs
pointing at the item. Cost: a new model, a union FK over weapon and wargear,
a column on `Assignment` plus a line in `ASSIGNABLE_FIELDS`
(`n26/core/models/assignment.py:41-61`, enforced at boot by `n26.E001`), a
`Spec`, a generated form, two registries in `n26/library/views.py`, a page in
`concepts.md`, migrations in both apps, and new prefetch paths in
`build_modifier_index` (`n26/core/card.py:938-1000`) — miss one and `compute`
lazy-queries, which it must not. It buys nothing the choice machinery lacks.

**(c) Rungs hosted under the item through `Assignment.parent`** — attractive
because `targets_attached_weapon()` would reach the weapon exactly. It does
not work as built: `reconcile_defaults` hosts what a carrier brings
*alongside* the carrier, not under it (`n26/core/operations.py:1762`), and
`n26/tests/sandbox/test_dustback_helamite.py:270` pins the consequence — that
scope reaches nothing when a thing is brought *by* an item rather than bolted
*to* one. Making it work means changing where built-ins land.

**(b) Slots and picks — recommended.** Per augmentable item:

- one `Picklist` of slot type **Augmentation** holding that item's tiers as
  `Pickable`s at positions 1..3;
- one `Slot` (label naming the item, `min_picks=0`, `max_picks` = the number
  of tiers, `assigned_to=bearer`), built into the item with `add_built_in`,
  so it appears when the item is carried and goes when the item goes.

A level is **one pick per rung, stacking**: at level 2 the model holds two
picks against that slot, and the level is the count of live picks — computed,
never stored. This matches the book's verb and keeps authoring one-to-one
with the printed lines; the alternative (one pick naming the level reached)
forces every rung's modifiers to be restated on the tier above it.

Each item gets **its own picklist and its own pickables** — "Tier 1 — Orrus
bolt launcher" is not "Tier 1 — Jakara rig". Picks land on the model, so a
shared "Tier 1" across items would collapse four augmented items into one
reading.

**How a tier's effects land.** Not `targets_attached_weapon()`, per above.
Name the item outright, as the Helamite claws do
(`n26/tests/sandbox/test_dustback_helamite.py:291-300`):

- weapon characteristics: `targets_weapons(is_one_of(bolt_launcher))` +
  `ef_changes_stat(lethality, mode="set", amount=2)`. `ChangesStat.accepts`
  admits weapon profiles as readily as models
  (`n26/library/models/modifier.py:1662`), proven at
  `n26/tests/sandbox/test_weapon_category_scope.py:161-183`. **Mind the
  vocabulary**: the seeded weapon shape is SR / LR / Str / AP / L
  (`n26/library/standard_content.py:36-68`), so the book's "Damage" is
  **Lethality**, and AP is inverted, so improve-by-1 takes -1 to -2.
- trait swaps: `ef_removes(rapid_fire_1)` plus `ef_adds(rapid_fire_2)` — a
  modifier holds one effect, so a swap is two modifiers on the pickable.
  Additions settle before removals within a round
  (`n26/core/effects.py:1058-1076`) and traits fold by display string
  (`effects.py:172-179`), so the pair is safe. "Remove Scarce" is the removal
  alone; "add Parry" the addition alone.
- the wearer: `targets_model()` + `ef_changes_stat(...)`. Armour save is a
  real characteristic (`Sv`, target and inverted,
  `n26/library/standard_content.py:45`), so "to 4+" is mode `set` amount 4,
  "+1" is mode `improve`.
- field armour saves are not characteristics: author them as a named `Rule`
  with an annotation and swap the pair, exactly as with a trait.
- **some printed lines have no column to land on.** The weapon shape has no
  Ammo and no accuracy modifiers, so "Ammo to 2+" and "improve the long range
  accuracy to -" become trait swaps (Ammo already rides as a trait
  annotation) or a named line with nothing computed. Settle these item by
  item while authoring.

**A two-way tier** (Malcadon rig T1: BS or WS) needs no `OffersChoice` — list
both as separate pickables. The same trick covers Power Boost result 1:
`Picklist.landing` returns *every* member whose band holds the roll
(`n26/library/models/slots.py:348-365`), so two members banded 1-1 both come
up and the player takes one.

**Ceilings are informed, never enforced.** `ChangesStat` has no cap field
(`modifier.py:1634-1664`) and `apply_changes` does not clamp
(`n26/core/render.py:1193-1225`). That is the right call: turning a capped
result into an augmentation is the player's act, not the app's.

## 2. Runtime model

"This item is at level 2" is two live `Assignment`s whose `chosen_for_slot`
is that item's slot. Nothing new is stored, and the card already draws the
slot as a `ChoiceLine` (`n26/core/render.py:387`, filled
`n26/core/effects.py:1597-1660`).

**Money.** The +20 belongs to the Power Boost result, not the rung — see §4.
Rung pickables are priced zero; Power Boost pickables carry 20/10/10/15/20.
`_choose_for_slot` hardcodes `paid=0` and lets `rating` fall through to zero
(`n26/core/operations.py:2190-2198` with `:358-366`), pinned by
`n26/tests/sandbox/test_slots_and_picks.py:207-218`. It already **forwards
`rating` in `**kwargs`**, so the change is to default it from the pickable's
own reference price. `op.select` is the in-house precedent for a free
acquisition that still adds rating (`operations.py:2374-2381`:
`paid=0, rating=price_of(thing).credits, reason=Reason.REWARD`).

**Ledger.** No new event kind. The pick writes the ordinary entry and event
through `assign` (`operations.py:284-396`) with `rating_contribution=20` and
`paid=0`; `Operation.settle` repins the model and the gang
(`operations.py:2516-2538`) and rating recomputes from the ledger. The roll
is already recorded as `ROLLED` (`operations.py:2383-2422`) and the Kill
Count spend as `TALLIED`. Removing a pick archives it and its rating stops
counting; no money comes back, because none went out.

## 3. Suit Evolution: mostly content, one small act

The Escape table is the precedent and it is **content only** — no code was
written for it (`n26/library/standard_content.py:1308-1345`, proven end to
end by `n26/tests/sandbox/test_escape.py`). Power Boost is the same shape,
and `SPYRER_GLITCH_TABLE` already sits where the new table goes
(`standard_content.py:1076-1099`, listed at `:1181-1187`).

**Power Boost, authored:** slot type *Power Boost* (repeats allowed), one
picklist with `dice="d6"`, `roll_selects="band"`, six bands over five
results with two members on band 1, one `Slot` (`max_picks` generous — this
repeats across a campaign) attached to the Spyrer subtype the way the glitch
table is (`n26/library/recipes.md:250-303`, step 4). Each result pickable
carries:

- its computed effect — `targets_model()` + `ef_changes_stat(...)` for 1-4;
- `op_changes_counter(kill_count, mode="subtract", amount=4)`, a **stored**
  effect that runs once when the pick lands
  (`n26/library/models/modifier.py:1522-1556`, driven by
  `_run_stored_effects`, `operations.py:398-414`);
- its price, which becomes the rating once §2's change is in.

So the whole rolled half is: the player opens the existing choose page
(`n26/core/views/choose.py`, `/gangs/<gang>/choose/<key>/`), clicks Roll,
takes a result. The spend, the stat change and the +20 all fall out. Do not
build a second picker.

**Do not gate the slot on the counter.** `counter_at_least(kill_count, 4)` on
the scope would hide the slot below four — and would take every pick already
made with it, because a pick whose slot has gone is excluded as an orphan
(`n26/core/effects.py:100-110`). Grant the slot unconditionally to Spyrers
and say the threshold in words. Inform, never police, and here it is also the
only safe option.

**Results 5-6** carry the spend and the +20 but no stat change. What follows
is the player raising one item's level, which is the ordinary choose page for
that item's augmentation slot. The Power Boost result's line should say so.

**A capped result** is substituted by the player: `_choose_for_slot`
deliberately does not check the pick against the band it landed on
(`operations.py:2135-2139`) because the rules substitute results. Print each
ceiling in the picklist member's `label_override` (list wording, so it never
rides the card) with a note saying what the rules do.

**Clear glitches is the one bespoke act.** It spends four Kill Count, zeroes
Glitch Count, and takes back the glitch picks carrying penalties. A per-model
view in the shape of `mark_fighter` (`n26/core/views/gangs.py:701-747`): a
dialog on the gang sheet keyed by a query parameter (`?evolve=<pk>`, beside
`?status=`), POST to its own route next to `n26-mark-fighter`
(`n26/urls.py:185`), inside one `operation(gang, actor=request.user)` calling
`op.tally` twice and `op.remove` on each live glitch pick. Registration is
the view, the `path()`, and the import plus `__all__` entry in
`n26/core/views/__init__.py`.

## 4. Switching, stepping back, refunds

Rungs are free, so switching or stepping back moves no money. What was
charged is the Power Boost result, which stays on the card as a line worth
20. Taking a rung back uses the verbs already there —
`rechoose_assignment` and `remove_assignment`
(`n26/core/views/owned.py:952, 1103`). `remove` archives and writes a
`REMOVED` event with no deltas (`operations.py:1010-1031`), so the rating
simply stops counting; `refund_of` pays back what was **paid**
(`operations.py:116-136`), which for a free pick is nothing. That is
"refunds follow the purchase" applied honestly: to lose the 20 the owner
removes the Power Boost result itself, which has its own verb. Note that the
Kill Count spend is a stored effect and is never undone — correct, since the
rules spent it.

Words on the augmentation choice: *The rules gain these one level at a time
through Suit Evolution. You can change it here.* The picker marks levels
already held.

**System Downgrade** lowers a level. Ship it as a result with no computed
effect and have the player take a rung back by hand, with the flow saying so;
an effect that retracts a pick is a later, general piece of work. Note also
that the seeded glitch table (`standard_content.py:1078-1099`) is an earlier
printing — no System Downgrade, Jammed Articulation, Disrupted Ammo Cables,
Cracked Power Cell or Reduced Power Distribution, which the text we hold puts
at 51-55. A content correction, not this issue's code.

**Rejected alternative:** pricing rungs cumulatively (20/40/60) so a step down
refunds itself. It double-counts against the boost line, makes the Hunt
Master's free level a special case, and spends the `price` field that a paid
ladder will want to mean a real purchase.

## 5. Experienced Hunter

A slot member can name a starting pick and the pick is written with it
(`operations.py:1811-1814`), but the free level is on an item the player
chooses at hire, so no built-in can name it.

Because rungs are free, nothing needs building. The slots are already open on
everything the Hunt Master carries and raising one takes nothing. All that is
wanted is that the card says so: the named `Rule` "Experienced Hunter" on the
profile, and one sentence in the augmentation choice's help. That is the
payoff of putting the money on the boost rather than the rung.

## 6. Paid ladders later

The minimal extension: a field on `Slot` saying its picks are bought, one
branch in `_choose_for_slot` taking the credits path, and rung pickables
carrying a real price. Ordering, levels, the card line, removal and refund
already exist.

Do not build now: no per-position price table, no cumulative-versus-
independent mode. n23's `ContentEquipmentUpgrade`
(`n23/content/models/equipment.py:627`) puts position and price on the rung
and the mode on the parent, so nothing can read a rung without first knowing
the parent's mode. Here the mode is not a field at all: a ladder is a slot
whose picklist is ordered and whose `max_picks` exceeds one; a set of
independent add-ons is the same shape without the order.

## 7. Content authoring

Per item: one picklist, two or three pickables, one slot, one built-in
attachment, and one or two modifiers per tier — roughly 22 items, plus the
Power Boost table. All through the existing authoring pages and verbs, so
`concepts.md` needs nothing new.

Ingest stays out of it: `n26/design/ingest.md` already rules upgrade ladders
hand-authored and out of the sheets, and the importer resolves weapon names
rather than creating them, so hand-author first. Write the walkthrough into
`n26/library/recipes.md` once the shape is agreed, in the register of the
Lasting Injury section beside it.

**Migrations:** none for the content shape. Leaves today are `library` 0089
and `n26` core 0062, with library 0090-0092 in flight on open PRs 2483 and
2485. Number last, repoint, and say so on the PR.

## 8. Work breakdown

Small and stacked (`gh stack`). n26 tests use `n26/tests/fixtures.py` and the
verbs in `n26/tests/sandbox/actions.py` — **not** the platform fixtures in
`gyrinx/conftest.py`, which `n26/tests/CLAUDE.md` forbids here. Every sandbox
test ends with `assert_reconciled(gang)`.

1. **A pick carries a rating.** `_choose_for_slot` defaults `rating` from the
   pickable's reference price, `Reason.REWARD`. Tests in
   `test_slots_and_picks.py`: a priced pickable moves the model's and the
   gang's rating, a free one does not, reconcile stays honest. Plus a guard
   that no shipped pickable is priced.
2. **The augmentation shape, content only.** New suite
   `n26/tests/sandbox/test_spyrer_augmentations.py`: build the Orrus bolt
   launcher and the Jakara rig from the book, hire a Spyrer, take Tier 1 then
   Tier 2, assert the card shows Lethality 2, AP -2, Rapid Fire (2) in place
   of Rapid Fire (1), and Strength up on the wearer. If the scopes hold this
   ships no production code — which is the point of it.
3. **The Power Boost table.** Seeded in `standard_content.py` beside the
   glitch table, the slot attached to the Spyrer subtype, the stored spend on
   each result. Tests with loaded dice: band 1 offers two members, four Kill
   Count goes, the rating moves by the table's figure, a capped result can be
   substituted, and the slot survives the count dropping below four.
4. **Clear glitches.** Route, dialog, the two tallies and the removals.
   Tests: the count zeroes, the penalty picks go, the history reads.
5. **Words and drawing.** The note on the augmentation choice, the Hunt
   Master sentence, `recipes.md`, a gallery sample. Copywriter pass.

A feature flag is probably unnecessary — nothing draws until the content
exists — but `n26/flags.py` is one line if 3 and 4 must land ahead of it.

## 9. Risks

- **Orphan picks.** Anything that makes a slot conditional can retract picks
  already made (`effects.py:100-110`). Grant the slots unconditionally. This
  is the trap most likely to be walked into.
- **Render cost.** Four augmentation slots on a Spyrer are four more choice
  lines and up to twelve rung picks. `compute` is O(nodes × modifiers ×
  rounds) and runs once per card per render (`n26/core/render.py:2525`), with
  no cache between requests. Take the query budget before and after using the
  existing budget assertions (e.g.
  `n26/tests/sandbox/test_gang_legacy.py:691-708`).
- **Rating on picks is a shared path.** Any priced pickable in prod would
  move a gang's rating on deploy. Check with `manage prodshell` before
  merging 1, and reconcile after.
- **Identity by display string.** Twenty items each with a "Tier 1": names
  are unique per pack, so the item belongs in the name or in the
  author-facing `qualifier`; the card prints the name alone.
- **Concurrent clicks.** `_choose_for_slot` runs under the gang's lock and
  one standing pick per roll is enforced there
  (`operations.py:2146-2153`), but `max_picks` is the picker's ceiling rather
  than the database's, so a race can overshoot by one. Tolerable here.
- **Migration numbering** against the open PRs above; collisions never
  conflict in git.
- **The seeded glitch table predates the printing we hold** (§4).

## 10. For Tom

1. Money on the boost or on the rung? This decides item 1 and the refund
   words. Recommendation: the boost.
2. *(Decided 2026-09-06: an owner may switch or step back freely; the app
   informs, never polices.)* Confirm the wording in §4 says enough.
3. Is the Hunt Master's free level just a note, or should the app open
   something for it?
4. Which printing of the glitch table is canon, and is correcting the seeded
   one part of this issue?
5. Should an item's augmentation choice draw under that item on the card, or
   among the model's other choices? The second is free today; the first is a
   change to `WeaponLine` (`n26/core/render.py:280-303`).
