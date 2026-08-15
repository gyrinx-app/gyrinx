# Campaigns: n23 as built vs n26 as written

Companion to `n23-campaign-spec.md` (code-derived) and `n26-campaign-spec.md`
(rules-derived). This document compares them and sets out the decisions that
need your input.

---

## 1. The headline

The two systems are built on opposite premises.

**n23's campaign system says nothing about the game.** It is a bookkeeping
toolkit: named resources, named assets with a holder, named gang attributes, a
free-text phase label, and a dice-rolling audit log. An arbitrator knows the
rules; the app records what they decided. The only n23 vocabulary anywhere in it
is a seeded resource type called `"Reputation"` — a *name*, with no behaviour
attached.

**n26's campaign rules are prescriptive and, unusually, automatable.** They
specify a fixed time structure (7 cycles in 3 phases), a challenge protocol with
a defined ordering rule, Territories as battle stakes with five *typed* kinds of
benefit, Reputation as a scored quantity with defined triggers and a floor, a
per-model post-cycle action menu with its own sub-currency, and end-of-campaign
Triumphs computed from tracked running totals.

So the gap is not "n23 has the wrong rules". It is that **n23 deliberately
declines to have rules, and n26 supplies enough of them to run.** Almost
everything n26 specifies is something a player would now expect the app to do
for them, and n23's design point is that the app doesn't do things.

That is the decision underneath everything else in this document.

---

## 2. Shape comparison

| | n23 (as built) | n26 (as written) |
|---|---|---|
| **Time** | 3 states; `phase` is a free-text label nothing reads | Campaign → 3 phases → 7 cycles; cycle end is a synchronisation point for all gangs |
| **Joining** | Gang is *cloned* into campaign mode; original untouched | Gang is founded at 1,000cr and simply plays |
| **Starting money** | `budget` (default 1500) topped up to: `max(0, budget − rating)` | Flat 1,000cr founding budget; unspent goes to Stash |
| **Territories** | A user-named asset type; `holder` FK; properties are free-form JSON | 19 defined Territories, D66 table, pool sized 3×players, tri-state (unclaimed/reserved/held), 5 typed Boon kinds, battlefield effects |
| **Reputation** | A seeded resource type named "Reputation", default 1 | First-class score: floor 1, gains before losses, pays 10× as income each cycle, decides a Triumph |
| **Scheduling** | None. `mission` is free text | Challenge protocol: one per cycle, ascending Gang Rating order, accept/decline with defined penalties, stake nomination |
| **Scenarios** | Free-text mission; Attacker/Defender roles are content-authored | Four independent D6 tables composed into a tuple (deployment, objective, side job, crew) |
| **Battle result** | Records winners / draw / unrecorded. Ending a battle touches no gang | Drives territory transfer, phase-scaled credits, Reputation delta, XP awards |
| **Post-battle** | One bulk manual editor, *per gang* and only loosely linked to a battle; nothing knows whether it was used | 5 ordered steps, both players present, per battle |
| **Post-cycle** | Does not exist | 3 steps; per-model action menu; income collection; roster update with 4 sub-steps |
| **Advancement** | XP is *spent* to buy a chosen advancement; config hardcoded in a form | XP accumulates into 21 rank bands; crossing one forces a 2D6 roll |
| **Ending** | `end_campaign()` flips a status field | Wrap-up: report, award 5 Triumphs, dissolution, optional Enduring gang |
| **Running totals** | None | Cumulative enemy OOA and battles fought, needed for Triumphs |

---

## 3. What carries over unchanged

More than you might expect. The parts of n23 that are genuinely edition-agnostic
and worth keeping:

- **The credits ledger and balance-sheet reconciliation.** Hard-won (the
  cost-pinning and cost-cache programmes) and entirely rules-neutral.
- **The action log.** `CampaignAction` with description/outcome/dice, FK'd to
  campaign, gang and battle, is exactly the right shape for a campaign journal
  regardless of edition.
- **The permission and arbitrator model**, including shared admins.
- **Invitations, pack gating, campaign templates and copying, gang sorting.**
- **Wealth and rating as distinct derived totals** — n26 needs both, and uses
  them for different things (Rating for challenge order and the underdog bonus;
  Wealth for the Creditor Triumph and as the universal tiebreak).
