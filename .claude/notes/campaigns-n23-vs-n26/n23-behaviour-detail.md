# n23 Campaign — Behaviour Layer

What the campaign feature actually *does*, read out of the views and handlers.
(Model fields are assumed known and are not restated.)

---

## 1. Campaign lifecycle behaviour

### 1.1 Start — two phases, one of them async

`start_campaign` (`n23/core/views/campaign/lifecycle.py:28`) is admin-gated
(`get_campaign_admin_or_404`), GET renders a confirmation page listing
`campaign.lists` (note the comment at `lifecycle.py:86`: pre-campaign gangs hang off the
`lists` M2M; the `campaign` FK on `List` is only populated at start, so it must not be
used for the pre-campaign roster — #1886). POST runs `handle_campaign_start` in a
transaction, then `log_event(CAMPAIGN/ACTIVATE)`, `track("campaign_started")`, and a
flash message saying "N gang(s) are joining — they'll be ready in a moment".

**Phase 1 — synchronous** (`n23/core/handlers/campaign_operations.py:57`):

1. Guard: `campaign.can_start_campaign()`; distinct `ValidationError` messages for
   "wrong status" vs "no lists" (`campaign_operations.py:98-106`).
2. Snapshot `campaign.lists.filter(status=LIST_BUILDING)` — **only LIST_BUILDING lists
   are cloned**; anything else in the M2M is silently dropped by the next step.
3. `campaign.lists.clear()` (`:113`) — the pre-campaign roster is wiped and rebuilt from
   clones.
4. Per original list, create a **stub**: a new `List` row in `CLONING_IN_PROGRESS` with
   only cheap scalars copied (name, house, owner, public, narrative, notes, theme_color,
   `credits_current`, `credits_earned`), `original_list` FK set, `campaign` FK set
   (`:144-157`). No fighters, no facts recompute.
   *Idempotency*: an existing CAMPAIGN_MODE or CLONING_IN_PROGRESS clone of the same
   original is re-added rather than duplicated (`:122-139`).
5. Flip `campaign.status = IN_PROGRESS`, save.
6. Write one overall `CampaignAction`: "Campaign Started: … / N gang(s) joined the
   campaign".
7. `transaction.on_commit` → enqueue one `complete_campaign_list_clone` task per stub,
   into task group `campaign-start:{campaign_id}` (`campaign_start_group_key`, `:19`).
   Enqueue failures are swallowed (`:194-205`) — the stub just stays CLONING_IN_PROGRESS.

**Phase 2 — background, one task per stub** (`n23/core/tasks.py:19`), all inside one
transaction under `SELECT FOR UPDATE` on the stub, returning early unless the stub is
still `CLONING_IN_PROGRESS` (so redelivery/retry is a clean no-op):

1. `stub._populate_clone_from(original)` — fighters, equipment, stash, facts.
2. `book_clone_actions(...)` — CLONE action on the original, CREATE action on the stub
   (run *after* populate so the CREATE deltas see recomputed caches).
3. `_distribute_budget_to_list(...)` priced off **`original.cost_int()`**.
4. Allocate default resources: `get_or_create` a `CampaignListResource` per
   `campaign.resource_types` at `resource_type.default_amount`, owned by
   `campaign.owner` (`tasks.py:96-105`).
5. `stub.status = CAMPAIGN_MODE`.

Missing referenced objects (original/campaign/user deleted) → log and give up, stub left
stuck (`tasks.py:70-77`).

**Budget rule** (`campaign_operations.py:217`): `credits_to_add = max(0, campaign.budget
- list_cost)` where list cost is rating + stash excluding credits. Zero budget, or a gang
already at/over budget, gets nothing (and no action rows). Otherwise it books a
`ListAction` of type `CAMPAIGN_START` with `credits_delta`, then explicitly calls
`campaign_list.apply_credit_delta(...)` (`create_action` is a pure record), then a
`CampaignAction` for visibility: "Campaign starting budget: Received X¢ (B¢ budget - C¢
gang rating)".

**Stuck-gang retry**: `retry_campaign_list_clone` (`lifecycle.py:99`) — POST-only, admin
only, re-enqueues into the same group. Refuses if the stub isn't `is_cloning` or has no
`original_list`. The campaign page polls the generic `/tasks/status` endpoint on that
group key.

### 1.2 End / reopen / archive

