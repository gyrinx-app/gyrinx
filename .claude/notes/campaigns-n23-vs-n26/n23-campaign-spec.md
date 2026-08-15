# n23 Campaign System — Specification (as built)

Derived from the Gyrinx codebase. Cites `file:line`. Companion to
`n26-campaign-spec.md` (rules-derived) and `comparison.md` (the analysis).
`n23-behaviour-detail.md` holds the long-form view-by-view reading this
summarises.

---

## 0. The one-sentence summary

**n23's campaign system is a general-purpose bookkeeping toolkit, not a rules
engine.** It gives an arbitrator generic primitives — named resources, named
assets, named attributes, a free-text phase, and a dice-rolling action log — and
then gets out of the way. Almost no game rule is encoded anywhere in it.

This is a deliberate and largely successful design. It is also the single fact
that determines how much work n26 campaigns will be.

---

## 1. Lifecycle

Three states, on `Campaign.status` (`n23/core/models/campaign.py:21-29`):

| State | Constant | Meaning |
|---|---|---|
| Pre-Campaign | `pre_campaign` | Recruiting gangs. Lists attached directly. |
| In Progress | `in_progress` | Running. Lists are campaign-mode clones. |
| Post-Campaign | `post_campaign` | Finished. No new lists. |

Guards are plain predicates (`campaign.py:194-204`). Note this is **not** the
project's `StateMachine` helper — `Battle` uses that, `Campaign` doesn't.
Transitions are hand-rolled and, unlike `Battle`, reversible (reopen).

There is no notion of cycles, rounds, weeks, or a phase sequence. `phase` is a
free-text `CharField(max_length=100)` whose help text suggests
`'Occupation', 'Takeover', 'Dominion'` (`campaign.py:83-91`), plus a
`phase_notes` TextField. The arbitrator types the phase name in. **Nothing reads
it; it is display-only.**

### 1.1 Campaign start — the important transition

`handle_campaign_start` (`n23/core/handlers/campaign_operations.py:57`) is
two-phase since #1222, because cloning many gangs inline blocked requests for
tens of seconds.

**Phase 1 — synchronous, atomic:**

1. Guard `can_start_campaign()`, with distinct errors for wrong-status vs
   no-lists (`campaign_operations.py:98-106`).
2. Snapshot `campaign.lists.filter(status=LIST_BUILDING)` — **only
   LIST_BUILDING lists are cloned**; anything else in the M2M is silently
   dropped.
3. `campaign.lists.clear()` — the pre-campaign roster is wiped and rebuilt from
   clones.
4. Per original, create a **stub** `List` in `CLONING_IN_PROGRESS` with only
   cheap scalars copied, `original_list` and `campaign` FKs set. Idempotent:
   an existing clone/stub is re-adopted rather than duplicated
   (`campaign_operations.py:122-139`).
5. Flip status to `IN_PROGRESS`; write one "N gang(s) joined" `CampaignAction`.
6. `transaction.on_commit` → enqueue one `complete_campaign_list_clone` per stub
   into task group `campaign-start:{campaign_id}`. **Enqueue failures are
   swallowed** (`:194-205`) — the stub just stays `CLONING_IN_PROGRESS`.

**Phase 2 — background, one task per stub** (`n23/core/tasks.py:19`), inside one
transaction under `SELECT FOR UPDATE`, returning early unless still
`CLONING_IN_PROGRESS` so redelivery is a clean no-op:

1. `_populate_clone_from(original)` — fighters, equipment, stash, facts.
2. `book_clone_actions(...)` — CLONE on the original, CREATE on the stub, run
   *after* populate so CREATE deltas see recomputed caches.
3. `_distribute_budget_to_list(...)`, priced off `original.cost_int()`.
4. `get_or_create` a `CampaignListResource` per resource type at its
   `default_amount`, owned by the campaign owner (`tasks.py:96-105`).
5. Flip to `CAMPAIGN_MODE`.

If referenced objects have been deleted, it logs and gives up, leaving the stub
stuck (`tasks.py:70-77`). A `retry_campaign_list_clone` view
(`views/campaign/lifecycle.py:99`) re-enqueues stuck stubs; the campaign page
polls `/tasks/status` on the group key.

**Joining a campaign forks the gang.** The campaign gang is a separate `List`
row with `original_list` pointing back at the player's list-building version.
The original is untouched. `Campaign.active_lists()` (`campaign.py:168`)
excludes stubs and is the correct accessor anywhere a member gang must be real.

### 1.2 Budget

`Campaign.budget`, default 1500 (`campaign.py:69`). Each gang receives
`max(0, budget − list_cost)` where list cost is rating + stash excluding credits
(`campaign_operations.py:217`). So the budget is a **target rating to top up
to**, not a grant — a gang already at or over budget gets nothing, and no action
rows are written.