- **The generic primitives themselves** as an *escape hatch*. Even a fully
  n26-aware system will want "arbitrator can track an arbitrary thing", because
  the n26 rules explicitly invite arbitrators to customise tables and add
  phases.
- **The clone-on-join model**, probably — though see §5.2.
- **Captured fighters**, which map onto n26 better than anything else in the
  system. n23 already offers exactly three terminal outcomes — sold to guilders,
  returned for a ransom, released — against n26's Escape table of executed /
  ransomed / daring escape. The shapes line up; the naming and the trigger
  differ (n26 reaches it from a specific Lasting Injury result, and defers the
  ransom payment to the next Update Roster step).
- **Crew spending at battle start**, which is the one existing example of a
  battle event moving credits correctly through the ledger.

---

## 4. What has no equivalent and would be new

In rough order of how much is missing:

1. **Cycles.** There is no time structure at all. Everything periodic in n26 —
   income, post-cycle actions, the five-fighter Work Territory cap, Trade Point
   expiry, roster mutability windows, challenge allowances — hangs off a cycle
   boundary that doesn't exist.
2. **The post-cycle sequence.** An entirely new flow, and the biggest single UI
   surface: a per-model action menu with eligibility rules, costs, caps and
   deferred resolution, followed by income collection and a four-sub-step roster
   update.
3. **Typed Territory Boons.** n23 assets carry free-form JSON that is display
   metadata only. n26 Boons are five distinct kinds with real semantics —
   including an either/or election, eligibility predicates, and different
   persistence-after-loss behaviour (recruits and equipment persist; income,
   reputation and specials do not).
4. **The challenge protocol.** Issue/accept/decline, per-cycle allowances,
   ordering by ascending Gang Rating, stake nomination and reservation.
5. **Territory pool state.** Unclaimed / reserved / controlled, with a
   campaign-level pool sized from player count.
6. **Battle-result propagation.** n26 defines exactly what a win pays; n23 has a
   human type it in. Worth being precise about how loose the current coupling
   is: `handle_battle_end` writes the result and freezes crew ratings but
   **touches no gang** — no XP, no credits, no injuries. The post-battle editor
   is reached from the *gang*, takes the battle as an optional FK used only to
   tag the resulting actions, and each gang records independently. There is no
   cross-gang consistency check, so a capture is entered by the losing gang
   naming the captor. And nothing knows whether it was ever used: the battle
   timeline's final step is hardcoded `"done": False`
   (`handlers/battle.py:427`), so the UI always says "you are here".

   The one place a battle *does* transact is the start:
   `charge_crew_spending` (`handlers/battle.py:241`) charges each crew's
   spending under `SELECT FOR UPDATE`, pairs every delta with a `ListAction`
   because the balance sheet asserts the credits chain, and floors at zero
   rather than going negative. So the machinery for "a battle event moves
   money correctly" exists and is careful — it just isn't wired to results.
7. **Rank-band advancement.** A different mechanism from n23's XP-spend, not a
   different table — and currently living in a form.
8. **Triumphs and running totals.** Cumulative OOA and battles-fought counters,
   plus end-of-campaign scoring with multi-winner ties.
9. **Trade Points.** A per-cycle sub-currency that is generated, spent and
   expires within one sub-step.
10. **Scenario generation** from four composed tables.

---

## 5. Issues needing your input

These are the decisions I can't make for you. Ordered by how much else depends
on them.

### 5.1 How much does the app *do*? — the central question

Three coherent positions:

- **(a) Stay a toolkit.** Ship n26 campaigns as *content*: a template campaign
  with a Territory asset type, 19 pre-authored assets, a Reputation resource,
  phase names. The app still records rather than computes. Cheapest by far,
  consistent with the current design, and preserves arbitrator freedom — which
  the n26 rules explicitly ask for. But it leaves every player doing arithmetic
  the rules fully specify, and Boons stay strings a human reads.
- **(b) Full rules engine.** Model cycles, challenges, typed Boons, post-cycle
  actions, Triumphs. The app runs the campaign. Much more work, and it commits
  you to the rules being right — including the places where they're broken
  (§5.7).
