# n26 Campaign System — Specification

Derived solely from the n26 rule reference at `rule-reference/n26/`. All mechanics are
paraphrased; no rules text is reproduced. Where the reference is silent or
self-contradictory this is called out in §12 rather than resolved.

Primary sources: `16-campaigns.md`, `17-territories.md`, `11-post-battle-and-post-cycle.md`,
`15-battlefield-setup-and-scenarios.md`, `12-gang-creation-and-roster.md`, `13-gang-tactics.md`,
plus `03`, `08`, `09`, `10`, `14`, `18`, `19` and the Pre-battle Sequence, which only exists in
the consolidated `n26-rulebook-reference.md` (around line 819) and has no split chapter file.

---

## 1. Campaign shape

A campaign is a fixed-duration contest between gangs for control of **Territories**. Battles
are the mechanism of transfer: each battle is fought with a nominated Territory as its stake.

### Time structure

Three nested units:

- **Campaign** — the whole thing. Fixed real-time span. The Arbitrator sets start date, end
  date, and the position of the Downtime cycle, and tells the players before play begins.
- **Phase** — three of them by default, each a fixed span of real time.
- **Cycle** — the atomic unit. Default is one real-world week, but the reference explicitly
  permits any period the group prefers. Cycle boundaries are declared by the Arbitrator, not
  computed from battle counts.

Default layout, seven cycles total:

| # | Phase | Cycles |
|---|-------|--------|
| 1 | Occupation | 3 |
| 2 | Downtime | 1 |
| 3 | Takeover | 3 |

The Arbitrator may lengthen or shorten any phase, or add phases, at setup time. So phase
count, phase order, and cycles-per-phase must all be configurable data, not constants.

At the end of every cycle, **all** gangs run the Post-cycle Sequence (§7). This is a
campaign-wide synchronisation point, not something a gang does independently after its own
battles.

### Phase semantics

The phase a battle falls in changes three things: what may be staked, the size of the payout,
and the Reputation swing.

**Occupation phase**

- Battle payouts: winner 2D3×10 credits to Stash and +1 Reputation; loser D3×10; a draw pays
  both sides D3×10; completing a Side Job pays D3×10.
- Only *unclaimed* Territories may be staked, unless the unclaimed pool is empty, in which
  case a Territory held by the challenged gang may be staked instead.

**Downtime phase** (single cycle)

- Every gang receives 250 credits. These are earmarked: spendable only during that cycle's
  Post-cycle Sequence, only on recruits and equipment from the gang's own Equipment List,
  and they cannot be banked into the Stash. The gang may add Stash credits on top.
- The reference does not say whether battles or challenges occur during Downtime; the framing
  ("after their last battle of the Occupation phase") implies they do not.

**Takeover phase**

- Battle payouts: winner 2D6×10 credits and +2 Reputation; loser D6×10; a draw pays both
  D6×10; Side Job pays D6×10.
- Losing control of a Territory costs the gang 1 Reputation.
- Only *controlled* Territories may be staked, i.e. every battle is now a raid on someone's
  holdings.

### Setup

The Arbitrator, ideally in one session with all players present:

1. Fix start date, end date, and Downtime placement; publish to players.
2. Build the Territory table (the book supplies one; supplements are expected to supply more
   options, and the Arbitrator may substitute freely). A physical card deck is an accepted
   alternative to a roll table.
3. Build the Scenario tables (same substitution licence).
4. Generate the contested Territory pool: **3 Territories per player**, tabulated for 3–8
   players (3→9, 4→12, 5→15, 6→18, 7→21, 8→24). Roll D66 on the Territory table; duplicates
   are permitted, so the pool is a multiset.
5. Every gang is founded and assigned its starting Territories: a Settlement (permanent,
   never stakeable) plus one rolled from the Territory table — or from a gang-specific
   Territory table if the gang has one, a choice the player must declare before rolling.

### Ending

There is no single winner. After the last cycle the campaign is over and all players run the
**Campaign Wrap-up**, in three steps:

1. **Report Results** — each player reports their standing against each Triumph criterion.
2. **Award Triumphs** — the Arbitrator awards five Triumphs (§11). Ties break on highest
   Wealth; if still tied, every tied gang receives the Triumph.
3. **Gang Dissolution** — gangs break up. A player may optionally mark a gang **Enduring** and
   nominate one earned Triumph to carry a benefit into their next campaign.

---

## 2. Participation

### The Arbitrator

One of the players takes this role in addition to running a gang. Responsibilities named by
the reference:

- Maintain the roster of participating gangs.
- Author the Territory table and the Scenario tables.
- Track Territory control and broadcast campaign progress to players.
- Declare when each cycle, each phase, and the campaign as a whole begin and end.
- Adjudicate random events and campaign-level elements.
- Adjust the founding budget up or down from the default 1,000 credits if desired.
- Receive per-battle result reports and maintain the running campaign statistics.

The Arbitrator is a human referee holding authoritative state (territory control, cycle
boundaries, cumulative OoA counts). Nothing in the rules is self-serving from the players'
rosters alone.

### Gangs

Any published gang list is admissible. No cap on player count is stated, but the Territory
pool table is only defined for 3–8 players.

