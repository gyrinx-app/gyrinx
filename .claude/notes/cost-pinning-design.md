# Equipment Cost Pinning — Design (Issue #1826 programme)

A design for making equipment cost resolution answer "what did this cost when it was
acquired?" instead of "what would this cost if the current holder bought it now?" —
while keeping the cache-first cost architecture intact. The mechanism: every priced
component carries a **pin**, which is an attribution FK, a cached amount, and an
explicit pin state (§4.1).

> **Anchor note:** file references were verified against the tree at design time;
> the `gyrinx/core/models/list.py` monolith has since been split into the
> `gyrinx/core/models/list/` package (`list.py`, `fighter.py`, `assignment.py`,
> `virtual.py`), so `models/list.py:NNNN` anchors identify the code but not its
> current line. Verify against the package before citing.

---

## 1. Problem statement

### 1.1 How equipment is priced today

A gang (`List`) carries three cached money figures — `rating_current`,
`stash_current`, `credits_current` — and every fighter and equipment assignment
carries its own cached `rating_current`. Pages read these caches; they never recompute
costs at render time. When something changes, a handler computes a **delta** and
propagates it up the chain (assignment → fighter → list) via
`propagate_from_assignment` (`gyrinx/core/cost/propagation.py`). A full recompute
(`facts_from_db`, or the admin "recompute cost caches" action at
`gyrinx/core/admin/list.py:180`) exists as a repair path and is expected to agree with
the accumulated cache.

An assignment's recomputed cost (`ListFighterEquipmentAssignment.cost_int()`,
`gyrinx/core/models/list.py:4494-4497`) is the sum of four **components** — base
equipment, weapon profiles, weapon accessories, upgrades — unless the user has set
`total_cost_override`, in which case `cost_int()` returns the override unconditionally
and never sums components.

Each component is resolved **live against the current holder**: the base cost checks
the holding fighter's fighter-type equipment list
(`ContentFighterEquipmentListItem`), then equipment-list expansions
(`ContentEquipmentListExpansionItem`), then the catalog price
(`ContentEquipment.cost`); profiles, accessories, and upgrades have analogous
holder-dependent override chains.

### 1.2 The bugs this creates

**Re-pricing on movement.** Because resolution keys off the *current* holder, moving
gear changes its price. A fighter dies and their gear transfers to the gang stash —
the stash fighter has no equipment list, so gear bought at a house-discounted price
silently re-resolves to the catalog price. Reassigning gear between fighters with
different equipment-list overrides does the same. To the user: **gang wealth changes
for no reason on a fighter's death**, and the stash badge disagrees with what the
stash visibly contains.

**Cache-vs-recompute divergence (the drift class).** Any mechanism that makes
`cost_int()` disagree with the delta-accumulated cache is invisible until the next
recompute snaps the cache to a different number — no error, just wealth jumping.
Seven producers of this class existed when the harness landed; two (the
pack-sweep gap and the bare-form endpoint) were fixed in the pack-axis PR,
leaving five live:

- **#1925 — component purchase under `total_cost_override`.** Buy an accessory on an
  assignment that has the override set. The handler computes the accessory's live
  cost (`gyrinx/core/handlers/equipment/purchase.py:204`) and propagates it into the
  caches (`purchase.py:237` → `propagation.py:95-97`), but `cost_int()`
  short-circuits to the override and ignores components entirely. Cache says
  `override + accessory`; recompute says `override`. The next sweep or admin
  recompute discards the cost of an accessory the user paid credits for.
- **Sales price at catalog, not at what the caches hold.** The sale view prices every
  line from raw content — `assignment.content_equipment.cost_int()` at
  `gyrinx/core/views/fighter/equipment.py:1772`, raw `profile.cost` and
  `accessory.cost` at `:1789-1815` — and `handle_equipment_sale` propagates those
  totals as the stash delta (`gyrinx/core/handlers/equipment/sale.py:122`) before
  deleting the assignment. Whenever the cached value differs from catalog (discounted
  gear, kill-frozen gear), each sale subtracts the wrong number and the stash cache
  drifts permanently.
- **Stash component removal never decrements the assignment chain.**
  `handle_equipment_component_removal` computes `rating_delta = 0` for stash fighters
  (the value rides `stash_delta` instead,
  `gyrinx/core/handlers/equipment/removal.py:233`), then propagates
  `Delta(delta=rating_delta)` — zero — into the assignment/fighter caches
  (`removal.py:265`). The list-level stash figure moves via the ListAction, but the
  stash fighter's and assignment's caches keep the removed component's value until a
  recompute snaps them apart.
