# Promotions — rules reference and spec

Rules research from `rule-reference/mirror` (Core Rulebook 2023 + house lists + FAQs),
feeding the content-driven promotions epic (#1596 Juve→Specialist, #1467 Prospect→Champion).
Written 2026-07-21.

## Vocabulary

A fighter has a **category** (Leader / Champion / Ganger / Specialist / Juve / Prospect /
Crew) and a **type** (a named entry in a gang list, e.g. "Goliath Forge Boss"). The 2023
rulebook states this framing explicitly in Death of a Leader:

> "…their **category** changes to 'Leader' and their **type** changes to that appropriate
> for their gang for the purposes of determining which equipment and Skill Sets they can
> access (for example, should an Orlock Road Sergeant be promoted to Leader, not only does
> their category change from Champion to Leader, but their type becomes 'Orlock Road
> Captain')." — `docs/founding-a-gang/gang-creation` (Core 2023)

Promotion changes category, type, or both — **never the statline** (see invariant below).

## The four promotion families (RAW)

### A. Ganger → Specialist (category relabel)

- **Source:** Core 2023 p148 (`docs/the-rules/gaining-experience`) + each house's
  `Promotion (X Specialist)` special rule.
- **Trigger:** roll of 2 or 12 on the Ganger 2D6 advancement table (6 XP, post-battle);
  *or* one Ganger promoted free at gang founding.
- **Effects:** "They are **still a Ganger**, but from now on gain all the benefits of
  being a Specialist" — keeps `Gang Fighter (Ganger)` (still counts toward the
  gang-composition majority). Gains Tools of the Trade, unlocked purchases (Special
  weapons; Heavy too for Orlock/Van Saar/Badzone), may spend XP on skills, and from now
  on picks advancements from the full table instead of rolling 2D6.
- **Bundled:** random Primary skill. **Cost: +20 credits** (total, including the skill).
- Specialist has its own skill-access row (Primary/Secondary) in every gang list, so
  access changes even though the statline and base cost don't.

### B. Specialist → Champion (core advancement purchase)

- **Source:** core Advancements table, "Specialists only" row.
- **Trigger:** 12 XP spent during any post-battle sequence.
- **Effects:** category → Champion; gains a random Primary skill. **Cost: +40 credits.**
- **Type choice:** the table just says "a Champion". In two-champion houses the player
  picks which champion type; the fighter then counts as that type for access and special
  rules (same "counts as" mechanics as family C).
- Gated by Champion composition caps where the gang list has them.

### C. Prospect/Juve → named type (house `Promotion (X)` / `Promotion (X or Y)` rules)

- **Source:** house gang lists (House of… books, consolidated in the mirror).
- **Trigger:** during the **Downtime** phase, fighter has **5+ Advancements** (errata'd
  to **3+** for Ash Waste Nomads; Badzone Enlisted Hive Scum is 3+). Optional, never
  compulsory, and **deferred while composition caps are full** (CGC FAQ: 3-Cutter cap —
  retire one or wait).
- **Target:** one named type, or a **choice of two**:
  - Goliath Forge-born → Forge Boss **or** Stimmer
  - Orlock Wrecker → Road Sergeant **or** Arms Master
  - Van Saar Neotek → Augmek **or** Archeotek
  - Delaque Psy-Gheist → Phantom **or** Nacht-Ghul
  - Cawdor Ridge Walker → Firebrand **or** Redemptionist Deacon
  - Ash Waste Nomads prospect → Watcher **or** Stormcaller
  - Escher Wyld Runner → Gang Matriarch (single target)
  - Ironhead Squat prospect → Exo Master (single)
  - Redemptionist Zealot (Juve) → Redemptionist Specialist (single, post-errata)
  - Badzone Enlisted Hive Scum → Badzone Enforcer Patrolman (**a Ganger type** — targets
    are not always Champions)
  - CGC Initiate (Juve) → Cutter (Champion) (via FAQ)
- **Effects (verbatim pattern):** "they will from now on **count as** [type] for the
  purposes of determining which **equipment and skill sets** they can access. Their
  existing **characteristics do not change**, but they will **lose** the [listed] special
  rules and **gain all the special rules** associated with [type]."
  - Lost rules are listed per fighter: always `Promotion (X)`, usually `Hot-headed`,
    `Fast Learner`, `Gang Fighter (Prospect)` (Escher errata added it), sometimes
    `Pious`, `Born in the Saddle`, `Expendable Conscripts`.
  - Skills granted by a lost special rule go with it (CGC FAQ: Infiltrate lost).
  - **No credit adjustment is stated.**
- "An appropriate model should be used to represent their new **category and type**."

### D. → Leader ("Death of a Leader")

- **Source:** Core 2023 (`docs/founding-a-gang/gang-creation`).
- **Trigger:** forced, when the Leader dies or is otherwise removed.
- **Eligibility:** highest Leadership among, in priority order: (1) `Gang Hierarchy (X)`
  holders, (2) `Tools of the Trade` holders, (3) anyone. Ties → most Advancements →
  player's choice.
- **Effects:** gains `Gang Leader`; category → Leader; **type → the gang's Leader type**
  (Road Sergeant → Road Captain); loses `Promotion (X)` if held; characteristics and
  other special rules unchanged. No stated cost change.
- **Conditional target types:**
  - Cawdor: `Fanatical` fighter → must become Redemptor Priest; `Pious` → chooses
    Word-Keeper or Redemptor Priest.
  - GSC: early-generation hybrid → Cult Alpha; later generation → Cult Adept.
  - Chaos Cults: type simply becomes Leader.

## What can change — the answer matrix

| Dimension | Changes? | Detail |
| --- | --- | --- |
| Category | **Yes** (B, C, D) | Family A formally keeps the fighter a Ganger (composition!) while granting Specialist benefits. |
| Type | **Yes** (B, C, D) | Sometimes a **choice of 2** (C, B-in-two-champion-houses); sometimes conditionally mapped (Cawdor/GSC leaders). |
| Statline | **Never** | Every type-change rule: "their existing characteristics do not change." Advancement-earned stats carry over. |
| Skills | Bundled gain only | A and B grant one random Primary skill as part of the promotion. C/D grant none. Skills from lost special rules disappear (CGC FAQ). |
| Skill-set access | **Yes** | Primary/Secondary sets follow the new type. |
| Advancement behaviour | **Yes** | Ganger random table → chosen advancements (A); `Fast Learner` lost (C); stat-increase caps re-base against the new category/type's basic profile. |
| Equipment list | **Yes** | Future purchases from the new type's list only; **all existing gear kept**, even off-list (Wrecker jump booster / Neotek grav-cutter FAQs). New type's category restrictions apply to new purchases (CGC Cutter: no new ranged weapons). |
| Special rules | **Yes, wholesale** | Lose the listed old-type rules, gain *all* of the new type's. |
| Cost / rating | Only where stated | +20 (A), +40 (B). C and D are silent → RAW cost unchanged. |
| Wargear identity | Rarely | Flavour transforms (CGC masks gain ornamentation → new rules). |
| Timing | Varies | Post-battle (A, B), Downtime with advancement threshold (C), on leader death (D), at founding (free Specialist, one per gang). |

**The core invariant:** promotion is an *identity and access* change, not a stat change.
RAW, a promoted Prospect-Champion is statistically still their old self plus whatever
advancements they earned — what changes is what they can buy, learn, and which special
rules govern them.

## Spec: what Gyrinx needs to express

Current support: Ganger→Specialist as a category relabel (`category_override`) — correct
for family A's category half, but doesn't switch skill/equipment access to the
Specialist row (#1596), and can't express families B–D at all (#1467).

### Content model

A promotion path is content data, editable in the admin — implemented as
`ContentPromotionPath` (`gyrinx/content/models/promotion.py`):

- `source` — ContentFighter FK (house-specific paths) *or* (house, category) for the
  generic core paths.
- `kind` — `CATEGORY_RELABEL` (family A) or `TYPE_CHANGE` (B, C, D).
- `targets` — M2M to ContentFighter, **1..n choices** (Forge Boss | Stimmer). For
  relabels: a target category label instead.
- Trigger metadata (informational, for UI guidance): `xp_cost` (12 for B), `cost_increase`
  (+20/+40), `advancements_threshold` (3/5 for C), `timing` (post-battle / downtime /
  founding / leader-death), `grants_random_primary_skill` (A, B).
- Conditional-target rules (Cawdor Fanatical/Pious, GSC generation) are out of scope as
  data — model as multiple paths or leave the choice to the player.

### ListFighter changes

- A promotion type pointer — third ContentFighter pointer (alongside base +
  `legacy_content_fighter`), **access-only** under the RAW-faithful decision below.
  Precedence:
  - equipment list: `legacy > promotion > base`
  - skill access, special rules: `promotion > base` (legacy never affects these — it is
    equipment-list-only)
  - statline, base cost: **base only** — the promotion pointer never touches them.
- Single active type-change (no stacking); promotion to Leader after Prospect→Champion
  *replaces* the override, not stacks.

### Statline & cost policy (decided 2026-07-21: RAW-faithful; supersedes 2026-07-05)

Decision: **RAW-faithful**. On every promotion — relabel or type change — the fighter
keeps its base `content_fighter` statline and base cost. The type-for-access pointer
affects equipment lists, skill access, and special rules only. Cost impact is solely the
flat, content-authored `cost_increase`, riding the existing `sq_advancement_cost_sum`
path exactly like today's promotions.

Why: it matches the rules verbatim ("their existing characteristics do not change"; cost
silent or a flat stated bump), and it is the *simpler* option — nothing is frozen or
snapshotted (the base FK stays), no live base-cost delta, no double-count trap against
`sq_advancement_cost_sum`, no `set_dirty()` cost arm, no `cost_override` interaction, no
#1826 pinning involvement. The earlier "as-if-hired" framing predated the rules research
and is retired.

### Equipment

- Keep **all** assignments on promotion (matches RAW + FAQs). No revalidation against
  the new list; existing gear is grandfathered.
- Cost pins stay frozen across promotion; only new purchases price against the new list.

### Eligibility & guardrails

Gyrinx is a bookkeeping tool: **warn, don't block**. Surface XP cost, advancement
threshold, and timing as guidance text on the promotion form; warn if `cost_override`
is set on the fighter; never hard-enforce composition caps (campaigns houserule these
constantly, and thresholds themselves get errata'd — Nomads 5→3).

### UI flow

Fighter → Promote → pick path (if several apply) → pick target type (if the path has a
choice) → summary of what will change (category, type, skill access, equipment list,
cost delta) → confirm. Reversal: single-level undo restoring the previous
category/override state.

### Seeds

- Core: Ganger→Specialist relabel (+20, random Primary skill) per house; Specialist→
  Champion type-change (12 XP, +40) with per-house champion choice sets.
- House books: the family-C table above (one row per source fighter).
- Leader paths (family D): later phase — needs the conditional-target story.

## Sources

- `docs/the-rules/gaining-experience` — advancement tables, Ganger 2/12, Specialist 12 XP row
- `docs/founding-a-gang/gang-creation` — Death of a Leader, category+type framing
- `docs/gangs/gang-lists/<house>/index.md` — `Promotion (X)` special rules per house
- `docs/gangs/gang-lists/*/faq` — kept-equipment, lost-skill, composition-cap, threshold errata
- `docs/gangs/gang-lists/{genestealer-cults,helot-chaos-cults}/...-in-campaigns` — conditional leader types