It is booked as a `CAMPAIGN_START` `ListAction` with a `credits_delta`, followed
by an explicit `apply_credit_delta` (`create_action` is a pure record), then a
mirror `CampaignAction` for the log. This care exists to keep the credits ledger
reconcilable against `n23/core/cost/balance_sheet.py` (`campaign.py:241-245`).

### 1.3 End, reopen, archive

All admin-gated with confirm-on-GET, all delegating to a model method then
writing a `CampaignAction` and a `log_event`.

- `end_campaign` (`lifecycle.py:159`) — **no side effects on member gangs at
  all.** No un-cloning, no archiving, no reconciliation, no scoring. Lists stay
  in `CAMPAIGN_MODE` attached to a post-campaign campaign.
- `reopen_campaign` (`lifecycle.py:219`) — likewise inert.
- `archive_campaign` (`lifecycle.py:279`) — refuses while in progress. Archived
  state is then a hard guard on nearly every mutating campaign view.

### 1.4 Joining and leaving

`campaign_add_lists` (`views/campaign/lists.py:29`) carries most of the rules:
blocked post-campaign; candidates are the user's own or public
`LIST_BUILDING` non-archived lists; a `CAMPAIGN_MODE` list is explicitly
rejected (`:69`); a pack-compatibility gate offers to add the gang's packs to
the campaign, with archived and unowned-unlisted packs hard-blocked (`:81-92`).
Membership goes through `CampaignInvitation`, auto-accepted when the campaign
owner is the list owner (`:117`).

`campaign_remove_list` (`lists.py:349`) is admin **or** list owner. It refuses
post-campaign and refuses a cloning stub (#1222 — would orphan a half-built
clone). On removal it un-assigns every held `CampaignAsset` (holder → None, one
save each — an N+1), logs, removes from the M2M, and if the list is
`CAMPAIGN_MODE` archives it and nulls its `campaign` FK (`:428-432`).
**Resources, attribute assignments and action history are left behind.**

---

## 2. Data model

Eleven models in `n23/core/models/campaign.py`, plus three in `battle.py`. All
inherit `AppBase` (UUID PK, owner, archive, history) except one join table.

```
Campaign
├─ lists                M2M → List (campaign-mode clones once started)
├─ admins               M2M → User (shared arbitrators)
├─ packs                M2M → CustomContentPack through CampaignContentPack
├─ resource_types       → CampaignResourceType → CampaignListResource (per gang)
├─ asset_types          → CampaignAssetType → CampaignAsset → CampaignSubAsset
├─ attribute_types      → CampaignAttributeType → CampaignAttributeValue
│                            → CampaignListAttributeAssignment (per gang)
├─ actions              → CampaignAction (log + dice)
└─ battles              → Battle → BattleParticipant, BattleNote
```

### 2.1 Campaign

Beyond the above: `public`, `summary`, `narrative`, `template` (marks a copyable
preset), `group_attribute_type` (which attribute visually groups the gang
table), `default_gang_sort` (a metric token like `-wealth` or
`-resource:<uuid>`), `default_included_crew_categories` (JSON list of fighter
categories pre-opted-in for crew picking), and per-user `pinned_by` /
`starred_by`.

`is_admin(user)` (`campaign.py:206`) is owner-or-shared-admin, memoised per
instance and prefetch-aware because it is called once per fighter card.

### 2.2 The three generic primitives

**Resources** — `CampaignResourceType(campaign, name, description,
default_amount)` and `CampaignListResource(campaign, resource_type, list,
amount)`. `amount` is a `PositiveIntegerField`, so resources cannot go negative;
`modify_amount()` raises `ValueError` rather than clamping (`campaign.py:846`)
and writes a `CampaignAction` describing the change.

**Assets** — `CampaignAssetType(campaign, name_singular, name_plural,
description, property_schema, sub_asset_schema)` → `CampaignAsset(asset_type,
name, description, holder→List, properties)` → `CampaignSubAsset(parent_asset,
sub_asset_type, name, properties)`.

Both schema fields are JSON. `property_schema` is a list of `{'key','label'}`;
`sub_asset_schema` is `{key: {'label','label_plural','property_schema':[...]}}`.
Values live in the instance's `properties` dict, and `properties_with_labels`
(`campaign.py:690`) joins them for display, skipping keys no longer in the
schema. **The schema is a display contract only** — no typing, no validation, no
required fields, no numeric semantics.

Control is a single nullable `holder` FK. `transfer_to()` (`campaign.py:742`)
reassigns and logs, optionally attached to a battle.

**Attributes** — `CampaignAttributeType(campaign, name, description,
is_single_select)` → `CampaignAttributeValue(attribute_type, name, description,
colour)` → `CampaignListAttributeAssignment`. Purely labelling/grouping
(Faction, Team, Alliance); feeds `group_attribute_type`.

### 2.3 CampaignAction

