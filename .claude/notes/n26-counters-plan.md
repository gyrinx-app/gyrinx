# n26: drawing and editing counters

## The bug that started this

A Spyre Hunt Master hired into a new gang gets `Kill Count` and `Glitch Count`
as built-in grants from their subtype, alongside `XP`. The grants land
correctly — prod shows all three as live assignments with `CounterValue` rows —
but the card draws none of them.

`model_card()` in `n26/core/render.py` drops every counter that is not XP:

```python
elif isinstance(thing, Counter):
    if thing.name.casefold() == XP_COUNTER.casefold():
        counted_xp = _counter_value(node)
```

Anything else falls out of the loop with nowhere to go — `ModelCard` has no
field for it. `test_a_counter_is_not_drawn_as_a_piece_of_equipment` locks in
"a counter is not equipment" but never asks for a counter line instead.

Counters *do* draw on the gang sheet (`GangSheet.counters`, from
`counter_readings(gang_card)`), but that reads gang-hosted counters only, so a
model's never reach it.

Second gap behind the first: nothing can change a counter by hand. `op.tally`
has exactly one non-test caller — a Tally modifier firing off an assignment
(`n26/library/models/modifier.py`). No view, no route. XP included: there is
today no way to give a fighter XP.

Prod holds three counters in total: `XP`, `Kill Count`, `Glitch Count`.

## The rules these serve

From The Book of Desolation p28 (Spyre Hunting Party).

**Kill Count** is a currency, not a score. "In addition to gaining XP, each time
a Spyrer takes an enemy fighter Out of Action, increase the Spyrer's Kill Count
by one." It accrues off the same event as XP and is spent on a separate track.

**Suit Evolution** is a post-battle action. With Kill Count at 4 or more, reduce
it by 4 and take one of: clear all glitches (Glitch Count to zero, and remove
the negatives the glitches caused), or roll D6 on the Power Boost table, apply
it, and raise the fighter's credits value. Repeatable while Kill Count is still
at least 4 — so a good battle might drain 8 or 12 in one sequence.