### Challenges

Battles are scheduled by a challenge protocol, not by a fixture list:

- Each player may issue **one** challenge per cycle, naming an opposing gang and a Territory
  as the stake.
- **Order of issuing**: first cycle, random order; subsequent cycles, ascending Gang Rating
  (weakest gang challenges first), with roll-offs to break ties. This is the system's
  catch-up mechanic — the underdog picks its fight first.
- **Legal stake** depends on the phase (see §1). The Settlement can never be staked.
- Once nominated during the Occupation phase, an unclaimed Territory is withdrawn from the
  pool by the Arbitrator until the battle resolves — so the pool needs a "reserved" state, not
  just claimed/unclaimed.
- The challenged gang may **accept** (battle is fought) or **decline** (the challenger takes
  the Territory without a fight).
- Declining is free of penalty if the gang has already issued its own challenge this cycle, or
  if it is receiving its second-or-later challenge this cycle. So each gang owes at most one
  compulsory defence per cycle.
- A player who has cleared all outstanding battles — their own challenge and every challenge
  they accepted — may issue a further challenge if cycle time remains. Challenge count per
  cycle is therefore unbounded in principle.

The challenger is always the attacker for scenario purposes.

---

## 3. Between-battle economy

A single currency, **credits**, plus a **Stash** that holds both loose credits and surplus
equipment. There is no upkeep, no maintenance cost, and no per-cycle drain.

### Income sources

| Source | Amount | When |
|---|---|---|
| Battle result | Occupation: 2D3×10 win / D3×10 loss or draw. Takeover: 2D6×10 win / D6×10 loss or draw | Post-battle, Receive Rewards |
| Side Job completed | Occupation D3×10, Takeover D6×10 (+D3×10 more if the Fence Hangout Territory was the stake) | Post-battle, Receive Rewards |
| Territory Income Boons | 15, 20 or 25 credits per Territory, per Territory entry | Post-cycle, Collect Income |
| Reputation | 10 × current Reputation | Post-cycle, Collect Income |
| Work Territory action | 15 credits per participating fighter, hard cap of 5 fighters per gang per cycle | Post-cycle, Actions |
| Downtime grant | 250 credits, ring-fenced and non-bankable | Downtime cycle only |
| Selling stash items | Half the item's value, rounded up, floor of 5 credits | Post-cycle, Update Roster |
| Corpse Farm battlefield effect | 10 credits per enemy taken Out of Action, in battles staking that Territory | During battle |

### Expenditure

| Sink | Cost |
|---|---|
| Recruiting models | Model's Credit Cost |
| Equipment | Item cost; Trading Post items additionally cost Trade Points |
| Medical Escort (treat a Critical Injury) | 30 credits base, +50 credits per +1 to the roll |
| Fit Bionics (remove a Lasting Injury) | 50 credits per injury instance |
| Visit Chop Shop (remove Lasting Damage) | 50 credits per damage instance |
| Ransom a captured model | D6×10 credits |
| Hired Guns | Recruited from Stash during the Pre-battle Sequence |

### Gang Rating

Sum of the Credit Cost of every model in the gang. **Excludes** Stash credits and Stash
equipment. Consumers:

- Challenge ordering (ascending, from cycle 2 onwards).
- **Underdog bonus**: if a gang's Rating is at least 200 credits below its opponent's, it gets
  one extra Gang Tactic for that battle per *full* 200 credits of deficit. This is the only
  in-battle balancing lever tied to Rating.
- Ordering of Hired Gun recruitment in the Pre-battle Sequence (higher Rating commits first).

Note that free recruits granted by Territory Boons still add their full cost to Gang Rating
and Wealth, and discounted recruits add their *undiscounted* cost.

### Wealth

Sum of all model costs **plus** Stash credits **plus** the value of Stash equipment. Consumers:
the Creditor Triumph, and the universal tiebreak for every Triumph. Wealth and Rating are
therefore two distinct derived totals over overlapping inputs and must both be computed.

---

## 4. Reputation

Reputation is a first-class gang attribute, tracked on the Gang Roster alongside Gang Rating
and Wealth. The reference is explicit that it measures standing rather than size — a small
gang can carry a high Reputation.

**Initial value:** 1. **Floor:** 1; it can never drop below this. **No ceiling is stated.**

### Gains

- Winning a battle: +1 in the Occupation phase, +2 in the Takeover phase.
- Territory Boons of the Reputation kind, while the Territory is held. Two Territories in the
  core list carry this: Generatorium (+1) and Gambling Den (+1).
- The Warmonger Triumph carried into a following campaign: the gang founds with +2 Reputation.

### Losses

- Losing control of a Territory during the Takeover phase: −1. (No equivalent is listed for
  the Occupation phase.)
- Losing a Territory whose Boon granted Reputation removes that grant — the reference frames
  this as the bonus being lost, not as a Reputation penalty.

### Ordering rule

If a gang both gains and loses Reputation in the same resolution, **all gains apply first**,
then losses, then the floor of 1 is enforced. This matters: a gang at 1 that gains 2 and loses
1 ends at 2, whereas applying the loss first would clamp and then rise to 3.