- **Death-transfer re-pricing (#1826 itself).** `handle_fighter_kill` values the
  dying fighter's gear in *that fighter's* pricing context
  (`gyrinx/core/handlers/fighter/kill.py:122`) and propagates that sum into the
  stash fighter's cache (`kill.py:174`) and the list's `stash_delta`. The new stash
  assignment then recomputes in the *stash's* context (no equipment list), so
  context-priced gear re-prices at catalog on the next recompute while the caches
  hold the dying-fighter value. This is the original reported bug, still live.
- **Reassignment prices the move in the old context.** `handle_equipment_reassignment`
  computes `cost_before` and `cost_after` on the *same Python instance*
  (`gyrinx/core/handlers/equipment/reassignment.py:80-96`); the component cost
  `cached_property`s populate at the first call and never invalidate, so
  `cost_after == cost_before` always. Context-priced gear moves at the old holder's
  price; the next recompute re-prices it to the new holder's context and the caches
  jump. (The `equipment_cost_changed_on_reassignment` telemetry can never fire.)
- **Pack-scoped price corrections never sweep (#1930) — FIXED (pack-axis PR).**
  `get_old_cost()` (`gyrinx/content/signals.py`) read the pre-save price through
  the pack-excluding default manager; a pack row raised `DoesNotExist` and every
  cost-change signal treated the save as a new instance — nothing dirtied, no
  audit action, no campaign credits. Fixed by mirroring the task's
  `all_content()` fallback. Found by the pack axis (§5.2).
- **The accessories-edit bare-form fallback — FIXED (pack-axis PR, deleted).**
  The weapon-accessories edit view carried a fallback POST branch that rewrote
  `weapon_accessories_field` wholesale via `form.save()` with no delta
  propagation, no ListAction, and no credits movement. UI-dead but endpoint-live;
  it also could not remove pack accessories at all (the M2M rewrite listed
  current rows through the default manager). A bare POST now falls through to
  the page render; a both-sides matrix cell pins the inert behaviour.

A note on the **admin** as a mutation surface: the assignment admin's change form
writes all three component M2Ms with no delta propagation either. That is *policy*,
not a bug: admin writes bypass delta propagation by design, are remediated by the
existing "recompute cost caches" admin action, and are explicitly allowlisted in the
acquisition-path CI guard (§4.6). The producers above are user-facing flows and
are bugs; the five still live are owned by Phases 2/3/9.

**Why whole-total freezing cannot be the fix.** The obvious wealth-stability
mechanism — freeze the assignment's *total* at transfer time — is unsound for exactly
the #1925 reason: with `total_cost_override` set, every subsequent per-component
purchase/removal handler is wrong for that assignment, forever, until the override is
cleared. (A death-transfer freeze along these lines was prototyped and rejected
for exactly this reason; nothing of it ships in production — `kill.py` today still
has the raw re-pricing bug above, and no system-written kill-frozen override rows
exist in production data. The only `total_cost_override` rows out there are
user-set.) Per-component pinning is the only way re-equipped stash gear remains
purchasable/removable without corrupting the caches.

### 1.3 Product intent

> **Equipment costs what it cost at acquisition, throughout its lifecycle — except
> when the underlying content price is corrected, in which case the correction
> propagates to every holder.**

The design achieves this by giving every priced component a **pin**: an attribution
FK naming the content row that set the price, a cached amount recording what it
was, and an explicit state saying how the two are to be read. The amount makes
movement price-neutral; the FK keeps corrections flowing; the state keeps sweeps
honest about which rows they may touch. §4.1 develops this.

---

## 2. Product requirements

1. **Wealth stability.** Death, kill-transfer, and reassignment must be
   price-neutral: no user-visible change to rating + stash + credits without a user
   action or a content correction. This applies to *all* gear, including gear bought
   at plain catalog price.

2. **Correction propagation.** When an admin corrects a content price (catalog,
   equipment-list override, expansion, accessory, upgrade), the correction must reach
   every assignment priced by that row — including gear that has since moved to
   another fighter or the stash.

3. **Per-component granularity.** The lifecycle example that defines the requirement:
   fighter A buys a lasgun at A's house-list price of 10¢; A dies and the lasgun goes
   to the stash; fighter B re-equips it; B buys an accessory priced off B's context;
   B dies. The lasgun must still be worth 10¢ + the accessory's acquisition price.
   Each component keeps *its own* acquisition price, independently.

4. **`total_cost_override` keeps its user-facing role** — "this assignment MUST cost
   X" — but gets a staleness UX: when a component purchase/removal would change the
   real total under a set override, the user is asked whether to update the override
   or keep it. Never silently pick either.

5. **Pins are user-editable.** A pin records where a price came from and what it was;
   users must be able to move or clear it (a repricing event with its own audit
   action).

6. **The balance sheet becomes user-facing eventually** — a "why does this cost X"
   per-component breakdown, first as an admin/debug view, later for users.

7. **Credits policy for corrections, stated explicitly.** In campaign mode, a content
   price correction charges or refunds gang credits by the amount of the change —
   this is existing behaviour (`gyrinx/content/models/signal_handlers.py:528` sets
   `credits_delta = -total_delta` for campaign lists). The widened sweeps of §4.7
   extend that to gear that has moved since acquisition, so a correction bills or
   refunds more gangs than it reaches today. That is **intended**: a correction is a
   correction wherever the gear now sits. The credits-ledger invariant (§5.1) makes
   every such charge auditable after the fact.

---

## 3. Technical constraints

1. **Cache-first read path is non-negotiable.** Pages read cached `rating_current`;
   handlers propagate deltas; pins may only change what a *recompute* resolves. No
   render-time cost recomputation may be introduced.

2. **Prefetch / no-N+1 invariant — for render paths.** All cost inputs on page-render
   paths must be reachable from `with_related_data()`-style prefetches. The
   query-count snapshot at
   `gyrinx/core/tests/fixtures/performance_view_queries.json` (see
   `gyrinx/core/CLAUDE.md`) must be regenerated when prefetch shape changes, and
   query counts must not regress. Note the asymmetry this creates for tooling: *live*
   resolution is query-free only for the base component — profile overrides query per
   profile (`list.py:4784-4788`), accessories per accessory (`list.py:4844-4847`),
   SINGLE-mode upgrades per rung (`list.py:4897-4910`). Test- and audit-scope tools
   (the balance-sheet harness, §5) are allowed to pay those queries; render paths are
   not, which is one more reason resolution must read cached amounts (§4.5).

3. **`cached_property` staleness hazard.** The per-component cost caches
   (`base_cost_int_cached` at `list.py:4467-4468`,
   `weapon_profiles_cost_int_cached` at `:4477-4478`,
   `weapon_accessories_cost_int_cached` at `:4487-4488`, `upgrade_cost_int_cached`
   at `:4940-4941`) are `@cached_property` **on the assignment instance**, and
   `cost_int()` reads them. Calling `cost_int()` twice on the same Python object with
   a mutation in between returns the same stale value both times. This silently
   defeats the before/after differential in
   `gyrinx/core/handlers/equipment/reassignment.py:80-96` today — its docstring says
   cost is calculated before and after because "cost may depend on the assigned
   fighter", but the caching guarantees `cost_after == cost_before`, and no test
   covers the `equipment_cost_changed_on_reassignment` telemetry that would have
   caught it. **Design consequence:** no fix may rely on a second `cost_int()` call
   on the same instance; use fresh instances or delta identities (§4.6).

4. **`set_dirty()` / `_affected_list_ids()` matched-pair invariant.** Each
   price-bearing content model's `set_dirty()` sweep has an audit-trail mirror in
   `gyrinx/content/models/signal_handlers.py::_affected_list_ids()` (`:259`); the
   module requires the two to be widened identically, in the same commit.

5. **Additive-only schema discipline.** Pin columns are added nullable; the
   through-model conversion is a *state-only* operation over the existing M2M join
   tables and must match their on-disk shape exactly (§4.8). No destructive schema
   step exists anywhere in this programme — there is nothing to contract.

6. **Batch backfills run via the async task system** — batched writes, idempotent,
   resumable; never one giant transaction.

---

## 4. Design

### 4.1 Core idea: every pin = attribution FK + cached amount + state

At acquisition time, each priced component records **three** things:

- **`pinned_*` FK** → the price-setting content row (the specific
  `ContentFighterEquipmentListItem`, expansion item, equipment-list accessory or
  upgrade override that live resolution landed on). Nullable.
- **`pinned_amount`** — the resolved cost at acquisition. Written for **every**
  component in every state except `UNPINNED`, always, not as an edge-case escape
  hatch.
- **`pin_state`** — a small choices enum making attribution explicit instead of
  inferred from FK nullness:
  - `UNPINNED` — legacy row awaiting backfill; amount null; live fallback applies.
    The only state with a null amount.
  - `SOURCE` — priced by an override row; the pin FK names it.
  - `CATALOG` — priced at catalog; the component's own content FK
    (`content_equipment`, or the through-row's profile/accessory/upgrade FK) *is*
    the attribution. Participates in catalog-price sweeps.
  - `DERIVED` — the amount is an evaluated derivation (expression accessories,
    SINGLE-mode cumulative upgrades, §4.4). Maintained only by re-derivation
    sweeps; **never** matched by raw catalog amount-copy sweeps, which would
    clobber the derived value.
  - `ORPHANED` — the price-setting source has been deleted. The amount is frozen
    and the row is excluded from **all** amount-rewriting sweeps; the deep audit
    classifies it as expected-frozen (§5.1).

  The state cannot be inferred: a bare null FK would be triple-overloaded
  (catalog-attributed vs derived vs orphaned), and any sweep keying on "FK is
  null" would re-price rows deletion promises are frozen, or overwrite derived
  amounts with raw catalog copies. The enum partitions the sweep domains by
  construction. It is a schema-shaping decision and must be settled before the
  schema phase (Phase 4).

The fields divide the work:

- **The amount is what resolution reads.** Holder-independence by construction:
  nothing about pricing a pinned component consults the current holder, so death,
  kill-transfer and reassignment cannot reprice anything — *including catalog-priced
  gear*. This is why the amount must be universal: were the pin an FK alone, a null
  FK would have to mean "fall back to live holder-dependent resolution", and
  catalog-bought gear moved onto a fighter whose equipment list discounts that item
  would silently re-price — the very bug class the programme exists to remove. With
  the amount present in every pinned state, live fallback exists only for
  `UNPINNED` rows.
- **The FK and state are what sweeps read.** When a source row's price is
  corrected, the sweep finds exactly the components it priced — pin-FK equality for
  `SOURCE` rows; the component's own content FK where `pin_state=CATALOG` for
  catalog-priced ones (those sweeps are already holder-independent); derivation
  membership for `DERIVED` rows; `ORPHANED` rows never — and **rewrites their
  amounts** (§4.7). Corrections propagate to every holder, which a bare frozen
  number could never do.
- **Deletion degrades gracefully.** Pin FKs are `on_delete=SET_NULL`. Deleting a
  price-setting content row nulls the attribution but the amount stands: the value is
  frozen, the provenance is gracefully lost, and nothing re-prices — resolution never
  consults the FK. No `PROTECT` is needed. A delete-side handler flips the affected
  rows to `pin_state=ORPHANED` — taking them out of every amount-rewriting sweep —
  and records the attribution loss for auditability (§4.7; this is new work — there
  are currently no `pre_delete`/`post_delete` handlers anywhere in
  `gyrinx/content/models/`).

**The honest trade-off.** Cached amounts do not self-heal. Under live resolution, a
recompute re-derives a correct value from content every time; under pinned amounts, a
component's price is only as correct as the last sweep that maintained it. A missed
sweep means a stale amount that persists until the next correction touches that
component. This is the cost of movement-neutrality, and the design ships an audit
tool aimed squarely at its own failure mode: the balance sheet's
**deep-reconciliation mode** re-resolves every pin FK against its source and reports
amount divergence (§5.1). Fast mode reads cached amounts with zero joins; deep mode
re-resolves and reports drift. Risk §7.1.

### 4.2 Precedence

Per component, in order — matching the order the resolvers actually check:

1. **Explicit override** (`cost_override` on the base — checked before anything
   else, `list.py:4617`; `total_cost_override` at the assignment level) — an
   explicit statement always wins. This rank is also how **default-materialised
   gear** is anchored: materialisation creates the assignment with
   `cost_override=0` (`list.py:4096-4099`), so it costs 0 at rank 1.
2. **Structural zero anchors.** Linked-child gear and default-assignment costing
   cost 0 *before any pin is consulted*: the linked-parent zero
   (`list.py:4620-4622`), the from-default profile/accessory zeros
   (`list.py:4740-4752`, `:4825-4831`), and the hard-coded zeros on the
   default-assignment costing path (`list.py:5257-5258`, `:5276-5277` — hard 0
   despite `ContentFighterDefaultAssignment.cost` existing as a field).
3. **`pinned_amount`** — read directly; zero joins. Applies in every `pin_state`
   except `UNPINNED`.
4. **Live fallback** — the existing holder-dependent resolution, unchanged, serving
   only `UNPINNED` rows. After the universal backfill (§4.8) no production row uses
   this branch; it remains as the safety net and the definition of what the
   backfill writes.

The guarantee **a pin must never charge for default or linked gear** — no matter
what an acquisition path wrote — rests on ranks 1 and 2 outranking rank 3:
default-materialised gear is held at zero by its `cost_override=0` and linked
children by the structural anchor, both consulted before any pin.

### 4.3 Storage

**Decision: explicit nullable FKs per source type, not `GenericForeignKey`.** The
codebase has a GFK precedent (`CustomContentPackItem`,
`gyrinx/core/models/pack.py:87-93`) and it was considered — but it is wrong for this
job:

- **Sweeps need indexed, joinable reverse lookups** (top priority — see §4.7).
  `filter(pinned_equipment_list_item=item)` on a plain FK gets a btree index and
  composes with `Q(...)` exactly like every existing `set_dirty()` filter. A GFK
  reverse lookup needs a hand-rolled composite index and never plans as well.
- **Prefetch is the harder constraint.** A GFK's `content_object` cannot be
  `select_related()`'d; reverse `GenericPrefetch` adds real complexity. The pin
  source set is small and closed (4-5 types, 1:1 with existing models) — explicit FKs
  make prefetch a one-line addition.
- **`SET_NULL` composes with the amount.** FK nulls out, amount stands — the §4.1
  deletion semantics need only the small delete-side handler that flips
  `pin_state` to `ORPHANED`. A GFK left dangling needs manual cleanup signals just
  to reach parity.
- The GFK precedent is justified there by *dozens* of heterogeneous target types.
  Pins don't have that problem.

**Through models are declared in place, on the existing join tables.** The three
component M2Ms (`weapon_profiles_field`, `weapon_accessories_field`,
`upgrades_field`, `list.py:4277-4298`) already have concrete auto-generated join
tables — code touches them directly today (e.g.
`weapon_accessories_field.through.objects.filter(listfighterequipmentassignment=…,
contentweaponaccessory=…)` in `removal.py`). Rather than creating parallel tables,
one migration converts them:

- **State-only conversion** via `SeparateDatabaseAndState`: `CreateModel` for the
  three through models with `db_table` set to the existing join-table names, a
  `BigAutoField` pk (the project's `DEFAULT_AUTO_FIELD`, `settings.py:405` — the
  auto-created join tables were built under it, so anything else diverges on
  fresh-from-migrations databases), FK attribute names and `db_column`s matching
  the columns code already queries on these tables (the lowercased-model-name
  attributes used by `weapon_accessories_field.through.objects.filter(
  listfighterequipmentassignment=…, contentweaponaccessory=…)` at
  `removal.py:251-253` and `sale.py:145`), and `unique_together` on
  (assignment, component) matching the existing unique constraint; plus `AlterField`
  pointing each M2M at `through=`. Database operations: **none** — the tables do not
  change.
- **Additive DDL**: plain `AddField` operations then add the nullable pin columns
  (FKs, amount, `pin_state` defaulting to `UNPINNED`) to the (now-modelled) tables,
  and the base pin columns to the assignment table.
- **No handler/view call-site changes.** Every existing `.add()` / `.set()` /
  `.remove()` / `.all()` keeps working: Django permits plain M2M writes through an
  explicit through model when all its extra fields are nullable or defaulted, which
  the pin fields are. No parallel tables, no dual-write window, no row-copy
  backfill, no cutover phase, nothing to drop later. Verified compatible elsewhere:
  non-admin ModelForms survive, simple-history tracks no M2M state, no fixtures or
  serializers touch the join tables, and `db_table` stability keeps
  `performance_view_queries.json` byte-identical.
- **The one exception is the admin, which the schema phase must rework.**
  `ListFighterEquipmentAssignmentAdmin` lists all three M2M names in `fields`
  (`core/admin/list.py:336-344`); with explicit through models each entry trips
  system check `admin.E013` (`manage check` fails, blocking deploy), and the custom
  form's `__init__` mutates `self.fields["weapon_profiles_field"]` /
  `["upgrades_field"]` (`admin/list.py:313-323`), which KeyErrors once those form
  fields are no longer auto-generated. Replace the M2M widgets with **through-model
  inlines** — which is also how admins get pin visibility (FK, amount, state) per
  component row. This lands inside the schema phase and is part of its Definition
  of done.
- **Consequence for model shape:** the through models mirror the existing tables —
  `BigAutoField` pk, not `Base`/UUID. They may gain `HistoricalRecords()` (an
  additive history table), with a stated caveat: bulk backfill writes
  (`bulk_update`) skip history, so through-row history starts sparse. Accepted —
  the audit trail for backfill is the ListActions it writes (§4.8), not model
  history.

**Fields.**

Base component (directly on `ListFighterEquipmentAssignment` — one base per
assignment, no through-row needed):

- `pinned_equipment_list_item` → `ContentFighterEquipmentListItem`, null, `SET_NULL`
- `pinned_expansion_item` → `ContentEquipmentListExpansionItem`, null, `SET_NULL`
- `pinned_base_amount` — `IntegerField`, null
- `pinned_base_state` — the `pin_state` enum (§4.1), small `CharField` with
  choices, default `UNPINNED`

Component through-models (each also carries `pin_state`, default `UNPINNED`):

- `ListFighterEquipmentAssignmentProfile`: `pinned_equipment_list_item`,
  `pinned_expansion_item` FKs (null, `SET_NULL`); `pinned_amount`
- `ListFighterEquipmentAssignmentAccessory`: `pinned_equipment_list_accessory` FK
  (→ `ContentFighterEquipmentListWeaponAccessory`, null, `SET_NULL`);
  `pinned_amount`
- `ListFighterEquipmentAssignmentUpgrade`: `pinned_equipment_list_upgrade` FK
  (→ `ContentFighterEquipmentListUpgrade`, null, `SET_NULL`); `pinned_amount`

All amounts are nullable `IntegerField` — **not** `PositiveIntegerField`; components
can be negative-cost (the removal handler already formats "removing it costs credits"
for negative components). `pin_state=UNPINNED` (the only null-amount state) = legacy
row awaiting backfill = live fallback; after the universal backfill and its
post-Phase-9 re-run (§4.8), `UNPINNED` rows exist only transiently.

### 4.4 Uniform amounts: no schema special cases

Two component shapes cannot be captured by a single "one FK, resolve its current
price" story — but with an amount on every row, neither needs special schema.

**`cost_expression` accessories.** An accessory `cost_expression` takes precedence
over equipment-list overrides (`list.py:4833-4836`), so an expression accessory's
only cost input is the assignment's base cost. Its `pinned_amount` is the expression
evaluated against the base at acquisition; its pin FK stays null and its
`pin_state` is `DERIVED` — so raw catalog amount-copy sweeps never match it (§4.1).
Corrections are a **sweep-granularity** matter: when the
expression is edited, or when the same assignment's `pinned_base_amount` is rewritten
by a base-price sweep, the sweep re-evaluates the expression against the current
`pinned_base_amount` and rewrites the accessory amount (§4.7). **Required fix:** the
`ContentWeaponAccessory` pre-save handler (`handle_accessory_cost_change`,
`gyrinx/content/models/signal_handlers.py:100-118`) watches only `cost`, not
`cost_expression` — editing an expression today dirties nothing. Two-line fix; the
design depends on it landing with the sweep work.

**SINGLE-mode cumulative upgrades.** The SINGLE branch of
`_upgrade_cost_with_override()` (`list.py:4895-4927`) sums *every* rung at position ≤
the held rung, each rung independently overridable, while the upgrade through-row
holds exactly one rung (the topmost). Its `pinned_amount` is the whole cumulative
total at acquisition; the pin FK points at the held rung's equipment-list override if
one priced it, and its `pin_state` is `DERIVED` regardless — the amount is a
derivation, not a copy of any single source, so amount-copy sweeps must never match
it. Corrections to *any* rung are again sweep-granularity: the
`ContentEquipmentUpgrade` sweep must locate assignments holding any rung of the same
stack at position ≥ the corrected rung and **re-derive** their cumulative amounts
rather than copying a single new price (§4.7). MULTI-mode upgrades are the simple
case: one rung, one amount, FK-matched sweep, `pin_state` `SOURCE` or `CATALOG`.

Stated plainly: for these two shapes, correctness lives in sweep re-derivation logic
rather than an FK equality match. A bug there produces stale amounts — the §4.1
trade-off — and is exactly what the deep-reconciliation mode (which re-derives
independently) is built to catch.

### 4.5 Resolution

Resolution reads the amount — **zero joins for pinned components**. The lookup caches
(`equipment_list_items_lookup`, `list.py:2238`;
`expansion_cost_lookup_by_category`, `list.py:1152`) are untouched and serve only the
legacy fallback branch.

`_equipment_cost_with_override()` (`list.py:4615`) gains one branch after the
existing `cost_override`/linked-parent checks and **before** the
`hasattr(content_equipment, "cost_for_fighter")` annotation shortcut (`list.py:4624`)
— a picker-annotated instance must not outrank the pinned amount — sketch:

```
if pinned_base_amount is not None:  return pinned_base_amount
# ...existing annotation shortcut and live fallback, unchanged (legacy rows only)
```

Profile/accessory/upgrade resolvers get the analogous branch via a per-assignment
`cached_property` map (component_id → through-row) built once from the prefetch.
Precedence per through-row: override → zero anchors → `pinned_amount` → live
fallback (§4.2).

**Call-site shape:** component *writes* keep working through the M2M API (§4.3);
acquisition paths migrate to pin-writing creation via the choke point (§4.6).
Component cost iteration walks prefetched through-rows to reach amounts.

**Prefetch changes:** `ListFighterEquipmentAssignmentQuerySet.with_related_data()`
(`list.py:4174`) prefetches the three through-row sets (pin FKs `select_related`'d
where the UI wants attribution; the amounts themselves add no joins);
`ListFighterQuerySet.with_related_data()` (`list.py:1778`) gets the new path segments
on its component prefetches. `ContentFighterDefaultAssignment` M2Ms stay untouched —
default-assignment gear is hard-zero on the costing path (§4.2) and never needs pins.
Side-benefit: through-model FKs have no manager filtering, so the `all_content()`
prefetch workaround for pack-scoped accessories (`list.py:4186-4191`, `:1854-1861`,
and its mirrors in the kill/sale/removal handlers) becomes unnecessary for prefetch
purposes. Regenerate `performance_view_queries.json` when this lands.

### 4.6 Handler changes

**One choke point for pin-writing.** A single resolve-and-pin step — natural home:
the assignment manager's `create_with_facts` (`list.py:4195`) plus a
component-level twin for through-rows — runs the existing live resolution once and
writes FK + amount + state. Zero-anchored gear (default-materialised, linked-child)
passes through unpinned or amount-0; either way the §4.2 anchors outrank, so a pin
can never charge for it. Every acquisition path routes through this choke point:

1. The main purchase flow. **The assignment is created in the view/form, not the
   handler**: `views/fighter/equipment.py:115-136` does `form.save(commit=False)` →
   `assign.save()` → `form.save_m2m()` (which writes profiles + upgrades);
   `handle_equipment_purchase` only refetches the saved assignment. The choke point
   for this path is therefore a **post-`save_m2m` pinning step invoked by the view**
   (or a form-level hook) — not a handler-internal call. Component purchases
   (accessory/profile/upgrade handlers) create through-rows directly and take pin
   kwargs.
2. `ListFighter.assign()` (`list.py:3050`) — direct assignment creation plus
   component `.add()`s, used by tests/admin/misc flows.
3. Equipment advancements (`list.py:6126`) — direct `create` + `upgrades_field.set`.
4. The vehicle flow (`gyrinx/core/handlers/fighter/vehicle.py:122`) — direct
   `create`.
5. Default-assignment materialisation (`list.py:4096`) — `create_with_facts` with
   `cost_override=0`; zero-anchored.
6. Linked-child equipment creation (`list.py:5087`) — zero via the linked-parent
   anchor.
7. `clone()` (`list.py:4960`) — **copies** pins + amounts + states verbatim; cloning
   is not acquisition, prices carry over.
8. Admin inline creation.
9. The kill/death transfer (`gyrinx/core/handlers/fighter/kill.py:143-168`) —
   creates the stash assignment directly and `.set()`s all three component M2Ms.
   **Allowlisted in the CI guard** until the price-neutral-movement phase (Phase 9)
   converts it to the clone-with-pins path.

**CI guard, in the sweep-test spirit:** a guard test introspects the codebase for
creation paths that bypass the choke point — every non-test construction of the
assignment or its through models must go via the pinning factory (module scan with an
explicit allowlist for the zero-anchored paths, the kill path until Phase 9, and the
admin write surface). A new acquisition path that forgets to pin fails CI instead of
silently minting unpinned rows. **Admin policy, stated once:** admin M2M writes
bypass delta propagation by design; the remediation is the existing recompute
action, and the allowlist entry is permanent.

**The #1925 fix — a delta identity, not a second `cost_int()` call.** Because the
`total_cost_override` short-circuit is the *only* thing that can make an
assignment-level "after − before" differ from a raw component price, the correct
assignment-level delta for any component add/remove/change is:

```
component_delta = 0 if assignment.has_total_cost_override() else raw_component_delta
```

— definitionally equal to `cost_int()`-after minus `cost_int()`-before, computed
without a second staleness-prone call (constraint §3.3). It generalizes cleanly under
pins: adding one accessory never changes the base amount or any other component's
amount, so the identity keeps holding. Apply it wherever a raw component cost feeds
`propagate_from_assignment`/`la_args`: `handle_accessory_purchase`
(`purchase.py:172`), `handle_weapon_profile_purchase` (`:262`),
`handle_equipment_upgrade` (`:353`), `handle_equipment_component_removal`
(`removal.py:174`). Keep the nominal component cost in descriptions and in
`calculate_refund_credits` (`gyrinx/core/handlers/refund.py:8`) — credits are a real
transaction; only rating/stash propagation is gated by the override.

**Sale prices from the assignment, not the catalog.** The sale flow (§1.2) must price
every line from the assignment's own component resolution —
`base_cost_int`/`profile_cost_int`/`accessory_cost_int`/upgrade cost, which after
pinning read the amounts — and honour `total_cost_override` for whole-assignment
sales. The dice-rolled sale price (what the gang *receives*) remains a credits
question; the **stash delta must equal what the caches hold**, or every sale of
non-catalog-priced gear manufactures drift. This fix is valuable pre-pinning (it
stops an active drift producer immediately) and is a prerequisite for pinning to mean
anything at sale time. The sale view's stray debug `print()`s
(`views/fighter/equipment.py:1773`, `:1775`) go with the same change. Owner:
Phase 3.

**Stash component removal must decrement the chain.** Propagate the true component
delta (override-gated per the identity above) into the assignment/fighter caches
regardless of which list-level bucket (rating vs stash) it lands in — fixing the
`removal.py:233`/`:265` zero-propagation described in §1.2. Owner: Phase 3.

**The accessories bare-form fallback goes away.** §1.2's fourth producer
(`views/fighter/equipment.py:1001-1011`) has no UI reaching it — the page's forms
all carry `accessory_id` — so the fix is deleting the branch (returning a redirect
or 400 for POSTs without `accessory_id`) rather than teaching it to propagate.
Owner: Phase 3.

**`total_cost_override` staleness UX (server-rendered, URL-driven).**
Purchase/removal *views* check `has_total_cost_override()`; if set and no choice made
yet, render a confirmation page driven by a query param
(`?override_action=update|keep`):

- `update`: bump the override via `handle_equipment_cost_override`
  (`gyrinx/core/handlers/equipment/cost_override.py:89`, its own ListAction), then
  proceed;
- `keep`: proceed with delta 0 — credits still charged, rating/stash unmoved,
  description states "(fixed total stays X¢)";
- neither: render the choice page (GET). Never silently pick.

Timing: the delta-identity fix introduces the silent "keep" semantics this UX exists
to surface, so the UX lands **with, or in the PR immediately following,** that fix
(Phase 2).

**Kill and reassignment become price-neutral.** `kill.py` stops setting
`total_cost_override`; the stash assignment is created via the clone-with-pins path —
transferred gear keeps its own FKs *and amounts*, which is exactly what makes it
price identically on any later holder without a blanket freeze. Belt-and-braces: the
transfer path resolve-and-pins any row still `UNPINNED` — by the time
this ships (Phase 9, after the Phase 8 backfill) there should be none, and the
defensive pin makes the ordering non-load-bearing. `reassignment.py` needs no cost
logic at all once amounts exist — moving a row changes nothing it reads — but its
broken before/after differential must still be fixed per §3.3 (fresh instance or
delta identity), since it is the same bug class and currently emits false telemetry.

**Holder-context changes stop repricing existing gear — a deliberate behaviour
change.** Today, setting or clearing `legacy_content_fighter` (admin-editable,
`admin/list.py:255`) or changing a fighter's type changes what live resolution
consults (`equipment_list_fighters`, `list.py:2233-2235`), so existing gear silently
reprices at the next recompute — unaudited, which is itself a violation of the
chain-continuity invariant (§5.1 family 3). With pinned amounts that repricing never
happens: acquisition context is what prices gear (§1.3), and a holder-context change
is not an acquisition. Users (or admins) who *want* the reprice perform it
explicitly via pin editing (§2.5 / Phase 10), which audits it. The §5.2 matrix
carries a "holder context changed" column so the new behaviour is pinned by test
rather than folklore.

### 4.7 Sweeps: widen and maintain the amounts

Sweeps now do two jobs: **rewrite amounts, then mark dirty**. When a price-bearing
source changes, the async task:

1. **Finds affected component rows, partitioned by `pin_state`:**
   - *override sources* — pin-FK equality on `SOURCE` rows (indexed reverse
     lookup);
   - *catalog sources* — the component's own content FK where
     `pin_state=CATALOG`; these sweeps are holder-independent already;
   - *derivation membership* — `DERIVED` rows only. SINGLE stacks: through-rows
     holding any rung of the same stack at position ≥ the corrected rung;
     expression accessories: rows whose expression was edited **or whose
     assignment's `pinned_base_amount` was rewritten earlier in the same sweep**
     (base corrections cascade to same-assignment expression accessories).
   - `ORPHANED` rows are excluded from **every** amount-rewriting sweep — their
     amounts are frozen by definition (§4.1); `UNPINNED` rows have no amount to
     rewrite and are reached by the existing dirty-marking alone.
2. **Computes exact per-row deltas**: new resolved amount − `pinned_amount`.
3. **Rewrites the amounts BEFORE any recompute/dirty processing.** This ordering is
   load-bearing against double-counting: `facts_from_db` must sum already-updated
   amounts, and the audited CONTENT_COST_CHANGE deltas come from old-vs-new amounts.
   Run dirty processing first and the correction either vanishes (recompute re-reads
   old amounts and the caches snap back) or double-counts (delta applied now, amounts
   rewritten later, second delta on the next recompute). A test pins the ordering.
4. **Marks dirty and lets the CONTENT_COST_CHANGE machinery apply and audit the
   deltas** — including the campaign-mode credits charge/refund
   (`signal_handlers.py:528`; policy §2.7).

**The audited deltas switch to per-row amounts, in this same phase.** The existing
machinery computes *list-level snapshot-vs-recompute* deltas: a pre-change cost
snapshot captured at enqueue (`signal_handlers.py:390-405`), recompute-vs-snapshot
in the async task (`:484-516`), campaign credits derived from that (`:524-535`).
That construction has an enqueue-to-task race: any user action landing in the window
(a purchase, say) is folded into the recompute but not the snapshot, so the same
`*_before` baseline is effectively claimed twice — the correction's audit action
absorbs the purchase's delta and campaign credits are double-charged, breaking chain
continuity (§5.1 family 3). Widened sweeps amplify the exposure (more lists per
correction, longer task runs), so the sweep-widening phase (Phase 6) switches the
delta computation to **the sum of per-row amount deltas** — Σ(new − old
`pinned_amount`) over the rows the sweep rewrote — which is independent of anything
else happening to the list inside the window and is exactly what step 2 already
computes. Until that switch lands the race is inherited from today's code, and the
family-3 invariant is what flags it.

`bulk_mark_assignments_dirty()` (`list.py:109`) already fans assignment → fighter →
list. Per-model changes:

| File:line | Current filter keys off | Change |
|---|---|---|
| `content/models/equipment.py:551` (`ContentEquipment`) | `content_equipment=self` | holder-independent already; **gains amount-rewrite** for base rows with `pin_state=CATALOG` |
| `content/models/weapon.py:358` (`ContentWeaponProfile`) | M2M | through-row lookup `profile_assignments__profile=self`; rewrite catalog-attributed amounts |
| `content/models/weapon.py:538` (`ContentWeaponAccessory`) | M2M | through-row lookup; rewrite catalog-attributed amounts; **plus expression re-derivation** (§4.4) |
| `content/models/equipment.py:683` (`ContentEquipmentUpgrade`) | M2M | through-row lookup; MULTI: rewrite matched rows; **SINGLE: re-derive cumulative amounts for same-stack rows at position ≥ self** (§4.4) |
| `content/models/fighter.py:316` (`ContentFighter`) | holder | unchanged (fighter base cost, not equipment) |
| `content/models/house.py:132` (`ContentFighterHouseOverride`) | holder | unchanged |
| `content/models/equipment_list.py:65` (`ContentFighterEquipmentListItem`) | **current holder's content_fighter** | **widen**: OR `Q(pinned_equipment_list_item=self)` on assignments + the profile-through mirror; rewrite pinned amounts |
| `content/models/equipment_list.py:125` (`...ListWeaponAccessory`) | **current holder** | **widen**: OR through-rows `pinned_equipment_list_accessory=self` → assignment ids; rewrite amounts |
| `content/models/equipment_list.py:185` (`...ListUpgrade`) | **current holder** | **widen**: OR `pinned_equipment_list_upgrade=self`; rewrite amounts |
| `content/models/expansion.py:293` (`ContentEquipmentListExpansionItem`) | equipment FK (already conservative) | OR pin FK; rewrite pinned amounts |

Every widened filter must be applied identically to
`_affected_list_ids()` (`gyrinx/content/models/signal_handlers.py:259`), **in the
same commit** (constraint §3.4).

**Delete-side handling (new work).** There are currently no
`pre_delete`/`post_delete` handlers anywhere in `gyrinx/content/models/` — deleting a
price-setting row is completely unwatched today. Add one per pin-target model: a
`pre_delete` handler captures the component rows about to lose attribution (pin-FK
match); after `SET_NULL` runs, those rows are flipped to `pin_state=ORPHANED` and an
audit record is written (per affected list: "price source deleted; N components keep
their amounts, attribution cleared"). No cache movement and no dirty-marking —
amounts stand, so no price changes — and the `ORPHANED` state is what keeps every
later sweep's hands off these rows (§4.1). Deep reconciliation (§5.1) classifies
them as expected-frozen rather than divergent.

**Archived rows are swept too.** Amount-rewriting sweeps include archived fighters'
and archived assignments' component rows: the rewrite is the same bulk UPDATE either
way, and skipping them would let a later unarchive resurrect a stale amount that the
deep audit would misread as a missed sweep. Cache fan-out keeps its existing
behaviour — `bulk_mark_assignments_dirty()` delegates `archived=False` filtering to
its callers (`list.py:121-123`) and that stands: archived rows get correct amounts
but no cache churn. The universal backfill (§4.8.4) pins archived rows for the same
reason. Balance-sheet *totals* exclude archived rows, matching cache semantics, but
deep mode audits their amounts (§5.1).

**Sweep-coverage test** ("does every sweep find pinned-but-moved gear and fix its
amount?"): one generated, parametrized test per pin-bearing source model — build
fighter A whose context prices the gear → assign, capture pin FK + amount → move the
gear to a fighter/stash whose context would never match that source → change the
source's cost → assert the amount is rewritten, the assignment is dirty, the
recompute matches, and the audit action + campaign credits are present. Plus
dedicated cells for SINGLE-stack lower-rung correction and expression re-derivation.
The parametrization list is asserted against model introspection (every model with a
`pinned_by_*` reverse relation must appear), so adding a new pin type without sweep
coverage fails CI.

### 4.8 Migration and backfill

1. **Schema** (Phase 4): the in-place through conversion + pin columns of §4.3. One
   deploy, no data movement, behaviour-neutral, no handler/view call-site changes —
   the admin rework (§4.3) is the one code change riding along.

2. **Drift reconciliation across ALL fighters** (opening Phase 8): before amounts are
   written en masse, recompute the cache chain for every fighter — not only stashes.
   Drift lives on regular fighters too: any fighter that ever hit the
   override-purchase, sale, stash-removal, or reassignment paths of §1.2 can carry
   it. Two hard requirements:
   - **Every value-changing recompute writes an audited action.** New
     `ListActionType.RECONCILE` (the enum at `gyrinx/core/models/action.py:17` has no
     such member today) carrying before-values and deltas — so the ledger-continuity
     invariant (§5.1) survives the recompute instead of being broken by a silent
     snap. The admin recompute action (`admin/list.py:180`), which writes no
     ListAction today, adopts the same type.
   - **Order matters for correctness too**: the delta-apply path clamps —
     `rating_current`/`stash_current` are updated as `max(0, current + delta)`
     (`list.py:1334-1335`). Applying pin-era deltas on top of stale caches doesn't
     500; it silently loses the clamped remainder, which is worse — a clamped apply
     breaks the chain-continuity invariant (§5.1 family 3) with no error anywhere.
     Reconciling first removes the hazard, and the RECONCILE work should flag any
     clamp that does fire as a continuity break in its own right.

3. **Legacy override conversion**: *(scope reduced — the prototyped kill-freeze
   never shipped, so no system-written override rows exist in production; only
   user-set `total_cost_override` rows do, and those stay user-owned as-is.)*
   Retained for reference in case any system-written rows are found: `kill.py` would have written system-owned
   `total_cost_override` rows on every death-transfer. Left alone, they would outrank
   pins forever (§4.2) and trigger staleness prompts users never asked for. Convert:
   where the override equals the assignment's current calculated component total,
   clear the override and write pins + amounts from live resolution —
   value-identical by construction. Where they differ, leave the row untouched and
   surface it in the drift report (§5.1 / Phase 1 command) for review — never
   silently pick a value. User-set overrides are not touched.

   **Expectation, stated plainly: the rows the freeze was invented for fail the
   convert-where-equal test by construction.** A kill-frozen row for discounted gear
   exists *precisely because* the frozen value differs from what stash-context
   resolution produces — that difference is the #1826 bug the freeze papered over.
   So the motivating population stays under `total_cost_override`, and the review
   queue is expected to be **dominated** by these rows, with nothing to resolve them
   to (the original acquisition context is unrecoverable). That end state is
   acceptable: after the #1925 delta-identity fix and the staleness UX (Phase 2), a
   standing override is safe rather than divergence-producing, and any user who
   wants the row on proper pins can re-price it via pin editing (§2.5 / Phase 10).
   The conversion's success metric is therefore *no silent value changes*, not
   *queue emptied*.

4. **Universal resolve-and-pin backfill**: batch through every assignment and
   through-row — archived included (§4.7); write `pinned_amount`, `pin_state`
   (`SOURCE`/`CATALOG`/`DERIVED` as resolution dictates), and the pin FK where an
   override row prices the component, all from the *current* live resolution.
   Properties:
   - **Value-neutral for `cost_int()` by construction** — each amount equals what
     live resolution returns at that instant; and after step 2 the caches agree with
     `cost_int()`, so it is cache-neutral too: no ListActions, no wealth movement.
   - **Sequencing**: runs after sweep widening (Phase 6) *and* after acquisition
     pin-writing (Phase 7) — so no pinned row is ever correction-blind, and no new
     unpinned rows are being minted while the backfill chases them.
   - Runs via the async task system — batched `bulk_update`, idempotent (skip rows
     whose `pin_state` is no longer `UNPINNED`), resumable.
   - Payoff: after this, no production row uses the live-fallback branch, and the
     kill/reassignment changes (Phase 9) can never meet unpinned gear. Old stash gear
     resolves at catalog today → amount = catalog price, `CATALOG` state; its
     original acquisition context is unrecoverable and stays catalog-attributed.
     Wrong or unwanted backfill pins are user-fixable via pin editing (§2.5 /
     Phase 10).

5. **Post-Phase-9 re-run — a documented procedure, not an afterthought.** Between
   the Phase 8 conversion/backfill and the Phase 9 deploy, every death still runs
   the old kill path: it mints *new* system-owned `total_cost_override` rows with
   `UNPINNED` through-rows. Steps 3 and 4 are idempotent by construction precisely
   so they can be **re-run once Phase 9 is live**, converting and pinning whatever
   the window minted. "No `UNPINNED` rows remain" is therefore a post-re-run
   claim, not a Phase 8 exit criterion.

---

## 5. Verification: balance-sheet harness first

The harness lands **before any production-code change** (Phase 1) so every later
phase has a regression gate, and every known drift producer is encoded as a failing
test from day one.

### 5.1 Module

New `gyrinx/core/cost/balance_sheet.py` (sibling to `propagation.py`, following the
convention that cross-cutting cost reporting lives in `core/cost/`, not on models).
Frozen dataclasses — field lists, not full definitions:

- `ComponentLine` — one priced component (base / one profile / one accessory / one
  upgrade): `kind`, `label`, `amount`, `pricing`
  (`"user_override" | "pinned" | "live"`), `pin_state` (§4.1, passed through so the
  deep audit can classify), `source_repr` (human-readable pointer to the
  attribution — the pin FK target, or the catalog row for `CATALOG` rows).
- `AssignmentBalance` — `assignment_id`, `equipment_name`, `lines`,
  `total_cost_override`, `cached_rating_current`; `calculated_total` = sum of lines;
  `total` = override if set, else calculated.
- `FighterBalance` — `fighter_id`, `name`, `is_stash`, `is_child`, `base`,
  `advancements`, `assignments`, `cached_rating_current`, `dirty`;
  `calculated_total`. **Child fighters** (vehicles/beasts spawned by an assignment)
  appear as their own `FighterBalance` with base 0 — `is_child_fighter` zeroes the
  fighter's base cost (`list.py:2470-2471`) while the owning assignment carries the
  equipment's value; the child's own assignments price normally. `reconcile()`
  asserts the pairing (child base 0 ↔ parent assignment priced) so nothing
  double-counts.
- `ListBalance` — `list_id`, `name`, `fighters` (active, non-stash), `stash`,
  cached `rating/stash/credits_current`, `dirty`; `reconcile() -> list[str]` returns
  human-readable drift problems (`[]` == clean).

`reconcile()` checks three invariant families:

1. **Calculated vs cached** at list, fighter, and assignment level (recompute-vs-
   cache agreement — the §1.2 drift class).
2. **Credits ledger**: `credits_current == chain-start credits + Σ
   ListAction.credits_delta`. Credits are a ledger, not derivable from content — a
   wrong `credits_delta` can never be caught by recompute comparison, only by
   summing the ledger.
3. **Action-chain continuity**: per action chain, `rating_before + Σ rating_delta ==
   rating_current` (and the stash analog). This is what catches silent recomputes —
   a wrong delta followed by any cache snap is invisible to family 1 — and it is why
   every value-changing recompute must write a `RECONCILE` action (§4.8.2).

**Scoping and anchoring for families 2 and 3.** Both families are ledger checks, so
both need a defined starting point and a ledger that actually records every
mutation:

- **Anchor at the chain start.** "Starting" values are the first ListAction's
  `*_before` fields (`credits_before`, `rating_before`, `stash_before`) — not list
  creation, which predates the action system for old lists. The invariants apply
  only to **lists with an action chain**: `create_action` records nothing without
  `latest_action` under `FEATURE_LIST_ACTION_CREATE_INITIAL` (`list.py:1285`), and
  the async cost-change task already skips no-chain lists
  (`signal_handlers.py:470-471`). No-chain lists are reported as *unscoped*, not
  failing.
- **Every credit mutator must write a ListAction — one today does not.**
  `Campaign._distribute_budget_to_list` (`gyrinx/core/models/campaign.py:164-188`)
  adds starting-budget credits directly to `credits_current` with only a
  `CampaignAction`, so every budget-funded list would violate family 2 as a false
  positive. Converting it to a proper ListAction is a small fix and lands as part
  of the harness-enablement work (Phase 1) — it is what makes family 2 satisfiable
  at all.
- **Family 3 has a documented eventual-consistency window.** A content cost change
  marks lists dirty and defers the audited action to an async task; a user who
  views the list first triggers a lazy recalc that writes new cache values with no
  action (`signal_handlers.py:473-491` — the task compensates using the enqueue
  snapshot when it lands). Inside that window the chain is legitimately
  discontinuous. The production drift report must run outside the window (no
  in-flight cost-change tasks) or tolerate in-flight chains — flag-and-recheck
  rather than hard-fail.

**Query budget, honestly stated.** `build_balance_sheet(lst)` is test- and
audit-scope and **may query**. Live resolution is inherently query-per-component
beyond the base (constraint §3.2's anchors), and pretending otherwise would push
production lookup-dict work into Phase 1 for no product benefit. The render-path
constraints are untouched because the harness is not a render path. Two modes:

- **Fast mode** reads pinned amounts + cached fields — zero extra joins for pinned
  rows, falling back to live resolution (with its queries) for `UNPINNED` rows.
  Fast mode becomes *genuinely* cheap only once amounts exist; the Phase 10 UI builds
  on it and carries its own explicit perf gate. Totals exclude archived rows,
  matching cache semantics (§4.7).
- **Deep-reconciliation mode** re-resolves every pin against its source (archived
  rows included), re-derives SINGLE-stack and expression amounts independently, and
  reports amount divergence **classified by `pin_state`**: for
  `SOURCE`/`CATALOG`/`DERIVED` rows divergence means a missed or mid-flight sweep —
  the design's own failure mode (§4.1) — while `ORPHANED` rows are reported in a
  separate **expected-frozen** category: their source is gone, they diverge from any
  live attribution by design, and mixing them into the divergence report would turn
  the audit into noise.

Before pins exist, every `ComponentLine.pricing` is `"user_override"` or `"live"`;
the `"pinned"` value exists in the schema from day one so later phases only change
what populates it.

### 5.2 Situation matrix

One pytest module `gyrinx/core/tests/test_balance_sheet.py`, one test per
(situation × mechanism) cell. Each cell asserts `reconcile() == []` **twice**:
immediately after the action, and after a forced `lst.facts_from_db(update=True)` —
the second check is what catches "cache says X, recompute says Y" drift.

| Situation | Assign | Purchase base | Purchase profile | Purchase accessory | Purchase upgrade | Remove component | Reassign | Kill/transfer | Sale | Override set/clear | Content price change | Pack/expansion price change | Holder context changed | Repeat death |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Fresh assignment, no override | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Assignment with `total_cost_override` set | – | – | ✓ **(xfail: #1925)** | ✓ **(xfail: #1925)** | ✓ **(xfail: #1925)** | ✓ **(xfail: #1925)** | ✓ | ✓ | ✓ **(xfail: sale)** | ✓ | n/a (override wins) | n/a | n/a (override wins) | ✓ |
| Assignment with base `cost_override` only | – | n/a | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | n/a | ignored for base | ignored for base | ✓ | ✓ |
| Gear moved fighter→fighter→stash→fighter (the §2.3 lifecycle) | | | | | | ✓ **(xfail: stash removal)** | ✓ | ✓ | ✓ **(xfail: sale)** | | ✓ (price changed on the *original* pinning fighter's list, after the gear has moved) | ✓ | ✓ | ✓ (twice) |
| **Legacy: unpinned discounted gear** (null amounts, simulating pre-programme rows) | | | | | | ✓ | ✓ | ✓ | ✓ **(xfail: sale)** | | ✓ | ✓ | ✓ | ✓ |
| **Legacy: user-set `total_cost_override` row** (the only override rows production carries) | | | ✓ **(xfail: #1925 class)** | ✓ **(xfail: #1925 class)** | ✓ **(xfail: #1925 class)** | ✓ | ✓ | ✓ | ✓ **(xfail: sale)** | ✓ (conversion) | n/a | n/a | n/a (override wins) | ✓ |

The two legacy rows model **"pre-programme data meets each pipeline stage"** — the
rows that prod actually carries. Some of their cells are red on current code (the
xfails below); others would go red under a mis-ordered rollout (e.g. handlers
becoming price-neutral before the backfill pinned legacy gear). The matrix is the
tool that catches that ordering mistake mechanically instead of by review.

**The catalog-vs-pack axis.** Every matrix cell that consumes content runs
twice — once with plain catalog rows, once with identical content scoped to a
subscribed `CustomContentPack` (parametrized fixtures, not duplicated tests).
Pack content is invisible to the default `ContentManager` and only surfaced by
`all_content()`/`with_packs()`, so any cost path that fetches content
carelessly prices pack gear differently — a class of drift the catalog variant
can never see. The axis has already earned its place twice: the Phase 2 review
caught a pack-only regression in the reassignment refetch, and the axis's
first run surfaced producer #1930. Cells whose *expected* behaviour differs by
side (the price-change sweep cells, the bare-form endpoint) use explicit
per-side parameters with per-side xfail marks instead of the shared fixture.

The **holder context changed** column (set/clear `legacy_content_fighter`, change
fighter type — §4.6) asserts the intended end state: existing gear does *not*
reprice, and every invariant family holds. On current code these cells expose
today's silent, unaudited repricing (a family-3 break for unpinned gear); they go
green as amounts land (Phase 5) and the backfill pins legacy rows (Phase 8) — a
second example of the "green only under the right rollout order" class the matrix
exists to police.

### 5.3 Known-red cells: strict-xfail tripwires, one group per live producer

Each live producer (§1.2) is a strict-xfail group owned by a named phase
(fixed producers' groups have flipped to passing assertions):

- **#1925 override-purchase divergence** — set `total_cost_override` via its handler,
  buy a component via its handler, reconcile. Fails: cached rating carries the
  component; recompute returns the bare override. Fixed in Phase 2. (The legacy
  kill-frozen row's purchase cells are the same divergence class and flip with it.)
- **Sale catalog-mispricing** — sell discounted or frozen gear; the stash cache
  drifts by (cached value − catalog price). Fixed in Phase 3.
- **Stash component-removal zero-delta** — remove a component from stash gear; the
  assignment/fighter caches keep its value. Fixed in Phase 3.
- ~~Accessories bare-form unaudited rewrite~~ — branch deleted in the pack-axis
  PR; a both-sides cell asserts the bare POST is inert.
- **Death-transfer re-pricing (#1826)** — kill a fighter carrying equipment-list
  discounted gear; the stash caches take the dying-fighter value while the stash
  assignment recomputes at catalog. Fixed by pinning in Phase 9 (price-neutral
  movement) — the headline bug flips last, when movement stops touching prices.
- **Reassignment context staleness** — move discounted gear to a fighter whose
  context prices it differently; the caches take the old-context price, recompute
  takes the new. Fixed in Phase 2 alongside #1925 (same `cached_property` hazard
  family, §3.3).
- ~~Pack price corrections never sweep (#1930)~~ — fixed in the pack-axis PR;
  both price-change cells now pass on both sides.

Each is marked `xfail(strict=True)`: it documents the bug, proves the harness can see
it, and strictness forces the mark to be removed in the same change that fixes it.
Any phase that accidentally re-introduces a divergence turns the matrix red.

---

## 6. Phasing

Three principles govern the sequence:

1. **Introspection before change.** Tools that reveal the current state land before
   anything mutates — the first deliverable improves our understanding of production
   reality, not production behaviour.
2. **Every phase is a standalone improvement.** A user or maintainer could stop after
   any phase and be better off than before it.
3. **Every phase has an explicit Definition of done and How we verify it.**

Exit gate for every phase: **all previously-green balance-sheet tests stay green.**

### Phase 1 — See the world: harness, matrix, debug UI

- **Deliverable:** `balance_sheet.py` (fast + deep modes, all three `reconcile()`
  invariant families with the §5.1 chain anchoring and scoping), `test_balance_sheet.py`
  (full matrix including the two legacy rows), the six strict-xfail groups, and the
  **balance-sheet debug UI**: a read-only, staff-gated per-list view in the app
  (a sibling of the list action log view) rendering every fighter → assignment →
  component line with its pricing state, cached-vs-computed columns, and any
  `reconcile()` problems highlighted. The same code path is runnable on demand
  against a *specific* production list (the debug view in prod, or a one-liner via
  `manage prodshell`); a fleet-wide drift sweep is a nice-to-have loop over the
  same entrypoint, **not** a gate and **not** a CI job — the balance sheet runs in
  tests and on demand, and is verified by eyes on real lists. One small production
  change rides along as harness enablement: `Campaign._distribute_budget_to_list`
  converted to write a proper ListAction (§5.1 — without it family 2
  false-positives on every budget-funded list).
- **Definition of done:** matrix merged and green except the six xfail groups;
  the budget-distribution ListAction conversion merged; the debug view renders a
  deliberately-drifted seeded list with the drift highlighted and a healthy list
  clean; the maintainer can open it for any list (including the original #1826
  production list) and verify by inspection.
- **How we verify it:** fault-injection meta-tests calibrate the instrument
  (tamper each cached level independently — assignment, fighter, stash, list
  rating, credits, an action delta — and assert `reconcile()` names exactly that
  level and nothing else); the six xfails fail strictly on current code for their
  verified mechanisms (proving the harness sees each known bug); a budget-funded
  campaign list reconciles clean on family 2; the debug view issues no writes
  (asserted via captured queries) and has a bounded query count; CI runs the full
  test matrix (the *tests* run in CI; the drift tooling does not).

### Phase 2 — Stop the #1925 divergence class

- **Deliverable:** the component-delta identity in the four purchase/removal handler
  sites (§4.6); the `reassignment.py` differential fix (§3.3 — same bug class); the
  `total_cost_override` staleness UX, in this phase or the immediately-following PR
  (§4.6 timing).
- **Definition of done:** the #1925 xfail group flipped; a test covers the
  `equipment_cost_changed_on_reassignment` telemetry; the staleness UX merged or its
  PR open.
- **How we verify it:** override-row matrix cells green both immediately and
  post-recompute; action-chain continuity holds across a purchase-onto-override; the
  legacy kill-frozen row's purchase cells flip with the same change.

### Phase 3 — Stop sale, stash-removal, and bare-form drift

- **Deliverable:** sale lines priced from the assignment's component resolution with
  `total_cost_override` honoured (§4.6, including removal of the stray sale-view
  debug `print()`s); stash component removal propagates the true delta into the
  assignment chain (§4.6); the accessories bare-form fallback branch removed
  (§4.6).
- **Definition of done:** all three remaining xfail groups flipped; no strict xfails
  remain in the matrix.
- **How we verify it:** sale and removal cells green pre- and post-recompute across
  all matrix rows, including both legacy rows; a POST without `accessory_id` no
  longer mutates the M2M; a post-deploy re-run of the Phase 1 drift report shows
  the producers stopped (no *new* drift accruing).

### Phase 4 — Pin schema, inert

Precondition: the `pin_state` enum (§4.1) is settled — it shapes the columns.

- **Deliverable:** the in-place through-model conversion + pin columns including
  `pin_state` (§4.3); the assignment admin reworked to through-model inlines
  (§4.3 — the M2M `fields` entries and the custom form's M2M mutation cannot
  survive explicit through models); prefetch updates (§4.5);
  `performance_view_queries.json` regenerated.
- **Definition of done:** migrations applied; no handler/view call-site changes;
  `manage check` clean (no `admin.E013`); the admin change form loads and saves,
  with pin columns visible read-only on the inlines; query counts not regressed;
  pins entirely inert.
- **How we verify it:** `makemigrations` clean afterwards; the full matrix green
  (behaviour-neutrality); the snapshot diff reviewed; a test proves M2M
  `.add()`/`.set()` still work through the declared through models; an admin
  smoke test exercises the change form.

### Phase 5 — Resolution honours amounts

- **Deliverable:** the precedence branch in the four resolvers (§4.5). All amounts
  null in production → no-op on deploy.
- **Definition of done:** hand-set-amount tests prove the §4.2 precedence: amount
  beats live and annotation shortcuts; zero anchors and user overrides beat amount.
- **How we verify it:** matrix green; a test hand-pins an assignment, moves it across
  holders with different equipment lists, and asserts the price never moves.

### Phase 6 — Sweeps maintain the amounts

- **Deliverable:** widened `set_dirty()` + `_affected_list_ids()` matched pairs;
  amount-rewrite in the async task with the rewrite-before-recompute ordering,
  partitioned by `pin_state` (§4.7); **the CONTENT_COST_CHANGE delta computation
  switched from list-level snapshot-vs-recompute to per-row amount sums** (§4.7 —
  this is what closes the enqueue-to-task double-count race that widened sweeps
  would otherwise amplify); SINGLE-stack and expression re-derivation; the
  delete-side `ORPHANED` handler; the `cost_expression` watch fix (§4.4, if not
  already landed standalone). No-op against all-`UNPINNED` production columns.
- **Definition of done:** the parametrized sweep-coverage test with its introspection
  assertion passes; the ordering test (amounts rewritten before dirty processing)
  passes; the delete-side handler has a test; a test simulates a user purchase in
  the enqueue-to-task window and asserts no double-count.
- **How we verify it:** per-source sweep tests — hand-pinned gear moved off-context,
  source corrected → amount rewritten, dirty set, recompute matches, audit action +
  campaign credits present; SINGLE lower-rung and expression cells pass; `ORPHANED`
  and `DERIVED` rows untouched by amount-copy sweeps; matched-pair widening in a
  single commit per model.

### Phase 7 — Acquisition writes pins

- **Deliverable:** the resolve-and-pin choke point; the nine enumerated paths
  (§4.6) routed through it — for the main purchase flow that means a
  post-`save_m2m` pinning step invoked by the view (or a form-level hook), since
  the assignment is created by the view/form, not the handler (§4.6 path 1); the
  CI bypass guard with its allowlist (zero-anchored paths, kill path until
  Phase 9, admin surface permanently).
- **Definition of done:** each path has a test asserting FK + amount + state
  written (or the zero-anchor paths asserting no charge); the guard test is in CI.
- **How we verify it:** matrix rows for fresh acquisitions show
  `pricing == "pinned"` in the balance sheet; the guard fails on a synthetic
  bypassing call site; the §2.3 lifecycle test passes for newly-acquired gear.

### Phase 8 — Backfill: reconcile, convert, pin

- **Deliverable:** `ListActionType.RECONCILE` + the audited all-fighter drift
  recompute (§4.8.2, admin action included); the legacy kill-freeze conversion
  (§4.8.3); the universal resolve-and-pin backfill (§4.8.4). Both conversion and
  backfill idempotent by construction — they are re-run after Phase 9 (§4.8.5).
- **Definition of done:** `UNPINNED` row count reaches zero **for rows existing at
  backfill time** — the final zero is a post-Phase-9-re-run claim, since deaths in
  the Phase 8→9 window keep minting frozen, unpinned rows (§4.8.5); the
  review-queue of unconvertible overrides enumerated in a report, with the
  expectation set that discounted kill-frozen rows dominate it and stay frozen
  (§4.8.3); every value-changing recompute audited.
- **How we verify it:** sampled assignments' `cost_int()` identical before/after
  (value-neutrality); action-chain continuity holds *through* the RECONCILE actions;
  deep-reconciliation mode reports clean on a prod copy; the drift report re-run
  shows family-1 drift eliminated.

### Phase 9 — Price-neutral movement

- **Deliverable:** `kill.py` drops the `total_cost_override` freeze and transfers
  pins + amounts (with the defensive pin-on-transfer for any `UNPINNED` straggler);
  reassignment carries amounts inherently (§4.6); the kill path leaves the CI-guard
  allowlist (§4.6); **the post-deploy re-run of the §4.8.3 conversion and §4.8.4
  backfill**, clearing whatever the Phase 8→9 window minted (§4.8.5).
- **Definition of done:** the full §2.3 lifecycle walkthrough (A buys → dies → B
  re-equips → B buys accessory → B dies) green as a named balance-sheet test, both
  prices held at each stage, including repeat deaths; both legacy matrix rows green
  under the new kill path; after the re-run, `UNPINNED` row count is zero and no
  system-owned frozen rows remain outside the review queue.
- **How we verify it:** movement cells green pre- and post-recompute; a wealth
  invariant test (rating + stash + credits unchanged across a kill); no new
  kill-frozen overrides appear in the drift report after deploy; the re-run's
  report shows the window's rows converted and pinned.

### Phase 10 — Surfaces: user-facing breakdown and pin editing

The staff debug view ships in Phase 1; this phase makes the balance sheet a
product surface.

- **Deliverable:** the user-facing "why does this cost X" breakdown (fast mode,
  with an explicit query budget — cheap by now because pinned amounts read with
  zero joins); **pin editing** — each component line gets an edit affordance
  ("move pin from fighter-type X's list to Y's / clear to catalog"). A pin edit is
  a repricing event — resolve old vs new, delta, ListAction, propagate — following
  the `cost_override.py` handler pattern; server-rendered, URL-driven per project
  conventions. Doubles as the remediation path for unwanted backfill pins.
- **Definition of done:** perf gate (query-count ceiling) enforced by test; the
  edit handler audited.
- **How we verify it:** performance snapshot for the view; an edit-flow test
  asserting old-vs-new resolution, ListAction, and propagation.

---

## 7. Risks, ranked

1. **Stale amounts on missed sweeps — the design's own failure mode.** Cached
   amounts do not self-heal (§4.1): a sweep that fails to find or re-derive a
   component leaves a wrong price until the next correction happens to touch it.
   This is the accepted price of movement-neutrality. Mitigations, layered: the
   parametrized sweep-coverage test with its introspection assertion (§4.7); the
   matched-pair docstring convention in `signal_handlers.py` (any new price-setting
   model must update `_affected_list_ids()` and the sweep test in the same PR); the
   deep-reconciliation mode as a standing audit runnable against production — with
   its `pin_state` taxonomy keeping it signal: `ORPHANED` rows report as
   expected-frozen, not divergence (§5.1); the drift report re-runnable at any
   time. The `pin_state` partition also removes an entire hazard sub-class at the
   root: without it, sweeps keying on "FK is null" would re-price orphaned rows and
   clobber derived amounts (§4.1).

2. **Sweep ordering violations double-count or drop corrections.** Amounts must be
   rewritten before dirty/recompute processing (§4.7.3). Mitigation: keep
   amount-rewrite and dirty processing in one task body; the ordering test. A
   sibling hazard is inherited rather than introduced: the existing snapshot-based
   delta machinery double-counts user actions landing in the enqueue-to-task window
   (§4.7), which widened sweeps would amplify — closed by the per-row delta switch
   in the same phase (Phase 6); until then, family 3 is what flags it.

3. **Re-derivation complexity for SINGLE stacks and expression accessories.** These
   sweeps re-derive rather than FK-match (§4.4) — the most intricate sweep logic in
   the design. A bug here is a risk-1 instance, but deep mode re-derives
   independently, so it surfaces as reported divergence rather than silent drift.

4. **The `cost_expression` signal-watch gap must actually land** (Phase 6 or
   standalone). Expression amounts are maintained by sweeps *by design*, which is
   only sound if expression edits trigger sweeps — today they don't
   (`signal_handlers.py:100-118`).

5. **The `reassignment.py` caching hazard is masked, not absent.** Amounts make
   reassignment inherently neutral, but the broken differential and its untested
   telemetry are the same bug class (§3.3); the Phase 2 gate must cover it
   explicitly, not just #1925.

6. **Kill-frozen overrides that stay frozen.** Discounted kill-frozen rows fail the
   convert-where-equal test *by construction* — the freeze exists precisely because
   the frozen value differs from stash-context resolution — so the review queue is
   expected to be dominated by rows with nothing to convert to (§4.8.3). This is a
   managed end state, not a failure: post-Phase-2 a standing override is safe, and
   pin editing (Phase 10) is the user remedy. The Phase 1 drift report sizes the
   queue up front; if it is large, review tooling may need its own slice of
   Phase 8. The Phase 8→9 window mints *more* frozen rows by design; the documented
   post-Phase-9 re-run (§4.8.5) is the procedure that clears them.

7. **`hasattr(..., "cost_for_fighter")` short-circuits** (`list.py:4624, 4754, 4838,
   4872`). The amount branch is deliberately placed above the annotation shortcut
   (§4.5), which defuses the hazard for pinned rows; `UNPINNED` rows still
   hit it — currently benign in handler paths because `purchase.py:107` calls
   `refresh_from_db()`. Add comments so a refactor doesn't reopen it.

8. **Backfill scale** — batched writes, idempotent/resumable async command, never one
   transaction (constraint §3.6).

9. **History gaps on bulk backfill.** `bulk_update` skips `HistoricalRecords`;
   through-row history starts sparse (§4.3). Accepted and stated — the audit trail
   for backfill is its ListActions.

10. **Historical prod drift is not retroactively fixable.** Pinning is prospective;
    the Phase 8 reconciliation stops caches lying, but prices already lost to stash
    re-pricing stay lost (old stash gear pins at catalog, §4.8.4). Expectations are
    set by the Phase 1 report and the pin-editing remediation path (Phase 10).
