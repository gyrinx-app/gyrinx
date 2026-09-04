# n26 Trade Point budgets: the Action concept, founding budgets, computed counters

Plan written 2026-09-04 from Louis's Slack ask and Tom's decisions in the same
thread. Rules read from `rule-reference/n26` (sections 11, 17, 18, 19 and the
Venator and Outcast gang books).

## Progress (2026-09-04 evening)

Merged to main, in order: #2419 (slice 3), #2423 (slice 1), #2436 (Actions
square staff-only, stash Trading Post line restored), #2428 (slice 4), #2435
(slice 7, backfill code only), #2438 (slice 2). In flight: slice 5 with the
slice 6 content as a Foundations seed `founding-budgets` (branch
`n26-founding-tp-budgets`), and slice 8 as two commits on
`n26-drop-starting-trade-points-1` / `-2` (the drop ships after the first
deploys).

Production steps that are Tom's, not code: press Create on the Foundations
page for the `visit-contribution` seed (now) and `founding-budgets` (after
slice 5 deploys); run the `n26_open_founding_actions` backfill from the
maintenance admin when the budgets are live and verify from outside (action
counts and rating/credits pins); copy iteration on the square, deferred.

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
  spends the budget again, and how a fighter hired later gets equipped from
  their budget.
- Existing gangs get an open founding action from a backfill (slice 7), run
  from the maintenance admin once the feature is broadly built. Until then
  only new gangs have one. Their past purchases carry no action, so a budget
  on an existing gang starts whole. Owners close the action when they are
  done.
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
   analytics. New gangs only; existing gangs wait for slice 7. No budgets
   yet. Tests: open on found, refuse a second open, close, reopen, history
   reads right, query counts on the gang page hold.
2. **Visit onto Action** (medium). Section 5 without the column drop, plus
   `LedgerEntry.action` and spend by action from section 2, since the
   migration stamps purchases with it. Tests: the four claims in
   `trading.py` still hold, `receipt_for` reads the action, spend by action
   agrees with the timestamp window for a stamped visit, the migration
   turns an open visit into an open action and stamps its purchases.
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
5. **Founding budgets** (large). Purchases record the founding action,
   per-fighter spend by action, `FOUNDING` terms, the equip screen tally and confirmation, the
   per-fighter arithmetic. Tests: list line counts TP for a budgeted
   fighter and not for another, refund returns to the founding action,
   refund after close is not counted, reopen starts from zero, sale
   returns nothing, overspend confirms, query counts on equip hold.
6. **Content** (authoring, no code). Modifiers on the Venator and Outcast
   profiles, the Clanless affiliation, the two subtypes. Verify on the
   content mirror before production.
7. **Backfill: open the founding action for existing gangs** (small). A
   `Backfill.Operation` choice, triggered from the maintenance admin: GET
   previews the count, POST enqueues a task. Follows `convert_specialisation`
   and `run_batched` in `n26/maintenance.py`: advisory lock, attempt count,
   chunked, every outcome written onto the record. Opens one founding
   action per unarchived gang that has never had one, through
   `Operation.open_action` so the ledger event is written. Skips gangs with
   any founding action, open or closed, so a rerun changes nothing. Tom
   runs it once the feature is broadly built. Tests: preview count, one
   opened per eligible gang, rerun is a no-op, archived gangs skipped.
   Smoke-test on a fork of the content mirror at production volume (1,979
   live gangs on 2026-09-04) and compare open actions before and after
   from outside the task.
8. **Drop `Gang.starting_trade_points` and the timestamp fallback** (small,
   second deploy).
9. **Actions square follow-ups** (small). Slice 1 already draws the open
   action as one grid square on the gang sheet, before the stash, with the
   Trading Post visit indicator moved into it and an actions menu (Tom's
   direction, 2026-09-04). This slice adds what that square grows into: a
   snapshot of the latest gang ledger history, and any per-action entries
   the later slices need in the menu. Tests: square with none, one and two
   open actions; query count holds.