### Effects

- **Income**: 10 × Reputation credits every Post-cycle Sequence. This is the whole of
  Reputation's mechanical payoff during play — it is an income multiplier.
- **Powerbroker Triumph**: highest Reputation at campaign end.

### Modelling implication

Reputation is *not* a plain counter. It decomposes into a persistent earned component plus a
set of conditional modifiers derived from currently-held Territories. A territory changing
hands must move the modifier with it. An implementation that increments a single integer when
a Reputation-granting Territory is gained will drift when that Territory is lost, and will
interact wrongly with the floor of 1.

---

## 5. Territories and holdings

Territories are the campaign's central contested resource and the reason battles happen.

### Kinds of Territory

- **Settlement** — every gang has exactly one. Cannot be lost, cannot be staked. Grants a
  Boon like any other.
- **Contested Territories** — 18 named entries in the core D66 Territory Selection table, with
  the pool sized at 3 per player. Duplicates are explicitly allowed.
- **Gang-specific Territories** — referenced as a possibility (a gang may roll its starting
  Territory from its own table if it has one) but no such table appears in the core reference.

### States

A Territory in the campaign is in one of: unclaimed (in the pool), reserved (nominated as a
stake, withdrawn until the battle resolves), or controlled by a specific gang.

### Acquisition and loss

- Only two routes in: win a battle in which the Territory was the stake, or have a challenge
  declined. There is no purchase, trade, or gift mechanism.
- Draw handling: staking an unclaimed Territory and drawing returns it to the pool; staking a
  controlled Territory and drawing leaves control unchanged.
- Dominator Triumph carried into a following campaign grants one extra Territory at founding.

### Boons

A Boon is the benefit attached to a Territory, active only while held. Five kinds:

| Boon kind | Behaviour |
|---|---|
| **Income** | Fixed credits added to Stash during Collect Income. Values in the core set: 15, 20, 25. |
| **Recruit** | A free or discounted model. Typically offered as an *alternative to* the Income Boon, i.e. an either/or election each cycle. Free recruits still add full cost to Rating and Wealth; discounted recruits add full undiscounted cost. Equipment beyond the model's base cost is paid for normally. **Recruits stay with the gang even after the Territory is lost.** Several are gated on the gang not already having that model on the roster. |
| **Equipment** | Named items added to the Stash during Collect Income. Also usually an alternative to the Income Boon. Items are **kept and sellable after the Territory is lost.** |
| **Reputation** | A conditional +N to Reputation for as long as the Territory is held. |
| **Special** | Bespoke rule. In the core set only Tech Bazaar: +1 Trade Point per Post-cycle Sequence, and the gang may always buy from the Trading Post regardless of whether anyone took the Visit Trading Post action. |

A single Territory may carry several Boons at once (e.g. Income + Reputation on the
Generatorium; Income *or* Recruit as an election on most others).

### Battlefield Effects

Most Territories additionally carry a **Battlefield Effect** that applies to any battle in
which that Territory is the stake — announced in step 5 of the Pre-battle Sequence. These are
in-battle rule modifiers (free Reload actions, visibility overrides, weapon restrictions in
round 1, extra XP for close-combat takedowns, extra Side Jobs, extra credits per takedown, and
so on). Note that some of them change *campaign-facing* outputs: Fence Hangout increases the
Side Job payout, Corpse Farm pays credits per enemy taken Out of Action, Bounty Den generates
an extra Side Job per player, Fighting Pit and Bone Shrine both add XP routes.

---

## 6. Post-battle sequence

Five ordered steps, performed with both players present, immediately after every battle.

### 1. Wrap-up

*Inputs:* end-of-battle model states; any "at the end of the battle" effects.
*Outputs:* deaths, Lasting Injury/Damage rolls, Recovery flags, capture resolutions.

- **Succumbing.** For each model that was Seriously Injured/Damaged when the battle ended, or
  which left the battlefield while Seriously Injured/Damaged, roll D6. On 3+ it is fine; on
  1–2 it counts as having gone Out of Action and takes a Lasting Injury/Damage roll.
- **Capture resolution.** Any model that rolled the Captured result (61–62) on the Lasting
  Injury/Damage table now rolls D6 on the Escape table: 1 = executed, deleted from the roster;
  2–4 = ransomed, the owning gang must pay the capturing gang D6×10 credits during the next
  Update Roster step or the model dies and is deleted with its equipment going to a Stash;
  5–6 = escapes cleanly and goes into Recovery. A paid ransom also results in Recovery.

### 2. Reassign Territory

*Inputs:* battle result, the staked Territory, its prior control state.
*Outputs:* new control state.

Winner takes (or retains) the stake. On a draw: an unclaimed Territory stays unclaimed and
returns to the pool; a controlled Territory stays with its prior holder.

### 3. Receive Rewards

*Inputs:* battle result, campaign phase, Side Job outcomes, in-battle XP events.
*Outputs:* Stash credits, Stash equipment, Reputation delta, per-model XP.

- Credits and any equipment per the campaign phase's reward table (§1). Equipment lands in the
  Stash and is only distributable in the Post-cycle Sequence.