All three are `get_campaign_admin_or_404` + confirmation-page-on-GET, and all delegate
the actual transition to a model method (`end_campaign()` / `reopen_campaign()` /
`archive()`), then write a `CampaignAction` describing the transition and a `log_event`.

- `end_campaign` (`lifecycle.py:159`): no side effects on member gangs at all — no
  un-cloning, no archiving, no credit reconciliation. Lists stay in CAMPAIGN_MODE
  attached to a post-campaign campaign.
- `reopen_campaign` (`lifecycle.py:219`): post-campaign → in-progress, likewise inert.
- `archive_campaign` (`lifecycle.py:279`): refuses while `campaign.is_in_progress`
  ("Please end the campaign first"). Archived state is then checked as a hard guard by
  nearly every mutating campaign view.

### 1.3 Joining and leaving

`campaign_add_lists` (`views/campaign/lists.py:29`) is the join surface and carries a lot
of rules:

- Blocked entirely once post-campaign.
- Candidate lists: user's own **or** public, `status=LIST_BUILDING`, not archived.
  A list already in CAMPAIGN_MODE is explicitly rejected ("cannot be added to other
  campaigns", `:69`).
- **Pack compatibility gate**: `campaign.validate_list_packs(list)`; if the gang carries
  packs the campaign doesn't have, the view shows an inline confirmation to add those
  packs to the campaign. Archived packs, and unlisted packs not owned by the requester,
  are hard-blocked (`:81-92`).
- Membership goes through `CampaignInvitation`: `get_or_create`, auto-accepted when
  `campaign.owner == list.owner` (`:117`), otherwise an invitation is sent. Declined
  invitations are reset to PENDING on re-invite. There's a lot of branchy
  already-invited / already-accepted / list-was-removed message handling (`:190-219`).
- Availability list excludes pending invitations; once started it excludes lists whose
  clone is already in the campaign (via `original_list_id`), pre-campaign it excludes
  direct members. Search over name/house/owner, `owner=mine|others|all` filter, and a
  `packs=matching` filter, paginated 20/page.

`campaign_remove_list` (`lists.py:349`): campaign admin **or** the list owner. Refuses
post-campaign, refuses a list not in the campaign, and refuses a `is_cloning` stub
(#1222, would orphan a half-built clone). On POST it un-assigns every `CampaignAsset`
held by the list (holder → None, one save each — N+1), writes a `CampaignAction`, removes
from the M2M, and **if the list is CAMPAIGN_MODE it archives it and nulls its `campaign`
FK** (`:428-432`). Resources, attribute assignments and action history are left behind.

`campaign_set_default_gang_sort` (`lists.py:470`): admin-only, stores a validated sort
token (`parse_gang_sort`) including `-resource:<uuid>` forms; readers can always override
with `?sort=`.

---

## 2. The generic primitives in practice

The four primitives (resources, assets, sub-assets, attributes) share a shape:
**admin defines the type, then per-gang instances are mutated by admin-or-gang-owner**.
They differ in how consistently that's enforced and in whether mutations reach the
campaign log.

### 2.1 Resources (`views/campaign/resources.py`)

- `campaign_resources` (`:36`): view page, any logged-in user, computes `is_admin` and
  the viewer's own lists for the template.
- Type CRUD (`:88`, `:178`, `:234`): `get_campaign_admin_or_404`. New/remove refuse on
  archived campaigns (edit does **not** — inconsistency). Creating a type while the
  campaign is in progress back-fills `CampaignListResource` rows for
  `campaign.active_lists()` via `ensure_campaign_list_resources` (CLONING stubs are
  skipped deliberately; they get theirs in Phase 2). Removing a type cascades to all
  list resources with only a count logged.
- `campaign_resource_modify` (`:303`): **admin or the holding list's owner** (`:326`).
  Guards: not archived, not pre-campaign. The actual change is
  `resource.modify_amount(delta, user=...)` on the model, which enforces non-negative and
  writes the `CampaignAction`; the view only handles `ValueError` → message.
- `MAX_CREDITS = 10000` is declared at `resources.py:30` and **never used** — dead
  constant.
- `ensure_campaign_list_resources` (`views/campaign/common.py:25`) is a defensive
  bulk backfill "for race conditions / transaction failures" — i.e. the seeding path is
  known not to be reliable.

### 2.2 Assets (`views/campaign/assets.py`)

- `campaign_assets` (`:33`) and `campaign_asset_detail` (`:91`) are open to any logged-in
  user; the detail page groups sub-assets by the parent type's `sub_asset_schema`, and
  deliberately renders orphan groups (types dropped from the schema) last rather than
  hiding persisted rows (`:142-146`).
- Type + asset create/edit/remove/clone: admin only, all with an archived-campaign guard.
- `campaign_asset_clone` (`:502`): copies description, deep-copied `properties` and all
  sub-assets; **never copies the holder** — a clone starts unowned. Duplicate names
  allowed (#2075). Writes a `CampaignAction` only `if campaign.is_in_progress` (`:563`).
- `campaign_asset_transfer` (`:615`): **admin or the current holder's owner** (`:636`) —
  note this means a gang can give an asset away but a gang that doesn't hold it can't
  take it. Guards: not archived, not pre-campaign. Delegates to
  `asset.transfer_to(new_holder, user=...)`, which writes the CampaignAction.
- `campaign_asset_remove` (`:706`): admin only, deletes outright, logs a CampaignAction
  only when in progress.

### 2.3 Sub-assets (`views/campaign/sub_assets.py`)

Admin-only throughout (`get_campaign_admin_or_404` on all three views) — gang owners
cannot touch sub-assets of an asset they hold. The `sub_asset_type` comes in as a URL
segment and is validated against the parent asset type's `sub_asset_schema` keys
(`:50-55`); labels for messages are pulled from that schema. Mutations are recorded via
`log_event`/`track` **only — no `CampaignAction`**, so sub-asset changes are invisible in
the campaign log.

### 2.4 Attributes (`views/campaign/attributes.py`)

- `campaign_attributes` (`:33`): open to any logged-in user; builds an
  `assignment_lookup` dict `{type_id: {list_id: [assignment,…]}}` in Python and passes
  `single_select_attribute_types` for the "group gangs by" dropdown.
- Type and value CRUD: admin only, archived guard.
- `campaign_set_group_attribute` (`:533`): admin only; validates the posted id parses as
  a UUID, belongs to the campaign, and `is_single_select` before setting
  `campaign.group_attribute_type`. Empty string clears it.
- `campaign_list_attribute_assign` (`:615`): **list owner or campaign admin** (`:640`).
  The form does the work (`form.save(user=...)`), including single- vs multi-select
  enforcement; `ValidationError` surfaces as a message. Archived guard, but **no
  pre-campaign guard** — attributes are assignable before start, unlike resources/assets.
  Assignment changes produce `log_event` only — again **no `CampaignAction`**.

### 2.5 Cross-cutting observations

- Only three of the four primitives write to the campaign log, and asset/resource logging
  is done inside model methods (`modify_amount`, `transfer_to`) while
  create/remove/clone logging is done inline in views — two different homes for the same
  concern.
- `is_pre_campaign` blocks resource modification and asset transfer, but not attribute
  assignment or any type-level CRUD.
- `campaign.archived` is re-checked ad hoc in ~12 places with hand-written messages; a
  couple of edit views miss it.

---

## 3. Battles & post-battle

The battle views are **not** in `views/campaign/battles.py` — that file is a single
read-only listing view (`campaign_battles`, `views/campaign/battles.py:8`; `?archived=1`
toggles archived). Everything else lives in `n23/core/views/battle.py` (753 lines),
`n23/core/handlers/battle.py`, `n23/core/handlers/crew.py` (1234 lines) and the
post-battle editor at `n23/core/views/list/post_battle.py`.

### 3.1 The flow

`battle_timeline` (`handlers/battle.py:371`) is the canonical statement of the intended
process, and is worth quoting as the shape of the feature:

1. Gangs join the battle (participants + optional roles)
2. Each gang picks a crew
3. Gangs mark themselves ready ("a gang can only say ready once it can cover its crew's
   spending")
4. The battle starts — spending is charged, crew membership frozen
5. Play the battle (print fighter cards from the crew page)
6. Record the result (who won, or a draw)
7. Post-battle updates — "XP, injuries, captures and credits, recorded by each gang"

Step 7 is hardcoded `"done": False` (`:427`) — the app has no idea whether post-battle
updates were actually done, so the timeline always ends "you are here".

State machine: `PRE_BATTLE → IN_PROGRESS → POST_BATTLE`, driven through
`battle.states.transition_to(...)`, with `_transition_battle` (`views/battle.py:445`) as
a generic log+flash wrapper.

### 3.2 Create / edit

`new_battle` (`views/battle.py:295`): allowed for a campaign admin **or any player with a
gang in the campaign** (`:301-303`); campaign must be `is_in_progress`. Saves the battle,
`set_participants(...)`, writes a `CampaignAction` ("Battle created: <mission> on <date>.
Gangs: …") deliberately phrased so it can't claim a result, and calls
`notify_battle_participants`.

`notify_battle_participants` (`handlers/battle.py:129`): one notification **per owner**,
not per gang; never notifies the acting user about their own action; uses
`NotificationType.LIST` (framed as "something changed on your gang"), links to the battle,
and goes through the safe `notify()` so a failure can't break battle creation.

`edit_battle` (`:380`): gated by `battle.can_edit`; sets `result` and `winners` directly,
bypassing `handle_battle_end` — so the end-of-battle invariants
(winner-must-be-participant, no second result) do **not** apply on this path. Only
newly-added participants are notified.

`edit_battle_roles` (`:599`) and `archive_battle` (`:642`) are ordinary CRUD; archiving
hides the battle and blocks further edits.

### 3.3 Starting a battle — credits actually move

`start_battle` (`views/battle.py:469`, `can_manage`): the transition and the charge are
one atomic block, transition first so an invalid state returns before any credits move
(`:477-492`). The confirmation page shows `battle_start_crew_rows` (owed / will pay /
unpaid per crew) and `battle_not_ready_gangs` (gangs with no crew *or* an unready crew).

`charge_crew_spending` (`handlers/battle.py:241`) is the substantive bit:

- Scoped to `live_battle_crews` — crews whose gang is *still* a participant
  (`set_participants` deletes participant rows but leaves crews behind, `:210-223`; the
  docstring records that doing this inline at each call site once charged a dropped gang).
- `SELECT FOR UPDATE`, filtered on `credits_charged_at__isnull=True`, so a retried
  transition never double-charges.
- **Only the Spending column is charged**: balancing allowances are granted to the
  underdog rather than paid for, and free extras cost nobody anything.
- A gang that can't cover its spending is charged what it has and **floored at zero** —
  never taken negative. The shortfall surfaces via `Crew.credits_shortfall` and a warning
  message; ledger and crew sheet are allowed to disagree.
- Every charge is paired with a `ListAction` (`UPDATE_CREDITS`) *before*
  `apply_credit_delta`, because `cost/balance_sheet.py` asserts the credits chain
  (`:280-296`) — an unpaired delta permanently breaks the audit chain for that gang.
- Writes a per-gang `CampaignAction` ("X¢ charged of Y¢ — Z¢ unpaid").

### 3.4 Ending a battle

`end_battle` (`views/battle.py:532`, `can_manage`) → `handle_battle_end`
(`handlers/battle.py:44`), atomic, `SELECT FOR UPDATE` on the battle:

- `can_end()` guard under the lock, so concurrent ends serialise and the second fails
  cleanly.
- Draw ⇒ empty winners; non-draw with no winners raises; every winner must be a current
  participant (re-checked under the lock).
- `result` is saved **before** the transition, because `transition_to()` saves with
  `update_fields=["status","modified"]` and would drop it (`:78-81`).
- `snapshot_played_crew_ratings` freezes what each crew fielded, before the transition —
  "from here on a crew reports what fought rather than what the gang looks like today".
- Writes a battle-linked `CampaignAction` with a neutral description and the concrete
  outcome ("Draw" / "Winners: A, B").

**Ending a battle does not touch any gang.** No XP, no credits, no injuries. All of that
lives in the post-battle editor, which is entirely optional and manual.

### 3.5 The post-battle editor

`post_battle_updates` (`n23/core/views/list/post_battle.py:388`), URL
`list/<id>/post-battle` (`n23/core/urls/list.py:41`). It is **per-gang, not per-battle**:
the battle is an optional FK chosen from a dropdown of non-archived battles the gang
fought in (`_selectable_battles`, `:122`), used only to tag the resulting actions.
`?battle=<uuid>` preselects it (UUID-validated, ignored if the gang didn't fight in it).

Permission: `get_list_for_edit` (list owner or campaign arbitrator); campaign mode only.
The battle detail page shows a "record post-battle" affordance per gang, gated on the
gang being campaign-mode, unarchived, and owned by the user or the user being a campaign
admin (`views/battle.py:250-256`).

Roster shown: all non-stash, non-archived fighters **including vehicles, crew and dead
fighters** (`_post_battle_fighters`, `:110`).

One `transaction.atomic` block (`_apply`, `:168`) applies only the filled-in fields, gang
gains first, then per fighter:

| Field | Effect |
|---|---|
| `credits_gained` | `handle_credits_modification(operation="add", description="Post-battle winnings", battle=…)` |
| `resource_<pk>` | `resource.modify_amount(delta, user, battle)`; a `ValueError` (a concurrent change pushing it below zero) is re-raised as `_ResourceApplyError`, rolling the **whole** submit back and re-rendering with a field error (`:100-107`, `:437-441`) |
| `assets_captured` | `asset.transfer_to(lst, …)`, de-duplicated with `dict.fromkeys` |
| `xp_<pk>` | `handle_fighter_add_xp` — bumps `xp_current` and `xp_total`, writes a CampaignAction |
| `counter_<pk>_<counter pk>` | `handle_fighter_adjust_counter` |
| `injury_<pk>` (repeated select, multiple allowed) | `handle_fighter_add_injury` — creates the `ListFighterInjury` and applies the injury's `phase` as the default outcome; a `DEAD` phase routes through `handle_fighter_kill` |
| `state_<pk>` | applied **after** injuries so an explicit choice beats the injury's default — unless the fighter just died. `DEAD` routes through `handle_fighter_kill` (equipment → stash, cost 0, rating propagation); anything else sets `injury_state` and writes a CampaignAction |
| `captured_by_<pk>` | `handle_fighter_capture` — **skipped if the fighter died in the same submit**, and reported as skipped in the flash message |

Precedence rules are explicit and interlocking: fatal injury > further injuries (breaks
the loop), fatal injury > explicit state, death > capture. The flash message is assembled
by `_ApplySummary` and includes "… died — any equipment they carried was returned to the
gang's stash."

Handlers stay HTTP-free; the view owns every `log_event`. `handle_fighter_add_injury`
guards `lst.is_campaign_mode` itself (`handlers/fighter/injury.py:77`).

### 3.6 Captured fighters

`views/campaign/captured.py` — three terminal outcomes for a `CapturedFighter`, all
scoped to `sold_to_guilders=False`:

- `fighter_sell_to_guilders` (`:95`) — capturing-list owner or campaign admin; a free-text
  credits amount clamped to `0..MAX_CREDITS (10000)`, parsed by hand from `request.POST`
  (no form).
- `fighter_return_to_owner` (`:192`) — capturing owner, campaign admin, **or the captive's
  original owner**; ransom clamped to `0..MAX_RANSOM_CREDITS (10000)`, likewise hand-parsed.
- `fighter_release` (`:304`) — same three-way permission, no credits.

The listing (`:30`) is visible to campaign admins and anyone owning a list in the
campaign, and unions "fighters my gangs captured" with "fighters captured from my gangs"
(`:60-63`).

### 3.7 The action log and dice

`campaign_log_action` (`views/campaign/actions.py:25`): campaign must be in progress and
unarchived, and the user must be an admin or own a list in it. After creating the action
it redirects to `campaign_action_outcome` to fill in the result — a deliberate two-step
(declare, then record what happened), with a "save and new" button that loops back.
**Only the action's creator may edit its outcome** (`:140`) — not even the arbitrator, and
the failure mode is a bare redirect with no message.

`CampaignActionList` (`:194`) paginates 50/page with search over
description/outcome/username plus gang, author, battle and timeframe (24h/7d/30d) filters.

Dice: `CampaignActionForm` takes `dice_count` ("Number of D6 Dice",
`forms/campaign.py:68`) and the model rolls on save. The standalone roller
(`views/dice.py`) is URL-driven and deterministic: the roll derives from a `seed` in the
query string, so a URL reproduces the roll and can be shared; with no seed it renders "?"
placeholders and rolls nothing. Counts are clamped (`MAX_GROUPS = 20`,
`MAX_DICE_PER_GROUP = 100`) because the config is untrusted, hand-editable URL input.

---

## 3b. The remaining modules, briefly

**`crud.py`** — `new_campaign` (`:63`) accepts `?template=<id>`; on save it runs
`apply_campaign_template(...)` (assets, resources, attributes, packs) and then
`ensure_default_resource_type(...)`, which gives **every campaign a "Reputation" resource
type** unless the template already supplied one (`:106-108`). A missing/invalid template
is a soft failure: it errors, copies nothing, and lets the user create the campaign as it
stands (`:87-93`). `edit_campaign` (`:166`) is admin-gated.

**`copy.py`** — `campaign_copy_from` / `campaign_copy_to`, admin-only, target must not be
archived. Sources are limited to campaigns the user owns plus `template=True` campaigns
(`:59-67`). Two-step: `action=preview` runs `check_copy_conflicts`, `action=confirm`
re-fetches the source (re-checking `archived` for the race), reads the tick-box selections
out of hidden fields and calls `copy_campaign_content(asset_type_ids, resource_type_ids,
attribute_type_ids, pack_ids)`. Copies **definitions and assets, not per-gang state** —
no `CampaignListResource` amounts, no attribute assignments.

**`packs.py`** — visible to campaign admins and members only (`:45-48`). Add/remove
blocked on archived and post-campaign campaigns; an unlisted pack can only be added by its
owner (`:141`). `campaign_pack_set_required` (`:181`) takes a `SELECT FOR UPDATE` on the
`CampaignContentPack` through-row and refuses to flip a pack to required while any gang in
the campaign isn't subscribed, naming the non-compliant gangs — `unsubscribe_pack` takes
the same lock, so the two serialise.

**`arbitrators.py`** — any campaign admin may grant admin to another user by username, or
revoke, *including revoking themselves* (after which they're redirected away since they
can no longer see the page, `:128`). Each change is a grant + `CampaignAction` in one
transaction ("a trust-boundary change: the grant and its audit record must land
together", `:47`). The owner is excluded defensively from `admins` in both directions and
can never be removed.

**`gang_sort.py`** — pure, query-free sort vocabulary shared by `?sort=` and
`Campaign.default_gang_sort`: `name | rating | credits | stash | wealth` plus
`resource:<uuid>`, `-` prefix for descending, default `-wealth`. Sorting happens in Python
over already-prefetched lists and the view's `resource_lookup`.

**`views.py`** (`CampaignDetailView`, `:129`) — the dashboard. Detects "gangs still
joining" (`has_cloning_lists`) and hands the template a `cloning_status_url` pointing at
the generic task-group status endpoint keyed by `campaign_start_group_key` (`:176-188`).
Builds `resource_lookup` `{list_id: {resource_type_id: resource}}`, resolves the gang sort
(viewer's `?sort=` wins, then the campaign default), and optionally groups gangs by
`campaign.group_attribute_type` (`?group=0` switches grouping off so the sort runs across
every gang).

---

## 4. Permissions

Four distinct predicates are in play, and which one applies is decided per view rather
than by any shared policy layer.

1. **Campaign admin** — `campaign.is_admin(user)` (owner OR `admins` M2M, memoised,
   `models/campaign.py:206`), reached in views either directly or via
   `get_campaign_admin_or_404` (`views/campaign/common.py:9`, which 404s rather than
   403s). Used for: all type-level CRUD (asset types, resource types, attribute types),
   asset create/edit/clone/remove, **all** sub-asset CRUD, campaign start/end/reopen/
   archive, clone retry, arbitrator management, pack management, copy, campaign edit,
   default gang sort, group attribute.
2. **Campaign admin *or* the relevant gang owner** — used for resource modification
   (`resources.py:326`), attribute assignment (`attributes.py:640`), list removal
   (`lists.py:371`), and asset transfer, where "relevant gang owner" means the *current
   holder's* owner (`assets.py:636`) — so an asset can be given away but not taken.
3. **Campaign participant** (`campaign.lists.filter(owner=user).exists()`) — creating
   battles (`views/battle.py:302`), logging campaign actions (`actions.py:47`), viewing
   packs and captured fighters, pinning the campaign.
4. **Per-object predicates on Battle** (`models/battle.py:149-193`), each of which
   short-circuits on `self.archived or self.campaign.archived`:
   - `can_edit` — battle owner or campaign admin. Edit details, winners, archive.
   - `can_manage` — battle owner, campaign admin, **or any owner of a participating
     gang**. Start, end, assign roles. So any player in the battle can end it and declare
     the winner.
   - `can_unarchive` — battle owner or campaign admin.
   - `BattleNote.can_edit` — note owner only.

Plus three one-offs:

- **Post-battle editor**: `get_list_for_edit` (`views/fighter/permissions.py:41`) with the
  default `{OWNER, ARBITRATOR}` — filtered in the queryset, so a failure is a 404.
- **Captured fighters**: capturing-list owner OR campaign admin OR (for return/release,
  not for sale) the captive's original owner (`captured.py:219-224`, `:332-337`).
- **Campaign action outcome**: `action.user != request.user` → silent redirect
  (`actions.py:140`). The creator only; arbitrators cannot correct someone else's entry.

Inconsistencies worth noting: read pages are mostly `@login_required` with no membership
check (`campaign_assets`, `campaign_attributes`, `campaign_resources`, `campaign_asset_detail`),
but `campaign_packs` and `campaign_captured_fighters` do gate on membership.
Failure modes are also mixed — 404 (`get_campaign_admin_or_404`, `get_list_for_edit`),
bare `raise Http404()` (captured), and `messages.error` + redirect (most of the rest).

---

## 5. n23-rules-specific things baked into views / handlers / forms

Most of the campaign machinery is genuinely generic — assets, resources, attributes and
sub-assets are all user-defined types with user-defined names and JSON property schemas.
The n23 specifics that *are* hardcoded:

- **"Reputation" is created for every campaign.** `DEFAULT_RESOURCE_TYPE_NAME =
  "Reputation"` / `"Gang reputation gained during the campaign"`
  (`handlers/campaign_copy.py:302-303`), applied by `ensure_default_resource_type` from
  `new_campaign` (`crud.py:106-108`). The only game-concept noun the system creates on its
  own.
- **Credits are the currency, spelled `¢`,** in `List.credits_current` /
  `credits_earned`, in every flash and CampaignAction string (`"Campaign starting budget:
  Received {n}¢ …"`, `campaign_operations.py:260`; `"{charged}¢ charged"`,
  `handlers/battle.py:307`). Not a configurable resource — a separate first-class column.
- **The budget formula is a gang-rating formula**: `max(0, campaign.budget -
  list_cost)` where list cost is rating + stash, described in the log line as "budget -
  gang rating" (`campaign_operations.py:249`, `:260`).
- **Gang metrics are a fixed vocabulary**: `rating | credits | stash | wealth`
  (`gang_sort.py:26-33`), with fixed one-letter headers "R Cr St W".
- **Dice are D6.** `dice_count` is labelled "Number of D6 Dice" / "How many D6 dice to
  roll" (`forms/campaign.py:68`, `:74`); the standalone roller's modes are `d6`/`d3` plus
  named `fp` (firepower) and `i` (injury) dice groups (`views/dice.py`).
- **Guilders.** Selling a captive is `fighter_sell_to_guilders` — a URL name, view name,
  handler name, template name and a boolean model field `sold_to_guilders`
  (`captured.py:95`). The alternatives (ransom, release) are equally n23-shaped.
- **Fighter states are a fixed enum**: `ListFighter.INJURY_STATE_CHOICES` with `DEAD`
  special-cased in the post-battle editor and in `handle_fighter_add_injury`
  (`ContentInjuryDefaultOutcome.DEAD` → `handle_fighter_kill`).
- **XP is one scalar pair** (`xp_current` / `xp_total`), advanced by a plain integer
  (`handlers/fighter/xp.py:61-63`).
- **Capture is between two gangs in the same campaign** and terminal in exactly three
  ways (sold / ransomed / released), each hardcoded as a view.
- Form help text carries n23 examples: `"e.g., 'Territory'"` / `"'Territories'"`
  (`forms/campaign.py:311-312`), `"e.g., 'Meat', 'Credits', 'Ammo'"` (`:699`).
- The battle timeline's step text is n23-flavoured ("Use each crew page to print fighter
  cards", `handlers/battle.py:417`).

---

## 6. Weaknesses / debt

No `TODO`/`FIXME` markers survive anywhere in `views/campaign/`, `handlers/battle.py`,
`handlers/campaign_operations.py` or the post-battle editor — the debt is structural, not
annotated.

**Guards are copy-pasted, not policy.** `campaign.archived`, `is_pre_campaign`,
`is_post_campaign` and the permission predicates are re-implemented inline in every view
with hand-written messages. The result is drift: `campaign_resource_type_edit`
(`resources.py:178`) and `campaign_asset_type_edit` have no archived guard while their
new/remove siblings do; attribute assignment has no pre-campaign guard while resource
modification and asset transfer do; read views are inconsistently gated on membership.
A differently-shaped campaign system would have to re-derive the intended matrix from
~40 call sites.

**Logging is split three ways with no invariant.** `CampaignAction` (the in-app log),
`log_event` (analytics), and `track` (product metrics) are each written by hand, at
different layers — some inside model methods (`modify_amount`, `transfer_to`), some in
handlers (`handle_fighter_add_xp`), some in views. Consequences: **sub-asset changes and
attribute assignments never reach the campaign log at all**; asset clone/remove log only
`if campaign.is_in_progress` while asset transfer logs unconditionally.

**Two doors to the same state change.** `edit_battle` (`views/battle.py:396-406`) sets
`result` and `winners` directly, bypassing `handle_battle_end` and therefore its
winner-must-be-a-participant check, its no-second-result guard, and
`snapshot_played_crew_ratings`. Similarly `handle_fighter_add_xp` exists specifically for
the post-battle editor, while "the single-fighter XP view still adds XP inline and could
adopt this handler later" (`handlers/fighter/xp.py:3-5`) — two implementations of the same
rule.

**Campaign start's failure surface.** Phase 1 wipes `campaign.lists` and rebuilds from
stubs, but the enqueue is fire-and-forget: a publish failure leaves a gang permanently
"joining" with only a manual retry button to rescue it (`campaign_operations.py:194-205`).
Phase 2 gives up silently if the original list, campaign or user has been deleted
(`tasks.py:70-77`). `ensure_campaign_list_resources` exists as a defensive backfill "for
race conditions, transaction failures, or other issues" (`common.py:26-34`) — the seeding
path is known to be unreliable.

**End of campaign does nothing.** `end_campaign` writes a log line and flips a status.
Gangs stay in CAMPAIGN_MODE, assets stay held, resources stay allocated, and nothing is
reconciled or returned. `reopen_campaign` is equally inert. Whatever "the campaign is
over" ought to mean is left entirely to the players.

**The post-battle editor is per-gang and unlinked from the battle.** Nothing requires it
to be used, nothing knows whether it was — `battle_timeline`'s final step is hardcoded
`"done": False` (`handlers/battle.py:427`). Each gang records its own results
independently, so a capture is entered by the *losing* gang naming the capturing gang, and
there is no cross-gang consistency check. `_apply`'s precedence rules (death beats
capture, injury beats explicit state) exist because the flat grid makes contradictory
input easy to enter.

**Ledger and sheet may legitimately disagree.** `charge_crew_spending` floors at zero and
leaves the shortfall visible only through `Crew.credits_shortfall` and a flash
(`handlers/battle.py:246-252`). Deliberate, but it means "what the crew fielded" and "what
the gang paid" are not reconcilable from the data alone.

**Hand-parsed money.** Both captured-fighter money paths read `request.POST.get(...)` and
`int()` it by hand with a 10,000 ceiling instead of using a form (`captured.py:133-148`,
`:231-246`). `MAX_CREDITS` is also declared in `resources.py:30` and never used, and
`captured.py` declares `MAX_CREDITS` and `MAX_RANSOM_CREDITS` with the same value.

**N+1s and count-in-loop.** `campaign_remove_list` un-assigns assets one `save()` at a
time (`lists.py:407-412`); `campaign_resource_type_new` calls `campaign.lists.count()`
inside the `log_event` kwargs (`resources.py:144`); `campaign_asset_clone` re-queries
`asset.sub_assets.count()` for the GET context after already listing them.

**`campaign_add_lists` is one 300-line view** carrying pack validation, an inline
confirmation flow, invitation state reconciliation, search, three filters and pagination
(`lists.py:29-344`), with deeply nested branching. It is the single hardest thing here to
re-shape.

**Not a problem, just surprising**: `views/list/post_battle.py:457` and `views/dice.py:33`
use PEP 758 unparenthesised `except ValueError, TypeError:`. Valid — `requires-python =
">=3.14"` — but it reads as a Python 2 relic and will confuse anyone skimming.

Also worth flagging for a re-shape: `campaign_asset_type_edit` (`assets.py:242`) and
`campaign_asset_edit` (`:446`) are the two asset views with no `campaign.archived` guard,
while every sibling has one.