Audit log and dice roller in one (`campaign.py:509`). FKs to campaign, user,
list, battle and `template_campaign`. Carries `description`, `outcome`, and
`dice_count` / `dice_results` (JSON) / `dice_total`. `save()` rolls if
`dice_count` is set and results are empty (`campaign.py:592`). Dice are
`random.randint(1,6)` — **D6 only; no D3, no D66**.

### 2.4 CampaignContentPack

Deliberately a bare `models.Model`, not `AppBase` — declined in #1774 because
`AppBase` would force a UUID PK swap on a live table for no benefit
(`campaign.py:468-480`). Carries `required`; `add_list_to_campaign` takes a
`select_for_update` lock on `pack_links` so a concurrent required-flip can't
race a join (`campaign.py:410`).

### 2.5 Battle

`n23/core/models/battle.py`. Uses the real `StateMachine` — forward-only
`pre_battle → in_progress → post_battle`. Fields: `campaign`, nullable `date`,
`mission` (free-text CharField), `participants` M2M through `BattleParticipant`,
`winners` M2M, and `result` (`""` unrecorded / `winners` / `draw` — blank is
deliberately distinct from draw, `battle.py:26-36`).

`BattleParticipant` carries an optional `role_option` FK to
`content.ContentBattleRoleOption`, so Attacker/Defender **is** content-authored,
unlike missions.

No stake, no territory link, no phase or cycle association, no scenario tables.

---

## 3. Participation and permissions