- Reputation adjustments, gains before losses, floored at 1.
- **XP awards** (per model):
  - 1 for taking part in the battle.
  - 1 for directly causing an enemy to become Seriously Injured/Damaged.
  - 2 for directly causing an enemy to go Out of Action; a further 1 if that enemy was a
    Leader, Champion, Brute or Vehicle.
  - The Serious Injury and Out of Action awards do not stack for the same enemy within one
    activation — only the higher applies.
  - 1 for assisting another fighter's successful Recovery test (Vehicles neither give nor
    receive assistance).
  - 1 for controlling an objective during an End phase, once per battle per fighter; only one
    fighter per objective is credited; Vehicles and Pets cannot control objectives.
  - 1 extra to the killer on a Memorable Death (66) Lasting Injury result.
  - Situational: the Mentor skill (+1 on a passed Leadership check when a nearby friendly
    gains XP), the Fighting Pit Territory (+1 for close-combat Serious Injury/Out of Action),
    the Bone Shrine Territory (shrine marker earns XP as an objective), and the Lesson Learnt
    (11) Lasting Injury result (D3 XP).

### 4. Clean House

*Inputs:* dead/destroyed models, retirement decisions, whether the gang still had a model on
the battlefield at the end.
*Outputs:* roster deletions, Stash additions.

- Dead fighters and destroyed vehicles are deleted from the roster.
- A dead fighter's equipment goes to the Stash **only if** the gang had at least one model on
  the battlefield when the battle ended; otherwise it is lost. This makes voluntary flight and
  bottling out materially expensive.
- Type-based exceptions override this: when a Vehicle, Brute or Hanger-on leaves the roster,
  its equipment is deleted rather than stashed.
- The player may also retire models here, typically ones crippled by Lasting Injuries; their
  equipment is stashed subject to the same type rules.

### 5. Report Results

*Output:* a report to the Arbitrator containing the participating gangs, the outcome, which
Territory changed hands if any, and how many enemies each gang took Out of Action. The
cumulative Out of Action count feeds the Slaughterer Triumph, so it must be persisted per
gang across the whole campaign, not just per battle.

---

## 7. Post-cycle sequence

Run by every gang at each cycle boundary. Three steps; the third has four sub-steps.

### 1. Post-cycle Actions

Each model may perform **one** action. The player chooses the resolution order; actions are
resolved one at a time. Models that are In Recovery or Critically Injured/Damaged may not act.
Unless a specific action says otherwise, different models may repeat the same action.

| Action | Eligibility | Effect |
|---|---|---|
| **Medical Escort** | Leader or Champion | Resolved at the start of Update Roster. Targets a fighter with a Critical Injury. Pay 30 credits or the fighter simply dies with no roll. Then D6: 1 = dies; 2–3 = stabilised, apply the Lasting Injury table result whose D66 first digit is 5 and second digit is the rolled D6; 4–6 = full recovery, goes into Recovery with no lasting effect. Each extra 50 credits paid adds +1 to the roll. |
| **Fit Bionics** | Leader or Champion | Resolved at the start of Update Roster. Removes Lasting Injuries from another fighter at 50 credits each; repeated instances of the same injury cost separately. Critical Injuries cannot be removed this way. The targeted fighter forfeits its own Post-cycle Action, and cannot also be the target of Medical Escort this cycle. |
| **Develop Tactics** | Leader or Champion | Generate one new Gang Tactic and add it to the roster. |
| **Visit Chop Shop** | Vehicle | Resolved at the start of Update Roster. Removes any number of Lasting Damage results, including Critical Damage, at 50 credits each; repeats cost separately. |
| **Work Territory** | Leader, Champion, Ganger or Prospect; **maximum five fighters per gang per cycle** | +15 credits to the Stash each. |
| **Visit Trading Post** | Leader or Champion | Unlocks Trading Post purchasing for the gang this cycle and contributes Trade Points: 2 for a Leader, 1 for a Champion. |
| **Train** | Any model | +2 XP. |

The set is extensible: Territories, skills and other sources may add actions. The Connected
skill adds an additional Visit Trading Post action worth 1 TP, stackable with the model's
normal action.

Because actions resolve before Advance Models, XP earned from Train counts toward advancement
in the same Post-cycle Sequence.

### 2. Collect Income

*Inputs:* Territories held, Reputation.
*Outputs:* Stash credits, Stash equipment, free/discounted recruits, Trade Points.

- Each held Territory yields its Boon(s): income credits, equipment into the Stash, a recruit
  (free or discounted), a Reputation modifier, or a Special effect.
- Each gang additionally gains 10 × Reputation credits.

### 3. Update Roster

**A. Advance Models.** For each model, compare accumulated XP to the rank thresholds. Each
rank crossed produces one roll on the Advancement table. Multiple ranks in a single cycle
produce multiple rolls. Starting XP awarded when a model joins the gang never generates
advancements. On each roll (2D6) the player may take any result at or below the number rolled.
Every advancement raises the model's Credits Value by a table-specified amount, which
propagates to Gang Rating and Wealth. If every available result is blocked by a characteristic
maximum, the player may take any result from the table instead.

Two subtype promotions run through this step rather than the advancement table:

- A Prospect reaching 13+ XP becomes a Ganger **instead of** rolling an advancement: swaps
  Prospect for Ganger, gains the Specialist subtype (so immediately picks a specialisation and
  its free skill), and gains +15 credits of cost. The fighter's entry does not change.
- A Ganger reaching 37+ XP becomes a Champion **after** rolling its advancement: swaps Ganger
  for Champion, keeps all other subtypes, and (via the Gang Tactics trigger table) generates 1
  new Gang Tactic.

**B. Visit the Trading Post.** In order: recruit new models from the gang list; purchase
equipment; sell unwanted items.

- Gang Equipment List items may always be bought.
- Trading Post items may only be bought if at least one fighter took the Visit Trading Post
  action this cycle (or the gang holds the Tech Bazaar). Each purchase costs both credits and
  the item's Trade Point value, drawn from the pool of TP generated that cycle. Unspent TP are
  lost at the end of this sub-step.
- Items marked Exclusive (TP value "E") can only be bought if they appear on a model's own
  Equipment List.
- Selling: item is deleted from the Stash for half its value, rounded up, minimum 5 credits.

**C. Redistribute Equipment.** Models may discard weapons and wargear into the Stash, and be
issued anything from the Stash. Exclusive items may only be issued to models whose gang
Equipment List carries them. Models may exceed three weapons, in which case they need multiple
Model Cards representing distinct equipment sets. Stash equipment may be assigned to any
number of a model's cards.

**D. Clean House.** Clear all In Recovery flags; delete dead, destroyed and retired models.

Also resolved during Update Roster: ransom payments arising from the Escape table, and any
correction of the Champion/Brute/Hanger-on composition ratio (§9) by retiring or recruiting.

---

## 8. Fighter progression

### XP and ranks

XP is accrued per model from battles (§6.3) and from the Train action. Rank is a pure function
of total XP over 21 threshold bands, mapping onto six titles: Rookie, Gang Member, Gang
Exemplar, Gang Hero, Gang Legend, Legend of the Underhive. Crossing a band boundary triggers
one advancement roll; the bands widen as XP rises (3-point bands up to 12, then 6, then 12,
then 24).

### Advancements

A 2D6 table of nine result rows, each giving a menu of characteristic increases or skill
grants and a fixed Credits Value increase from +5 to +30. Higher rolls unlock strictly better
options, and a player may take any lower row. A roll of 12 additionally permits selecting a
skill from *any* Skill Set, including sets normally exclusive to other gangs and the Inherent
skills — subject to the skill's own Type/Subtype restriction.

A separate maximum-characteristics table caps all thirteen characteristics. No advancement,
equipment or bionics work may exceed those caps unless a rule says so explicitly.

### Skills

Six universal Skill Sets of six skills each (Agility, Brawn, Combat, Cunning, Savant,
Shooting), plus three Inherent skills granted by rules rather than chosen. Each fighter entry
in a gang list declares Primary and Secondary access per set; advancements variously grant
"random Primary", "select Primary", "random Secondary", "select Secondary" or free choice.
Wyrds treat the Wyrd Powers list as a Secondary Skill Set, so wyrd powers arrive through the
ordinary advancement channel. Eight Specialist specialisations each grant a fixed free skill.

### Injury, recovery, capture and death

- Going Out of Action in campaign play always produces a D66 roll on the Lasting Injury table
  (fighters) or Lasting Damage table (vehicles). Duplicate results stack. Parts of a result
  that cannot be applied (a duplicated skill, a capped characteristic) are dropped and the
  rest applied. Multiple simultaneous causes still produce only one roll.
- **In Recovery** is a cycle-scoped state: the model misses all remaining battles that cycle
  and may not take Post-cycle Actions. It clears in Clean House at the end of the cycle.
- **Critical Injury / Critical Damage** is terminal unless treated: a Critical Injury kills the
  fighter unless a Medical Escort succeeds; a Critically Damaged vehicle cannot fight or take
  Post-cycle Actions until the chop shop repairs it.
- **Captured** removes the model from the owner's control pending the Escape table (§6.1) —
  execution, ransom, or escape.
- Permanent characteristic reductions (BS, WS, M, S, T, Ld) come from six of the Lasting
  Injury results; the injury persists on the model card until removed by Fit Bionics.
- **Death of a Leader** triggers automatic promotion: highest Leadership among, in priority
  order, non-Loner Champions, then Loner Champions, then any fighter that is not a Beast,
  Brute, Pet or Support. Ties break on total XP, then player choice. The promoted fighter gains
  the Leader subtype, loses Loner/Champion/Ganger/Prospect, and its *role* changes to the
  gang's leader role for equipment and skill access — keeping existing gear even if now
  disallowed, but unable to buy role-specific gear from its old role. Vehicles and Hangers-on
  can never be promoted; if only those remain, the gang is dissolved.

---

## 9. Gang roster changes

### Founding

- Budget 1,000 credits by default, adjustable by the Arbitrator; the budget may not be
  exceeded. Unspent credits carry into the Stash in campaign play (they are lost in skirmish).