- **(c) Toolkit plus computed helpers.** Keep the generic core; add cycles as
  the one new first-class concept; make Boons typed enough to *propose* income
  at cycle end ("collect 20cr from Tech Bazaar?") without enforcing it. The app
  suggests, the human confirms.

My recommendation is **(c)**, and I'd defend it on two grounds. First, the n26
rules hand the arbitrator explicit licence to vary almost everything — campaign
length, phase count, all four scenario tables, the Territory table — so a rigid
engine would fight the rules it implements. Second, the drudgery players
actually feel is the arithmetic (income, XP, rank-ups, TP), not the decisions;
computing-and-confirming removes the drudgery without removing agency.

But this is a product call about what Gyrinx is for, and you may simply want the
app to run an n26 campaign properly.

### 5.2 Does n26 get its own campaign system, or is campaign shared?

Right now campaigns live entirely in `n23/`. `n26/` has none. Given the
dual-edition programme is "parallel with reuse", campaigns need a call:

- **Own implementation in `n26/`** — clean, no compromise on either side, but
  duplicates the ledger/log/permissions/invitations machinery, which is the
  genuinely valuable and edition-neutral part.
- **Shared platform-level campaign** with edition-specific rules plugged in —
  right in principle, but the n23 campaign package is ~5,000 lines of views with
  n23 assumptions threaded through, and extracting it is its own project.
- **Fork and diverge** — copy into `n26/`, accept the duplication, let them
  drift.

This interacts strongly with 5.1: under (a) sharing is easy, under (b) the two
systems have little in common beyond bookkeeping.

One finding should weigh on this. **The n23 campaign package has no policy
layer.** `campaign.archived`, `is_pre_campaign`, `is_post_campaign` and the four
different permission predicates are re-implemented inline in roughly forty view
call sites with hand-written messages, and they have already drifted — asset-type
edit and asset edit lack the archived guard their new/remove siblings have;
attribute assignment lacks the pre-campaign guard that resource modification
has; read pages are inconsistently gated on membership; failure modes are
variously 404, bare `Http404`, and message-plus-redirect. Logging has drifted the
same way, split across `CampaignAction`, `log_event` and `track` written by hand
at three different layers, with the result that **sub-asset changes and attribute
assignments never reach the campaign log at all**.

That matters here because extracting a shared core means first re-deriving the
intended permission matrix from those forty sites — that is the real cost of the
"shared platform" option, not the model layer. `campaign_add_lists` alone is a
single 300-line view carrying pack validation, an inline confirmation flow,
invitation reconciliation, search, three filters and pagination.

**I'd want your steer here before anything else**, because it determines whether
the next step is "extract a platform campaign core" or "build n26 campaigns
greenfield".

### 5.3 Reputation — keep it a resource?

You flagged this as the thing that would trip me up, and it turns out to be the
sharpest modelling question in the comparison.

In n23 it's a resource type named "Reputation" with no behaviour. In n26 it is
load-bearing: it pays `10 × Reputation` credits every cycle, it has a floor of
1, gains apply before losses, and it decides the Powerbroker Triumph.

The subtlety: **n26 Reputation is not a plain counter.** It decomposes into an
earned base plus conditional modifiers from currently-held Territories
(Generatorium and Gambling Den each grant +1 while held). If you implement it as
a single integer and increment on territory gain, it will drift when the
territory is lost, and it will interact wrongly with the floor. A gang at 1 that
gains 2 and loses 1 must end at 2 — applying the loss first and clamping gives 3.

Options: keep it a resource and accept manual bookkeeping; keep it a resource
but make resources support derived modifiers; or promote it to a first-class
gang field. The middle option is interesting because it generalises — "a
resource with contributions from held assets" is exactly what Territory income
is too.

### 5.4 Do cycles become first-class?

I think this is the one piece of new structure that's hard to avoid under any of
the 5.1 options, because so much of n26 is defined per-cycle. Even under (a),
without a cycle concept there's nowhere to hang "this happened in cycle 3", and
Triumphs can't be computed.

Question for you: is a cycle a **campaign-wide object** (arbitrator advances it,
everyone moves together — matches the rules) or a **per-gang counter**? The
rules are clear it's campaign-wide, but campaign-wide advancement means one
player can block everyone, which is a real product risk for asynchronous play.

### 5.5 How much of the post-cycle sequence do we build?