Three tiers: **campaign owner**; **shared admins / arbitrators**
(`campaign.admins`, PR #1922 / #988), merged by `is_admin()`; and **gang
owners**.

The recurring predicate elsewhere in core is
`Q(owner=user) | Q(campaign__owner=user)`, with helper `get_list_and_fighter()`
in `views/fighter/permissions.py`; `state.py` and `xp.py` still inline it.

Battle permissions are finer (`battle.py:149-194`): `can_edit` (owner or admin),
`can_manage` (those plus **any participating gang's owner**, so players run
their own battle flow), `can_add_notes` (= can_manage), `can_unarchive`. All
refuse if the battle or campaign is archived.

**Per-primitive permission reality** (from the views):

| Primitive | Type CRUD | Per-gang mutation | Writes to campaign log? |
|---|---|---|---|
| Resources | admin | admin **or holding list's owner** (`resources.py:326`) | yes (in model) |
| Assets | admin | transfer: admin **or current holder's owner** (`assets.py:636`) | yes (in model); create/remove/clone logged inline in views, and only `if campaign.is_in_progress` |
| Sub-assets | admin | admin only — a gang cannot touch sub-assets of an asset it holds | **no** |
| Attributes | admin | list owner or admin (`attributes.py:640`) | **no** |

Guard inconsistencies worth noting: `is_pre_campaign` blocks resource
modification and asset transfer but **not** attribute assignment or any
type-level CRUD; `campaign.archived` is re-checked ad hoc in ~12 places with
hand-written messages and a couple of edit views miss it; resource-type *edit*
lacks the archived guard that new/remove have.

---

## 4. Battles and post-battle

Battle flow is the state machine above, with crews layered on
(`n23/core/models/crew.py`, 1,301 lines — Battle Crews, #1346/#1993: a virtual
sub-gang per battle, recipe → lock → draw, which never mutates gang caches).

**The post-battle editor** (`n23/core/views/list/post_battle.py`, 518 lines;
form in `n23/core/forms/post_battle.py`) is a bulk per-gang update screen. One
submit can apply, per its `_ApplySummary` tally: credits, resources, asset
transfers, XP, injuries, kills, counters, fighter states and captures. It
delegates to the fighter handlers (`handle_fighter_add_xp`,
`handle_fighter_add_injury`, `handle_fighter_kill`, `handle_fighter_capture`,
`handle_fighter_adjust_counter`) and `handle_credits_modification`. Shipped as
iteration 2 via PR #2006 (closed #1810).

Critically: **it is a manual editor, not a sequence.** It presents everything at
once and the user decides what to enter. It does not walk ordered steps, does
not compute rewards, and does not know what a battle result implies.

---

## 5. Economy and bookkeeping

The most developed and most rules-agnostic part of the system, and the part most
worth keeping.

- **Credits** live on the `List` (`credits_current`, `credits_earned`), mutated
  via `apply_credit_delta` and always booked as a `ListAction` with a
  `credits_delta`.
- **Cost caches** — `rating_current`, `stash_current` — after the cost-cache
  deletion programme (#1860, complete) and cost-pinning (#1826, phases 1–9).
- **Balance-sheet invariants** in `n23/core/cost/balance_sheet.py` keep the
  ledger reconcilable.
- **Wealth** and **rating** are distinct derived totals; `default_gang_sort` can
  sort the campaign table by either, or by any resource.

---

## 6. Gangs in campaign mode

Entering a campaign clones the list into `CAMPAIGN_MODE`, which unlocks
campaign-only affordances: credits, XP spending, injuries, capture, death, stash
transfers, advancements. Fighter states (dead / captured / injured / recovery)
live on `ListFighter`.

Nothing is *frozen* — a campaign-mode gang stays editable at all times. There is
no cycle-scoped lock and no "roster is closed until the post-cycle sequence"
concept.

---

## 7. What is hard-coded to n23 rules

Remarkably little **in the campaign system itself**:

1. **`DEFAULT_RESOURCE_TYPE_NAME = "Reputation"`**
   (`n23/core/handlers/campaign_copy.py:302`), description "Gang reputation
   gained during the campaign", `default_amount=1`. Seeded into every campaign
   unless a template defines its own. This is the *entire* extent of n23 game
   vocabulary in the campaign models — and it is a name, not a mechanic:
   nothing reads it, grants it, or spends it.
2. **`Campaign.budget` default 1500** — the n23 founding budget.
3. **`phase` help text** naming Occupation / Takeover / Dominion — a hint only.
4. **D6-only dice** in `CampaignAction.roll_dice()`.
5. **`MAX_CREDITS = 10000`** at `resources.py:30` — declared and never used.

Outside the campaign package, the rules-bound parts campaigns *depend on* are
much heavier:

6. **`ADVANCEMENT_CONFIGS`** (`n23/core/forms/advancement.py:120`) — a Python
   dict **in a form** encoding the n23 XP economy: each advancement carries an
   `xp_cost`, a `cost_increase` and a `roll`. Players **spend** XP to buy a
   chosen advancement. Not content data, not overridable, wrong layer.
7. **Injuries** — `ContentInjury`, content-authored (good), plus
   equipment-injury links (#1027, PR #2076).
8. **Promotions** — content-driven since the promotions epic
   (#1596/#1467/#1468), with promotion paths seeded by migration.
9. **Battle roles** — `ContentBattleRoleOption`, content-authored.

---

## 8. Extension seams and weaknesses

**Already generic — reusable as-is:**

- The action log — arbitrary description/outcome/dice, FK'd to campaign, gang
  and battle.
- Resources — any named per-gang non-negative integer.
- Assets — any named holdable thing with a holder and free-form properties.
- Attributes — any named gang grouping.
- Permissions and the arbitrator model.
- The credits ledger, cost caching and balance-sheet reconciliation.
- Content packs, with their subscriber archive semantics.
- Invitations, pack gating, gang sorting, campaign templates and copying.

**Where it isn't generic:**

- **No time structure.** `phase` is a string. There are no cycles, no ordering,
  no "end of cycle" event — nothing to hang periodic income or per-cycle limits
  on. This is the single biggest gap.
- **No typed asset properties.** `property_schema` is display metadata. There is
  no way to say "this asset grants 20 credits per cycle" in a form the system
  can act on. Every n26 Boon would be a string a human reads and applies.
- **No asset state beyond `holder`.** No unclaimed / reserved / controlled
  tri-state, no pool, no staking.
- **No scheduling.** `mission` is free text; there is no challenge, no
  accept/decline, no per-cycle allowance, no ordering rule.
- **Battle *results* don't transact.** `handle_battle_end` writes the result and
  freezes crew ratings but touches no gang — no XP, credits or injuries. The
  post-battle editor does all of that manually, with a human deciding the
  numbers, and nothing records whether it was used (`battle_timeline`'s last
  step is hardcoded `"done": False`, `handlers/battle.py:427`).
  Battle *start* is the exception and the counter-example: `charge_crew_spending`
  (`handlers/battle.py:241`) moves credits correctly under `SELECT FOR UPDATE`,
  pairing every delta with a `ListAction` because the balance sheet asserts the
  chain, and flooring at zero rather than going negative.
- **Advancement lives in a form**, encoding one edition's XP economy.
- **No campaign-level running totals** — no cumulative enemies-taken-OOA, no
  battles-fought counter.
- **No end-of-campaign scoring.** `end_campaign()` flips a status field.

**Debt noted in passing:**

- `Campaign` hand-rolls its state transitions instead of using the project's
  `StateMachine` (which `Battle` uses).
- Sub-asset and attribute mutations never reach the campaign log.
- Logging lives in two homes: model methods for resource/asset mutation, inline
  in views for create/remove/clone.
- `ensure_campaign_list_resources` (`views/campaign/common.py:25`) exists as a
  defensive backfill "for race conditions / transaction failures" — the seeding
  path is known not to be reliable.
- `campaign_remove_list` un-assigns held assets one save at a time (N+1).
- `views/campaign/` is 16 modules and ~5,000 lines; `assets.py` (777) and
  `attributes.py` (706) are the heaviest, largely CRUD.