Slices 3 and 4 can run in parallel with 1 and 2. Slice 5 needs 1 and 3.
Slice 7 can be built any time after 1 but is run only when Tom says so.
Slice 9 comes last.

## Parallel work and sub-agents

Every sub-agent is an Opus agent (`model: "opus"` on the Agent call), one
slice per agent, each in its own worktree with its own `DB_NAME`. Launch
implementation agents from the root checkout with `isolation: "worktree"`.
Launched from inside a worktree, background agents share that worktree's
index and collide (see the orchestration memory). The orchestrating session
keeps the branch and PR bookkeeping, merges in order and rebases what is
left.

Dependencies:

- 1 and 3 have no dependencies.
- 2 needs 1. 4 needs 3. 7 needs 1. 9 needs 1 and reads better after 2.
- 5 needs 2 and 3.
- 6 needs 3 and 4 for the subtype modifiers, and 5 before the founding
  figures mean anything on screen. Authoring can start on the content
  mirror after 3.
- 8 needs 2 deployed.

Waves:

| Wave | In parallel | Agents |
|---|---|---|
| A | 1 Action model and founding action; 3 computed counter contributions | 2 implementation agents |
| B | 2 visit onto Action; 4 visit contribution as content; 7 backfill | 3 implementation agents |
| C | 5 founding budgets; 9 gang header; 6 content on the mirror | 2 implementation agents, 1 content agent |
| D | 8 column drop, after 2 is deployed | 1 implementation agent |

Per PR, after the implementation agent finishes: one Opus `code-reviewer`
agent, one Opus `copywriter` agent where user-facing strings changed, then
the orchestrator's browser pass and gallery page check. **Then Tom checks
before merge** (his ruling, 2026-09-04): the orchestrator sends the PR
number, a one-line summary, a local URL on the agent's dev server and a
short checklist, and waits for his go. Nothing merges on the orchestrator's
own judgement. UI gets an earlier ping with screenshots as soon as it takes
shape. Slice 7 also gets an
Opus verification agent that forks the content mirror, runs the backfill at
production volume and compares open actions before and after from outside
the task.

Files two waves touch at once, so expect rebases:

- `n26/core/models/ledger.py` `LedgerEvent.Kind` and `LedgerEntry`: slices
  1, 2.
- `n26/core/operations.py`: slices 1, 2, 5.
- `n26/core/effects.py`: slices 3, 5.
- `n26/core/trading.py`: slices 2, 4.
- `n26/core/migrations/`: slices 1, 2, 3, 5, 8 each add one. Two agents in
  one wave both adding a migration means the second rebases and renumbers.
  CI stays green on a PR that is behind main, so the orchestrator checks
  for a migration conflict before every merge.

## Verification before shipping slice 5

- Fork the content mirror, hire a Venator Hunt Leader, open the founding
  action, buy a list item and a Trading Post item, refund one, close, reopen,
  and compare the tally and the ledger by hand at each step.
- Run the data migration from slice 2 on the fork and compare the 13 open
  visits' remaining figures before and after from outside the code.
- Screenshots of the equip screen in all three states: no action, founding
  budget in play, visit open. Gallery page for the Action card.

## Decisions taken on the open questions (Tom, 2026-09-04)

- Existing gangs get the founding action opened for them by a backfill, run
  from the maintenance admin when the feature is broadly built. Not a
  migration.
- The founding card lives on the gang page. A gang header showing the open
  action is slice 9.
- A fighter hired after founding closed gets their budget when the owner
  reopens the action.

## Out of scope

- The Venator Legacy list closing after hire. Separate issue.
- Closing the founding action on the first battle.
- Tech Bazaar and the Clanless first-visit +1 as modifiers.
- The Nomad Trading Post's scavenge roll.
- Exclusive gating on the Unrestricted tab and in redistribution.
