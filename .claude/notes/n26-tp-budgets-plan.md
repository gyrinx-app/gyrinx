# n26 Trade Point budgets: the Action concept, founding budgets, computed counters

Plan written 2026-09-04 from Louis's Slack ask and Tom's decisions in the same
thread. Rules read from `rule-reference/n26` (sections 11, 17, 18, 19 and the
Venator and Outcast gang books).

## What this delivers

- A generic **Action**: a named thing a gang opens and later closes. The first
  is **Found and equip gang**, opened when a gang is created and closed by a
  button. The Visit Trading Post action becomes the second.
- **Personal founding TP budgets**: Venator Hunt Leader, Hunt Champion and
  Hunter (5, 4, 3), Outcast Leader and Champion (4, 3). They count only while
  the founding action is open.
- **Clanless**: each Leader and Champion gets +1 to that budget, as a computed
  modifier.
- **Refunds return TP to the action the purchase counted against.** No choice
  on the refund screen. Points never move from a founding budget into a
  gang visit. A sale returns no TP.
- The Leader 2 / Champion 1 visit contribution becomes content instead of a
  special case keyed on the subtype name.

## Rules facts this is built against

- `11-post-battle-and-post-cycle.md:126-130, 241-243`: Visit Trading Post is a
  Post-cycle Action, Leader or Champion only. Leader adds 2 TP, Champion 1.
  Trading Post purchases need the action; equipment list purchases do not.
  Unspent TP is lost at the end of the sub-step.
- `gangs/other-gangs/venators.md:45, 63, 81`: at hire, a Hunt Leader, Hunt
  Champion or Hunter buys from the Legacy list and the Trading Post "with a
  combined TP of 5 or less" (4, 3). So list purchases count TP for these
  fighters. The Legacy list closes after hire (`:49, 67, 85`).
- `gangs/other-gangs/outcast.md:34, 46`: Outcast Leader 4, Champion 3, from
  the affiliation's list, the Outcast list and the Trading Post combined.
- `gangs/other-gangs/outcast.md:109-110`: Clanless gives each Leader and
  Champion +1 TP at creation, and +1 TP on the first visit each Post-cycle.
- `17-territories.md:215-225`: Tech Bazaar gives +1 TP each Post-cycle and
  keeps the Trading Post open.
- Selling never returns TP. n26 already agrees: `Operation.refund` writes
  back `trade_points_delta`, `Operation.sell` does not.

## Decisions already made

1. Personal TP counts first. The two kinds of budget should not be open at
   the same time, but the model must allow it.
2. The founding action closes by hand. Closing on the first battle waits for
   battle state.
3. The Venator Legacy list closing after hire is a separate issue.
4. Clanless +1 is a **computed** modifier. Stored effects and built-ins need a
   migration when the content is wrong, so new content avoids them.
5. Overspend confirms and never refuses. Credits stay the only refused
   resource.
6. Refunds follow the purchase. Louis has been told this and why.

## Where this starts from

Built today, read from the code:

- `Gang.starting_trade_points` (`n26/core/models/gang.py:39-49`) is the only
  open/closed state. Null means no visit is open.
- `Operation._set_trade_points` (`n26/core/operations.py:601-618`) writes the
  boundary event `TRADE_POINTS_SET` every time, so a new visit supersedes the
  old one. `visit_trading_post` writes one `VISITED_TRADING_POST` per fighter
  in the same batch.
- `reconcile.trade_points_spent` (`n26/core/reconcile.py:101-146`) sums
  `trade_points_delta` over events whose **assignment** was created after the
  latest boundary. Windowing on the assignment is what makes a refund land on
  the purchase's own visit. There is no upper bound: only the latest visit is
  ever asked about.
- `LedgerEntry` (`n26/core/models/ledger.py:43-81`) has `trade_points` and
  `bought_from` but nothing that records which budget a purchase counted
  against. That link is rebuilt from timestamps at read time.
- `TRADE_POINTS_FOR_RANK = {"Leader": 2, "Champion": 1}` in
  `n26/core/trading.py:27` matches subtypes by name.
- Counters: `Counter` is content; the value is `CounterValue` on the
  assignment, written only by `op.tally`. `counter_readings`
  (`n26/core/effects.py:1109`) reads stored values only. `OpChangesCounter`
  (`n26/library/models/modifier.py:1374`) is the one counter effect and it is
  stored: it fires once when its carrier lands.
- `ChangesStat` (`modifier.py:1500`, applied at `effects.py:885-900`) is the
  computed numeric effect to copy.