**Power Boost (D6)**: 1 Combat Neuroware (+1 WS or BS, max 2+, +20cr); 2
Heightened Reactions (+1 I, max 2+, +10cr); 3 Improved Motive Power (+1 M, max
8", +10cr); 4 Thickened Armour (+1 save, max 2+, +15cr); 5-6 Hunting Rig
Augmentation (one weapon or wargear +1 Augmentation level, +1 more if a
characteristic would exceed its max, +20cr). Any roll that would push a
characteristic past its maximum becomes Hunting Rig Augmentation instead.

**Glitch Count** is a death clock. A Spyrer taken Out of Action rolls D66 on
Spyrer Hunting Rig Glitches rather than the Lasting Injury table. Results 41-64
each read: Convalescence, +1 Glitch Count, and one penalty (a characteristic
down, a weapon's Ammo or AP worsened, an Augmentation level lost). 11 gains D3
XP and no glitch; 12-36 carry no glitch; 54 adds a standing risk; 65 rolls D3
more times; 66 kills outright.

The kill switch: during Purchase Advancements, if Glitch Count is higher than
Toughness the rig shuts down and the fighter is deleted with all their
equipment. Vicious, because result 64 lowers Toughness — a bad run moves the
threshold down while pushing the count up. That is why the number has to be
legible on the card.

**What it means here.** Both counters persist across battles and move in both
directions. Clearing the glitch *penalties* is not a counter act — those are
stat edits and lasting effects modelled elsewhere; Suit Evolution only zeroes
the count. Every act that moves either belongs to a post-battle sequence n26
does not have yet, so hand-editing on the model's own page is the right shape
for now.

## Scope

Settled with Tom, 2026-08-31.

- Draw counters everywhere a card draws: gang sheet, fighter-edit page, print
  sheet, text sheet.
- Controls **only on the fighter-edit page** (`/n26/fighters/<pk>/edit/`). No
  controls on the gang sheet: doing this rapidly is a bulk-update feature later,
  and the sheet's rule that its controls live in the actions slot stands.
- **XP is editable**, through the same control on the same page. It is the
  gap people feel first, and it will be bulk-editable later too.
- The card there already draws in `edit` mode — the same switch that brings out
  Equip and the Choose buttons — so the controls need no new mode.

Deferred: the dialog (arbitrary change, a note, reset-to-zero), bulk update, and
the `3/4` threshold reading that `CounterAtLeast` would make possible.

## Design

**XP keeps its statline cell, and gets a line only where it can be moved.**
The cell shows `61/79` including the target, which a counter line has no way to
show. The line earns its place by being the control, so on a screen that offers
none — the gang sheet, a print sheet, a hire preview — it would say 61 twice and
is left out. `ModelCard.counter_lines` is that rule, in one place, read by the
card template, the print columns and the text sheet alike; `counters` holds them
all. Every other counter has no cell and draws either way.

The alternative — an action slot inside `c-n26.statline` — costs more and buys
less now that the controls are not on the sheet, and that component draws
hundreds of times per sheet and is shared with print.

**Order.** XP first, then the rest in the order the card holds them. The lines
sit at the top of the card's `<dl>`, under the statline strip and adjacent to
the XP cell above them, so every tally the model keeps reads as one block.

**No act that will be refused.** `op.tally` floors at zero, so the `-` is not
drawn at zero.

**One route, signed change.** `assignments/<str:pk>/tally/`, matching the
assignment-keyed verbs already in `n26/core/views/owned.py`. A signed `change`
means the bulk-update feature later posts to the same place.

```
 -- Fighter edit page ----------------------------------------------------------
| XP             61  ( - ) ( + )                                               |
| Kill Count      3  ( - ) ( + )                                               |
| Glitch Count    0        ( + )       <- no minus at zero                      |
| Skills         Nerves of Steel, Overwatch          [Choose skill] [pencil]    |
| Gear           Spyre Hunting Rig                            [Equip]           |

 -- Gang sheet, print, text sheet ----------------------------------------------
| XP stays in its cell alone                                                    |
| Kill Count      3                                                             |
| Glitch Count    0                                                             |
```

## Build

Built, in this order.

1. **Draw.** `CounterLine` in `n26/core/render.py`; `ModelCard.counters` and the
   `counter_lines` property; filled in `model_card()` where the `Counter` branch
   dropped non-XP counters. XP goes in the list *and* keeps filling `counted_xp`.
   The loop already skips `broadcast` nodes, so the gang's own counters do not
   leak onto a member's card.
2. **Card.** A line per counter at the top of the `<dl>` in
   `cotton/n26/model_card/body.html`, controls in a new
   `cotton/n26/counter_controls.html` drawn only where the line has an href.
3. **Print and text.** `detail_groups` in `n26/core/printing.py` and the model
   block in `n26/core/render_text.py`, both reading `counter_lines`.
4. **Route.** `assignments/<str:pk>/tally/` -> `n26-tally` in
   `n26/core/views/owned.py`: `_own_assignment_or_404`, 404 for anything that is
   not a `Counter`, signed `change`, `op.tally`, analytics, message, and a `back`
   through `_safe_redirect`. `link_counters` fills the hrefs, called from
   `edit_fighter` and nowhere else.
5. **History.** `op.tally` writes the movement and where it landed into the
   note; `_movement` in `n26/core/history.py` turns it into words, and `TALLIED`
   joins `_NOTE_IS_MACHINERY` so the sentence does not print twice.
6. **Gallery.** Counters on the sample card in `n26/designsystem/sampledata.py`
   and a `Part` for the controls, so `/n26/design/c/model-card/` shows them.
7. **Tests.** `TestWhatTheCardShows` and a new `TestMovingACounterByHand` in
   `n26/tests/sandbox/test_counters.py`.