- Composition constraints: exactly one Leader; and the count of models with Champion, Brute
  or Hanger-on subtypes must be ≤ the count of models without any of those. Pets do not count
  (they are wargear). If a campaign drifts out of compliance, the player must fix it in a
  Post-cycle Sequence by retiring offending models or recruiting ordinary ones.
- Equipment constraints: max three weapons per fighter (grenades count as wargear, not
  weapons); asterisked weapons occupy two of the three slots; at most one accessory per
  weapon; vehicles have per-entry weapon limits.

### Equipment sets

A model may hold multiple Model Cards, each a different loadout drawn from the equipment it
owns. No additional cost — each item is bought once and may appear on any number of cards. The
roster carries one line per model with the total cost of everything it owns. Only one card is
used per battle; under random crew selection, all of a model's cards are shuffled together and
one drawn, so the player cannot choose the loadout.

### Mutability

Locked during a cycle; mutable only in the Post-cycle Sequence (recruit, buy, sell,
redistribute, retire, promote, heal). The exceptions that let a gang spend mid-cycle are Hired
Guns, recruited from the Stash during the Pre-battle Sequence of an individual battle, and any
Territory Boon that supplies a Hired Gun.

### Enduring gangs

A gang marked Enduring at wrap-up can be re-founded for a later campaign:

- The old Leader retires permanently. The new Leader must be one of the previous iteration's
  fighters, hired for their Credits Value with all Lasting Injuries, XP, weapons, wargear and
  skills carried over, then processed through the Death of a Leader promotion rules.
- Any other previous-iteration model may be rehired on the same carry-over terms.
- One earned Triumph is selected and grants a founding benefit (§11), for that next campaign
  only.

---

## 10. Scenarios

Scenarios are generated per battle, at the moment a challenge is issued, from four independent
D6 tables. There is no scenario list as such; a scenario is a tuple.

| Table | Rolled by | Determines |
|---|---|---|
| Deployment | Challenger | One of six deployment-zone geometries |
| Objective | Challenger | One of six victory conditions (VP races, elimination scoring, zone control) |
| Side Job | Each player, separately | A secondary objective worth a credit payout |
| Crew | Challenged player | How each side selects its starting crew and reinforcements |

Crew selection methods referenced by the Crew table: Random (X), Custom (X), Hybrid (X+Y),
and Reinforcements (X) with a per-round arrival schedule and a D6 roll fixing how far from
enemies each reinforcement deploys. Support-subtype fighters are always included and don't
count against crew limits; Pets ride along with their owner; Hangers-on may be excluded from
random draws.

Optional battlefield modifiers: Pitch Black (a D6 table setting a Visibility band) and Tunnel
Warfare (no climbing, no ladders), both by mutual agreement.

The Arbitrator may substitute entries into any of the four tables, resize them, change them
between cycles to reflect a shifting campaign narrative, or simply dictate which entry applies
to a given battle.

### Campaign-level consequences of a scenario

- Win/lose/draw drives Territory transfer (§6.2) and the phase-scaled credit and Reputation
  reward (§1).
- Side Job completion pays credits per phase, independently for each gang — both sides can
  complete theirs.
- Enemy models taken Out of Action are reported and accumulated for the Slaughterer Triumph.
- The staked Territory's Battlefield Effect modifies the battle, and in several cases modifies
  the payouts (extra Side Job, extra Side Job money, credits per takedown, bonus XP).
- Voluntarily fleeing (permitted once a third of the starting crew is lost) is an automatic
  scenario loss, and risks losing a dead fighter's equipment if no model remains on the field
  at the end.

---

## 11. Named entities and tables requiring data modelling

Everything below is a distinct named collection the system needs as data, with approximate
size and row shape.

### Campaign-structural