- The Visit card in `n26/core/templates/n26/trade_points.html:56-116` already
  prints the label "Action", the title, a tally and a "Complete action"
  button.
- No event or field marks that founding is over. `create_gang` sets
  `starting_credits` directly and `Operation.found` writes only the founding
  assignment's `ADDED` event.
- Content in the mirror: Venator profiles exist (House, Ogryn, Squat,
  Ratling, Beastman Hunt Leader / Hunt Champion / Hunter), Outcast Leader and
  Champion exist, the Clanless affiliation exists, and Leader and Champion
  are subtypes in the N26 pack. Three counters exist: XP, Kill Count, Glitch
  Count.

## Design

### 1. The Action model

A small table, `n26/core/models/action.py`:

- `gang` FK, `kind` (choices: `FOUNDING`, `TRADING_POST_VISIT`), `opened`
  and `closed` FKs to the `LedgerEvent` that opened and closed it (`closed`
  null while open), `trade_points` (what a visit added; null for founding).
- One open action per kind per gang, as a partial unique constraint on
  `(gang, kind)` where `closed` is null.
- `Operation.open_action(kind, ...)` writes an `ACTION_OPENED` event and the
  row. `Operation.close_action(action)` writes `ACTION_CLOSED` and sets
  `closed`. Both events are assignment-less, like `BUDGET_SET`, so
  `reconcile.check_entry` never folds them. Both join `_NOTE_IS_MACHINERY`.
- Opening a kind that is already open is refused, as `gang_trade_points`
  does today.

Lifted from the visit, made generic:

- The always-write boundary event and the one-at-a-time refusal.
- The Action card (label, title, tally, "Complete action") becomes a
  component fed by an `ActionCard` render structure.
- `Receipt.facts` (Available, Spent, Remaining) and the contributors-by-batch
  lookup in `receipt_for`.
- `trade_points_href` becomes `action_href(gang, kind, user)`.
- The history sentence convention (kind plus a machine-readable note).

### 2. Purchases record their action

- `LedgerEntry.action` FK, nullable. `Operation.buy` sets it to the action
  the purchase counted against, decided by the equip view (section 4).
- Spend for an action is the sum of `trade_points_delta` over events whose
  assignment's entry has `action = A`. A refund's event sits on the same
  assignment, so it lands on the same action. This replaces the timestamp
  window and gives closed actions an exact figure.
- Per-fighter spend within the founding action adds
  `assignment__miniature_root = fighter`.
- Legacy purchases have no action. `trade_points_spent` keeps the timestamp
  window as a fallback for the visit until the data migration in section 5
  has run, then the fallback is deleted.

### 3. Counters: computed contributions and two new counters

- New computed effect `ContributesToCounter(counter, amount)` on `Modifier`,
  `is_stored = False`, accepted for MODEL and GANG targets. `compute` collects
  contributions per counter, as it collects `StatChange`s.
- `counter_readings` returns `stored + sum(contributions)`. A counter with
  contributions but no assignment appears as a computed reading, as granted
  collections and rules do today. `CounterAtLeast` reads the combined value.
- `Counter.drawn` boolean, default True. A counter with `drawn = False` is
  read by flows and never drawn on a card or the fighter-edit page.
- New content, both `drawn = False`:
  - **Trading Post visit contribution.** The Leader subtype carries a
    modifier contributing 2, the Champion subtype 1. `trading.visitors`
    reads each roster member's computed reading instead of
    `TRADE_POINTS_FOR_RANK`. A fighter holding both ranks uses the higher
    contribution, as today.
  - **Founding TP budget.** Each Venator and Outcast Leader and Champion
    profile carries a modifier contributing its figure. The Clanless
    affiliation carries `TargetsMiniature(Leader, Champion)` plus a
    contribution of 1. The gang-hosted affiliation reaches each member
    through the broadcast, the same route the Clan House list access takes.
- Nothing here is a built-in or a stored effect. Fixing a wrong figure is an
  authoring edit.

### 4. The founding action on the equip screens

- `Operation.found` opens a `FOUNDING` action. A gang page card shows it with
  a "Complete action" button. A closed founding action can be opened again
  from the same place, which is how an owner who refunded founding purchases
  spends the budget again.
- On a fighter's equip screen, while the gang's founding action is open and
  the fighter's Founding TP budget reading is above 0:
  - every line counts its TP, list lines included. This is the book's
    "combined TP". A third `Terms`, `FOUNDING = Terms(charges_trade_points=True,
    shows_exclusive=True)`, is passed to `browse`. Exclusive lines have no TP
    and count 0.
  - purchases record the founding action.
  - the screen shows the fighter's budget as a tally: granted, spent,
    remaining.
  - going past the budget shows the overspend confirmation, with the figures.