This is the largest new surface. It splits into pieces of very different value:

- **Collect Income** — pure arithmetic, high drudgery, easy win. Build it.
- **Post-cycle Actions** — a per-model menu with eligibility, costs, caps and
  deferred resolution. Genuinely useful, genuinely fiddly.
- **Advance Models** — needs the new rank-band mechanism regardless (§5.6).
- **Trading Post + Trade Points** — TP is a whole sub-currency with a one-step
  lifetime. Do we model it, or just show the player what they've earned?
- **Redistribute Equipment / Clean House** — mostly existing stash and state
  machinery.

Worth deciding which of these ship first rather than treating it as one lump.

### 5.6 Advancement has to be rebuilt, not re-tabled

n23 spends XP to buy a chosen advancement, with the economy hardcoded in
`ADVANCEMENT_CONFIGS` inside a *form*. n26 never spends XP: it accumulates into
21 rank bands, and crossing a band forces one 2D6 roll where you may take any
result at or below what you rolled.

These aren't the same mechanism with different numbers. Two consequences:

- n26 advancement is new code, not new data.
- Whatever we build should live in content/data, not in a form — and it's worth
  deciding whether to fix n23's placement at the same time or leave it.

### 5.7 The rules have real holes — what do we do at them?

The n26 reference leaves several things genuinely unresolved. Each needs a
product answer if the app implements the mechanic:

- **A gang reduced to only its Settlement cannot be challenged** (the Settlement
  can never be staked) and, in the Takeover phase, has no route back (only
  controlled Territories may be fought over). That gang is frozen out of the
  campaign. This looks like a real rules bug, not a reading error.
- **The Chop Shop is circular**: a Critically Damaged vehicle can't take
  post-cycle actions until repaired, but Visit Chop Shop is itself a post-cycle
  action taken by that vehicle. As written it can't be satisfied.
- **Ransom equipment destination** is ambiguous — "the owning gang's Stash" when
  the model is in enemy hands could mean either gang, and it's worth real
  credits.
- **Reputation has no cap**, while paying 10× per cycle and +2 per Takeover win.
  That compounds without bound.
- **Whether battles happen during Downtime** is never stated.
- **Whether starting Territories come out of the contested pool** is never
  stated.
- **Two-player campaigns** aren't covered (the pool table starts at 3).

Under option (a) these stay the arbitrator's problem. Under (b) we have to pick
answers and effectively publish house rules.

### 5.8 Smaller things worth a decision

- **Dice**: `CampaignAction` rolls D6 only (`random.randint(1,6)`), and its form
  is labelled "Number of D6 Dice". The standalone roller (`views/dice.py`)
  already does d6, d3 and named firepower/injury dice, and is URL-seeded so a
  roll is reproducible and shareable. n26 additionally needs 2D6 and D66.
  Extending is cheap; the decision is whether rolls are app-generated or
  player-entered.
- **n23 nouns are spread through the code, not just the campaign models.**
  Credits are a first-class column spelled `¢` in every flash and log string;
  gang metrics are a fixed vocabulary (`rating | credits | stash | wealth`) with
  fixed one-letter headers; and *Guilders* appears as a URL name, view name,
  handler name, template name and a `sold_to_guilders` boolean field. None of
  this is wrong for n23, but it's the vocabulary a shared core would have to
  neutralise — and it's a bigger surface than the single "Reputation" constant
  in the campaign package suggests.
- **Roster mutability**: n26 locks the roster during a cycle and opens it only
  in the post-cycle sequence. n23 campaign-mode gangs are always editable.
  Enforcing this would be a behaviour change players would feel.
- **The clone-on-join model**: n26 has no notion of a gang existing outside a
  campaign, and adds *Enduring* gangs that carry fighters into a **next**
  campaign. Worth checking the clone model serves that rather than fighting it.
- **`end_campaign()` currently does nothing.** If Triumphs land, it becomes a
  real transition with scoring — and the existing reopen path needs to make
  sense alongside it.

---

## 6. Suggested next step

Answer 5.1 and 5.2 — the automation level and where the code lives — and the
rest mostly follows. If it helps, I can draft the data model for whichever
option you pick, or spike the cycle concept (§5.4) since it's needed under all
of them.