| Entity | Entries | Row shape |
|---|---|---|
| **Campaign phases** | 3 default (Occupation, Downtime, Takeover) | name; cycle count; win/lose/draw/side-job payout dice expressions; Reputation on win; Reputation on territory loss; stake-eligibility rule (unclaimed-only / controlled-only); flat grant (Downtime's 250cr, ring-fenced) |
| **Territory pool sizing** | 6 rows (3–8 players) | player count → territories generated. Effectively `3 × players` |
| **Triumphs** | 5 | key; name; end-of-campaign criterion (max territories / cumulative enemy OoA / max Wealth / max battles fought / max Reputation); next-campaign founding benefit |
| **Triumph founding benefits** | 5, 1:1 with Triumphs | free-text effect, but mechanically: extra starting Territory; 9 distributable XP capped at 3 per model; +100 starting credits; +2 Reputation plus attacker/defender election in the first battle; one free Hanger-on from a list of five |

### Territories

| Entity | Entries | Row shape |
|---|---|---|
| **Territory Selection table** | 18 (D66, in adjacent pairs) | D66 range → Territory name |
| **Territory definitions** | 19 (18 above + Settlement) | name; flavour; one or more Boons; optional Battlefield Effect |
| **Boons** | ~25 across the 19 Territories | kind (Income / Recruit / Equipment / Reputation / Special); value; whether it *replaces* the Income boon as an election; eligibility predicate (e.g. "gang has no Ammo-Jack on roster"); persistence-after-loss flag (recruits and equipment persist; income, reputation and specials do not) |
| **Battlefield Effects** | 18 (one per non-Settlement Territory) | name; effect text; applies only when this Territory is the stake. Several alter campaign-facing outputs (Side Job payout, credits per OoA, extra Side Job, bonus XP) |
| **Hangers-on referenced by Boons** | 6 named (Ammo-Jack, Rogue Doc, Slopper, Hive Watcher, Dome Runner, plus generic Ganger) | Not statted in this reference — supplied by gang lists / supplements |

### Post-battle and post-cycle

| Entity | Entries | Row shape |
|---|---|---|
| **Post-battle sequence** | 5 steps | ordered; each with sub-procedures |
| **Escape table** | 3 rows (D6 bands 1 / 2–4 / 5–6) | outcome: executed, ransomed (D6×10, deferred to Update Roster), daring escape |
| **Post-cycle sequence** | 3 steps, third with 4 sub-steps | ordered |
| **Post-cycle Actions** | 7 core, extensible | name; eligible Types/Subtypes; per-gang cap (only Work Territory has one, at 5); credit cost formula; resolution timing (immediate vs. start of Update Roster); effect |
| **Medical Escort result table** | 3 rows (D6 1 / 2–3 / 4–6) | outcome: death, stabilised-with-injury (feeds a partial D66 lookup with first digit fixed at 5), full recovery. Modifiable by +1 per 50 extra credits |
| **Model Ranks** | 21 XP bands | XP range → title (6 distinct titles) |
| **Advancement table** | 9 rows (2D6, some banded) | roll → menu of one-or-more selectable outcomes (characteristic +1 options, skill grants) → Credits Value increase (+5 to +30) |
| **Maximum characteristics** | 1 row × 13 columns | per-characteristic cap |

### Injury and status

| Entity | Entries | Row shape |
|---|---|---|
| **Lasting Injury table** | 15 rows (D66, banded) | range → name → effect (XP gain, Condition grant, characteristic reduction, Recovery flag, Captured, Critical Injury, instant death) |
| **Lasting Damage table** | 15 rows (D66, banded) | same shape, vehicle-flavoured, plus explosion effects |
| **Injury dice faces** | 3 symbols | Injured / Serious Injury / Out of Action |
| **Model Statuses** | 4 | Active, Engaged, Suppressed, Seriously Injured/Damaged, with a strict priority order |
| **Conditions** | 9 named in core, open-ended | Fearsome, Frenzy, Hatred (X), Injured/Damaged, Intoxicated, Terrifying, Webbed, Insanity, plus weapon-trait-derived ones |
| **Insanity table** | 6 rows × 3 columns | D6 → forced action for unengaged / engaged / seriously-injured models |
| **Fighter Subtypes** | 14 | Beast, Brute, Champion, Flying, Ganger, Hanger-On, Leader, Loner, Mounted, Pet, Prospect, Specialist, Support, Wyrd — each with rules affecting crew selection, post-cycle eligibility, equipment inheritance on death, and promotion |
| **Vehicle Subtypes** | 8 | Hybrid, Loner, Manoeuvrable, Skimmer, Tracked, Transport (X), Walker, Wheeled |
| **Specialist specialisations** | 8 | name → free skill |

### Skills, tactics, powers

| Entity | Entries | Row shape |
|---|---|---|
| **Skill Sets** | 6 sets × 6 skills = 36, plus 3 Inherent | set; D6 index; name; eligible model types; rules text |
| **Skill access** | per fighter entry | fighter → set → Primary/Secondary/none. Lives in gang lists, not in the core reference |
| **Core Gang Tactics** | 18 (D66, in adjacent pairs) | D66 range; name; timing trigger; effect. Gang holds a *collection* of these; each usable once per battle; re-roll duplicates on generation |
| **Gang Tactic generation triggers** | 3 rows | trigger (Leader added / Champion added, including promotion / Develop Tactics action) → number generated (2 / 1 / 1) |
| **Wyrd Powers** | 6 | D6 index; name; action type; continuous-effect flag; rules |
| **Perils of the Warp** | 6 rows | D6 → effect |

### Scenario generation

| Entity | Entries | Row shape |
|---|---|---|
| **Deployment table** | 6 | D6 → named map with deployment-zone geometry |
| **Objective table** | 6 | D6 → name; objective placement; VP scoring rule; VP threshold to win; draw conditions |
| **Side Job table** | 6 | D6 → name; completion condition; rolled per player |
| **Crew table** | 6 | D6 → per-side crew selection method (Random/Custom/Hybrid with parameters) and Reinforcements parameters; may differ between attacker and defender |
| **Crew selection methods** | 4 | Random (X), Custom (X), Hybrid (X+Y), Reinforcements (X) |
| **Pitch Black table** | 4 rows (D6 banded) | D6 → Visibility band (3"/6"/12"/24") |

### Equipment and economy

| Entity | Entries | Row shape |
|---|---|---|
| **Trading Post weapon list** | ~120 profile rows across 16 categories, including ammo/variant sub-rows | name; short range; long range; Strength; AP; Lethality; traits; credit cost; TP value (0–4, or "E" for Exclusive) |
| **Close combat weapons** | 6 categories | same shape |
| **Armour & field armour** | ~5 | name; effect; cost; TP |
| **Personal equipment** | 11 | name; effect; cost; TP |
| **Weapon accessories** | 7 | name; restriction (e.g. las-only, asterisked-weapons-only); effect; cost; TP |
| **Weapon traits** | ~60+ named | name; parameterisation; rules |
| **Gang Equipment Lists** | per gang | Not in this reference; supplied by gang lists |
| **Trade Points** | scalar per gang per cycle | generated 2/Leader, 1/Champion, +1 for Tech Bazaar, +1 per Connected skill use; spent at purchase; expires at the end of the sub-step |

### Gang-level derived values

| Value | Definition | Recomputation trigger |
|---|---|---|
| **Gang Rating** | Σ model Credit Cost | recruitment, death, retirement, advancement (+Credits Value), equipment purchase/assignment, promotion (+15 for Prospect→Ganger) |
| **Wealth** | Gang Rating + Stash credits + Stash equipment value | all of the above, plus income, purchases, sales, ransoms |
| **Reputation** | earned base + Σ Territory reputation modifiers, floored at 1 | battle results, territory gain/loss, founding Triumph benefit |
| **Territories held** | set of Territory instances | battle results, declined challenges |
| **Cumulative enemy OoA** | running total across the whole campaign | every battle report |
| **Battles fought** | running total | every battle report |

---

## 12. Open questions and ambiguity

**Genuinely ambiguous in the reference**

1. **Ransom equipment destination.** The Escape table says an unransomed model's equipment goes
   to "the owning gang's Stash". Given the model is in enemy hands, it is unclear whether this
   means the original owner or the captor. Both readings are defensible and the choice is
   worth real credits.
2. **Chop Shop circularity.** A Critically Damaged vehicle may not perform Post-cycle Actions
   until repaired at the chop shop — but Visit Chop Shop is itself a Post-cycle Action
   performed by the vehicle. The rule as written cannot be satisfied. Contrast Medical Escort,
   which is deliberately performed by a *different* model precisely to avoid this.
3. **Does the starting Territory come out of the contested pool?** The Arbitrator generates
   3 per player as the pool to fight over, and separately each gang rolls one starting
   Territory. Whether these overlap is not stated.
4. **Reputation loss outside Takeover.** The −1 for losing a Territory is listed only under the
   Takeover phase. Whether Occupation-phase losses are penalty-free, or the rule was simply
   stated once, is unclear.
5. **Reputation cap.** A floor of 1 is explicit; no maximum is given. With income at 10×
   Reputation and Takeover wins paying +2, this is an unbounded compounding income source.
6. **Nothing to stake.** In the Takeover phase the challenger must nominate a Territory the
   defender controls, but the Settlement can never be staked. A gang reduced to only its
   Settlement therefore cannot legally be challenged — and, since only controlled Territories
   may be fought over in that phase, it has no route back either.
7. **Battles during Downtime.** Not addressed. The phrasing implies Downtime is a battle-free
   cycle, but it is counted as a Cycle and the challenge rules are stated per-Cycle.
8. **Two-player campaigns.** The Territory pool table starts at 3 players. Whether a two-player
   campaign is intended, and with what pool size, is unstated.
9. **Persistent tie on Triumphs.** Ties break on Wealth; if Wealth also ties, all tied gangs
   receive the Triumph. So a Triumph is not guaranteed to have a single holder — the model
   must allow multiple winners per Triumph.
10. **Election timing for either/or Boons.** Most Territories offer Income *or* Recruit/
    Equipment. Whether the election is re-made each cycle or fixed on acquisition is not
    stated. Several Recruit boons are gated on the gang not already having that model, which
    implies a per-cycle re-evaluation.
11. **Simultaneous rank-ups and promotion interaction.** A Ganger crossing several ranks in one
    cycle, one of which takes it past 37 XP, rolls an advancement per rank *and* promotes —
    the ordering of those rolls relative to the subtype swap is not spelled out.

**Explicitly variable, by design**

The reference marks these as Arbitrator-configurable, so they must be settings rather than
constants: campaign length, phase count, phase length, cycle duration in real time, founding
budget, the Territory table's contents, all four Scenario table contents (which may even
change between cycles or be dictated per battle), whether card decks replace roll tables, and
the Pitch Black and Tunnel Warfare options.

**Deliberately out of scope of this reference**

Gang lists, gang Equipment Lists, per-fighter skill access, Hangers-on and Hired Gun profiles,
Brute profiles, gang-specific Territory tables and gang-specific Tactics are all referenced as
existing but live in supplements. Any campaign implementation is data-incomplete without them.

**Signals of change from the previous edition**

The reference rarely flags edition changes directly. Two places where it does: the removal of
laying fighters down to indicate Status (explicitly attributed to this edition), and the
Arbitrator's Toolkit framing throughout, which promotes previously fixed values to
configurable ones. The campaign's overall shape — a phase structure of expansion, a downtime
break, then a land-grab, resolved by multiple Triumphs rather than a single victor — is
presented as *the* core campaign rather than one campaign type among several, but the
reference does not itself contrast this against the earlier edition.
