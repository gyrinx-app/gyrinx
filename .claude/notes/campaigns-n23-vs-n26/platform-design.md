# A generic campaign platform: does n26 undermine it?

Revisits the comparison from the position that the generic system is the *right*
answer — Gyrinx informs, it doesn't police; arbitrators improvise; the job is to
make the common case easy through good defaults and templates.

Question asked: keeping assets, resources, the action log and battles, is there
anything in n26 that undermines that concept?

---

## The short answer

**No. Nothing in n26 undermines assets, resources, actions or battles.** The
n26 rules were written years after n23's, and the n23 abstraction still absorbs
them — in a couple of places better than I expected.

But n26 does expose **three structural gaps** and **one duplication**. Two of
the gaps mean the current *implementations* of resources and phases are subtly
wrong rather than merely thin, so they'd bite whichever campaign type you ran.

The distinction worth holding on to:

- The **concepts** survive n26 intact.
- The **shapes** of `CampaignResourceType` and `Campaign.phase` do not.
- One **subject** is missing entirely: campaign-authored per-fighter state.

---

## 1. What n26 confirms

Worth stating first, because it's the load-bearing result. Every one of these
maps onto an existing primitive with no new concept:

| n26 thing | Existing primitive | Notes |
|---|---|---|
| Territories | Asset with nullable `holder` | The unclaimed pool is just assets with no holder. Duplicates already allowed (#2075). |
| Settlement | Asset with a flag | "Can't be lost, can't be staked" is two booleans. |
| Reputation | Resource | Modulo the floor and derived-contribution problems below. |
| Cumulative enemies taken OOA | Resource | Needed for the Slaughterer Triumph. It's a per-gang counter — nothing more. |
| Battles fought | Resource, or derived | Needed for Warmonger. |
| Wealth / Rating | Already first-class | n26 uses them for different jobs; both already exist. |
| Triumphs | Assets held at campaign end, or resources | Multi-winner ties are fine — assets don't need to be unique. |
| Challenges | A `Battle` in `PRE_BATTLE` | See §2.4 — this one is a genuinely good fit. |
| Scenario (4 rolled tables) | `mission` string + dice in the action log | Roles are already content-authored via `ContentBattleRoleOption`. |
| Battlefield effects | Asset property, displayed on the battle page | Needs the asset↔battle link (§2.4), then it's free. |
| Gang Tactics | Gang-held assets | A collection of named things a gang holds. |
| Boon "either/or" elections | A logged decision, not stored state | Inform-not-police: show both, record the choice. |

The pattern: **most n26 "campaign statistics" are just resources**, and most
n26 "things a gang has" are just assets. That is the abstraction doing its job.

---

## 2. The three gaps

### 2.1 There is no time — and `phase` is a string

`Campaign.phase` is a free-text `CharField` that nothing reads. That is the
single biggest gap, and it is not n26-specific: any campaign with recurring
anything needs it.

n26 needs a time structure for at least five distinct jobs:

- **Recurrence** — income is collected per cycle.
- **Allowances** — one challenge per cycle; a maximum of five fighters may Work
  Territory per cycle.
- **Expiry** — Trade Points are generated, spent and lost inside one sub-step.
- **Attribution** — "which cycle did this happen in", without which
  end-of-campaign scoring can't be computed.
- **Varying defaults** — Occupation and Takeover pay different amounts and allow
  different stakes.

**Generic shape.** A campaign has an ordered sequence of **periods**. A period
has a name, an order, an optional grouping (what n26 calls a phase), and can
carry data — the defaults and guidance that apply while it's current. Battles,
actions and resource changes get stamped with the period they fell in.

Advancing the period is an arbitrator action that *proposes* everything
recurring: "collect income — here's what each gang is due, confirm or edit".
Nothing is enforced. A gang can be behind without being blocked.

This generalises well beyond n26 — Dominion has cycles, any campaign has rounds
or weeks, and a campaign with no structure at all just has one period.

**Risk worth naming:** n26 treats the cycle as a campaign-wide synchronisation
point where every gang moves together. For asynchronous play that means one slow
player stalls everyone. Inform-not-police resolves it — periods advance when the
arbitrator says so, and being behind is a display state, not a lock.

### 2.2 Assets can't contribute to resources

Today an asset's `properties` is free-form JSON that is **display metadata only**
(`properties_with_labels` just joins keys to labels), and a resource amount is a
single stored integer. There is no way for holding a thing to affect a number.

n26 leans on exactly that relationship, in two flavours:

- **Continuous** — Generatorium and Gambling Den each grant +1 Reputation *while
  held*.
- **Periodic** — most Territories yield 15/20/25 credits *per cycle*.

The continuous case is the one that makes the current model actively wrong. If
Reputation is a stored integer that gets incremented when a Reputation-granting
Territory is gained, it **silently drifts when that Territory is lost**, and it
interacts wrongly with the floor. A gang at 1 that gains 2 and loses 1 must end
at 2; applying the loss first and clamping gives 3.

**Generic shape.** A resource value becomes `stored base + Σ contributions from
currently-held assets`. The asset type's property schema gains typed entries
alongside its display-only ones:

- `grants N of resource R while held` (continuous, derived, never stored)
- `yields N of resource R per period` (periodic, proposed at period end, then
  stored once accepted)

This is generic and immediately useful for any campaign type — "this territory
gives +1 X" is the most common house rule there is. It also means the display
can honestly show *why* a number is what it is, which is the informing job.

### 2.3 Per-fighter campaign state is content-authored, not campaign-authored

Every campaign primitive is **per gang**: resources attach to a list, assets are
held by a list, attributes label a list. There is no campaign-authored per-fighter
equivalent.

Something close exists — `ListFighterCounter`
(`n23/core/models/list/campaign_state.py:68`) — but it is keyed to
`ContentCounter`, which is **content-authored** (site admin only) and gated on
fighter *type* via `restricted_to_fighters`. An arbitrator running a campaign
cannot define a per-fighter tracked value the way they can define a per-gang one.

n26 needs this for the Post-cycle Actions menu: each model performs one action
per cycle, with eligibility by type and subtype, per-gang caps, costs and
deferred resolution. "Has this fighter acted this period" is per-fighter,
per-period state with nowhere to live.

**Generic shape.** Campaign-authored counters on fighters, mirroring
campaign-authored resources on gangs — same authoring model and permissions,
different subject.

---

## 3. The duplication to resolve

Building a platform for multiple campaign types makes an existing overlap
awkward. "A named tracked thing" currently exists in **three** places with three
different authoring models:

| Model | Subject | Authored by |
|---|---|---|
| `CampaignResourceType` | Gang | The arbitrator, per campaign |
| `ContentCounter` | Fighter | Site admin, globally, gated on fighter type |
| `ContentAttribute` + `CampaignAttributeType` | Gang (labels) | **Both** — one of each exists |

Gang attributes genuinely exist twice: content-authored
(`ContentAttribute` → `ListAttributeAssignment`) and campaign-authored
(`CampaignAttributeType` → `CampaignListAttributeAssignment`).

The platform question this poses is a clean one. A tracked thing has:

- a **subject** — gang or fighter
- an **authoring scope** — content (ships with the game), campaign (this
  arbitrator's), or template (a starting point to clone)
- a **kind** — a number, a label, or a holdable thing

Today those three axes are tangled into four half-overlapping models. Untangling
them is what "a generic platform for multiple campaign types" actually means in
practice, and it's more valuable than any individual n26 feature.

---

## 4. Smaller shape problems in the current primitives

None of these are conceptual — they're the existing fields being too narrow.

- **Resources are `PositiveIntegerField`** with a hard floor of zero, and
  `modify_amount` raises rather than clamps. n26's Reputation floors at **1**, not
  0. A resource type needs a configurable floor and cap.
- **Resources have no lifetime.** Trade Points are generated, spent and expire
  within one sub-step. A resource type needs a lifetime: permanent, or reset each
  period.
- **Assets have no state beyond `holder`.** n26 wants a Territory withdrawn from
  the pool while a battle over it is pending. Good news: if a battle can have
  staked assets (§2.4), "reserved" is *derivable* — it's an asset staked on an
  unresolved battle — so no third state is needed.
- **Assets have no flags.** "Can't be lost", "can't be staked" (the Settlement).
- **Dice are D6 only.** `CampaignAction.roll_dice()` is `random.randint(1,6)`,
  and the form is labelled "Number of D6 Dice". n26 needs D3, 2D6 and D66. The
  standalone roller (`views/dice.py`) already does D3 and named dice and is
  URL-seeded so a roll is reproducible — that's the better model to converge on.

### 4.1 Battles need one new relation

A battle should be able to have **assets staked on it**. That single link buys
four things at once: n26's stake mechanic; the "reserved" pool state for free;
battlefield effects (show the staked asset's properties on the battle page); and
a natural home for the challenge flow, since a `Battle` in `PRE_BATTLE` with a
stake and a proposed opponent *is* a challenge. Declining is then "cancel the
battle, transfer the asset anyway".

Asset transfers already accept a `battle` argument for logging
(`transfer_to(new_holder, user, battle=None)`) — it just isn't persisted on the
asset.

---

## 5. What stays out

Being explicit about the boundary, because n26 changes plenty that isn't the
campaign system's problem:

- **Advancement, rank bands, injuries, skills** — the fighter domain. n26
  reworks these substantially (XP accumulates into ranks and forces a roll,
  rather than being spent to buy a chosen advancement), but that's a separate
  project from the campaign platform.
- **Equipment and recruit Boons** — a Territory that adds an item to the stash or
  grants a free fighter. Making this automatic would mean modelling equipment
  grants from assets. Under inform-not-police it doesn't need to be: it's a
  prompt with a link at income time, not an automation.
- **The rules' own contradictions** — a gang reduced to only its Settlement can't
  be challenged and has no route back; the Chop Shop repair is circular. If the
  app never enforces, these stay the arbitrator's call, which is the right place
  for them.

---

## 6. What the platform looks like

Pulling it together. Additions to what already exists are marked **new**.

```
Campaign
├─ periods                 NEW  ordered, named, groupable into phases,
│                               each carrying defaults/guidance
├─ resource types               per gang
│    └─ + floor / cap      NEW
│    └─ + lifetime         NEW  permanent | per-period
│    └─ + derived contributions from held assets   NEW
├─ counter types           NEW  per fighter, campaign-authored
│                               (mirrors resource types)
├─ asset types                  holdable, with a property schema
│    └─ + typed properties NEW  grants-while-held / yields-per-period
│    └─ + flags            NEW  cannot be lost / cannot be staked
├─ attributes                   labels — unify content- and campaign-authored
├─ actions                      log + dice
│    └─ + wider dice       NEW  D3 / 2D6 / D66, seeded and reproducible
│    └─ + stamped with period   NEW
├─ battles                      participants, roles, winners, result, crews
│    └─ + staked assets    NEW  buys stakes, "reserved", battlefield effects
│                               and the challenge flow in one relation
└─ templates                    the delivery mechanism for all defaults
```

### The defaults story

This is what makes the common case easy, and it needs no new machinery —
`Campaign.template` and `apply_campaign_template` already exist and already copy
asset types, resource types, attribute types and packs.

A shipped **"Necromunda n26"** template would carry: a Territory asset type; 19
Territory assets with their Boons as typed properties; a Reputation resource with
a floor of 1 and its derived contributions wired up; a period structure of seven
cycles grouped into three phases; and per-phase defaults for the battle payouts.

The arbitrator clones it and changes whatever they like — which is the whole
point, and is exactly what the n26 rules themselves invite, since they hand the
arbitrator explicit licence to vary campaign length, phase count, the Territory
table and all four scenario tables.

---

## 7. Verdict

Keep assets, resources, the action log and battles. n26 doesn't threaten any of
them.

Change three things, in this order:

1. **Periods** — replace the `phase` string with ordered periods. Everything
   recurring hangs off this, and nothing else can be built first.
2. **Resource shape** — floor/cap, lifetime, and derived contributions from held
   assets. This one fixes a latent correctness bug, not just a limitation.
3. **Per-fighter campaign counters** — give arbitrators the same authoring power
   over fighters that they have over gangs.

Then the n26 content is a template, not a feature.