- Otherwise the screen behaves as today: list lines count nothing, Trading
  Post lines count against the open visit if there is one, and a purchase
  with no open action shows a confirmation first.
- A fighter with no budget on a gang with an open founding action sees no
  change.
- The `post_is_shut` note is not shown while a founding budget is in play.

### 5. The visit moves onto Action

- `visit_trading_post` opens a `TRADING_POST_VISIT` action with
  `trade_points` set to the minted or typed figure. `leave_trading_post`
  closes it. `VISITED_TRADING_POST` events stay as they are.
- `Gang.visiting_trading_post` and `trade_points_left` read the open action.
  `Gang.starting_trade_points` is removed after the data migration.
- Data migration: one `Action` row per gang with a non-null
  `starting_trade_points`, `opened` pointing at its latest
  `TRADE_POINTS_SET` event. Production has 13 such gangs. Purchases made
  under those visits get `LedgerEntry.action` set from the same timestamp
  window the code uses today.
- Column drop is a second deploy (see the destructive-migration gotcha in
  memory).

## Slices

Each slice is one PR. Sizes are guesses.

1. **Action model and founding action** (medium). Model, two event kinds,
   `open_action` / `close_action`, `Operation.found` opens one, the gang page
   card with "Complete action" and "Start again", history sentences,
   analytics. No budgets yet. Tests: open on found, refuse a second open,
   close, reopen, history reads right, query counts on the gang page hold.
2. **Visit onto Action** (medium). Section 5 without the column drop. Tests:
   the four claims in `trading.py` still hold, `receipt_for` reads the
   action, the migration turns an open visit into an open action and stamps
   its purchases.
3. **Computed counter contributions** (medium). `ContributesToCounter`,
   reading arithmetic, `Counter.drawn`, authoring support in `specs.py` and
   `authoring.py`. Tests: contribution with no stored value, contribution
   plus stored value, `CounterAtLeast` on the combined value, a carrier
   removed takes its contribution away, a `drawn = False` counter is absent
   from cards and the edit page.
4. **Visit contribution as content** (small). The two subtype modifiers,
   `visitors` reads the counter, `TRADE_POINTS_FOR_RANK` deleted. Tests:
   promoted fighter counts, removed rank does not, both ranks use the
   higher.
5. **Founding budgets** (large). `LedgerEntry.action`, spend by action,
   `FOUNDING` terms, the equip screen tally and confirmation, the
   per-fighter arithmetic. Tests: list line counts TP for a budgeted
   fighter and not for another, refund returns to the founding action,
   refund after close is not counted, reopen starts from zero, sale
   returns nothing, overspend confirms, query counts on equip hold.
6. **Content** (authoring, no code). Modifiers on the Venator and Outcast
   profiles, the Clanless affiliation, the two subtypes. Verify on the
   content mirror before production.
7. **Drop `Gang.starting_trade_points` and the timestamp fallback** (small,
   second deploy).

Slices 3 and 4 can run in parallel with 1 and 2. Slice 5 needs 1 and 3.

## Verification before shipping slice 5

- Fork the content mirror, hire a Venator Hunt Leader, open the founding
  action, buy a list item and a Trading Post item, refund one, close, reopen,
  and compare the tally and the ledger by hand at each step.
- Run the data migration from slice 2 on the fork and compare the 13 open
  visits' remaining figures before and after from outside the code.
- Screenshots of the equip screen in all three states: no action, founding
  budget in play, visit open. Gallery page for the Action card.

## Open questions

- Should the founding action open for gangs that already exist, or only for
  new ones? Recommendation: only new ones. Existing owners open it by hand.
- Where does the founding card live: the gang page, or the edit tabs beside
  Trade Points? Recommendation: the gang page, because it comes and goes.
- Does a fighter hired after founding closed get a budget? The book says
  "when added to a Gang Roster", so yes in principle. Recommendation: the
  budget counts whenever the founding action is open, and the owner reopens
  it to equip a new hire. Revisit if that turns out wrong.
- Does the Trading Post visit get its own per-visit modifier for Tech Bazaar
  and the Clanless first-visit +1 now, or stay on the typed figure?
  Recommendation: typed figure until campaign phases exist.

## Out of scope

- The Venator Legacy list closing after hire. Separate issue.
- Closing the founding action on the first battle.
- Tech Bazaar and the Clanless first-visit +1 as modifiers.
- The Nomad Trading Post's scavenge roll.
- Exclusive gating on the Unrestricted tab and in redistribution.
