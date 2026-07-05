# Content-Driven Promotions — Epic Design

Unifies **#1596** (Promote to Specialist missing for Juves) and **#1467** (Promote to
Champion missing for some Prospects). Milestone #6 "Powered-up Campaigns" ("Better
promotions"). Written 2026-07-05.

## TL;DR — the two issues are NOT the same fix

| | #1596 Juve → Specialist | #1467 Prospect → Champion |
|---|---|---|
| What changes | Category **label** only | The fighter **type** (`ContentFighter`) |
| Statline / base cost | Unchanged (still a Juve) | Changes (Champion is a different, dearer type) |
| Choice involved | None — single target | **Pick 1 of ≥2** Champion types |
| Handled by today's `category_override`? | ✅ label-only override suffices | ❌ override never swaps `content_fighter` |
| Handled by `ContentPromotionPath(from_category→to_category)`? | ✅ | ❌ can't say *which* Champion |

**Reject the "one fix solves both" premise** in the issue #1596 plan. #1596 is a category
*relabel* (a one-liner today; a content row after Phase 2). #1467 needs a new *fighter-type
change* primitive with target selection. Integrate them under one epic, two mechanisms.

The old plan's claim that `ContentPromotionPath` "provides the foundation for #1467" is only
half true — it generalises the relabel path, but does nothing for the type-change requirement.

## The collision to respect: `legacy_content_fighter`

There is already a **second `ContentFighter` pointer** on `ListFighter`:
`legacy_content_fighter` (`core/models/list/fighter.py:523-530`). It grants **equipment-list
access + equipment-list item costs** from another fighter — **not** statline, **not** base
cost (confirmed: `_base_cost_before_override` at `fighter.py:976-999` only reads
`content_fighter_cached.cost_int()` / `ContentFighterHouseOverride`). Gated by `can_take_legacy`
/ `can_be_legacy` (`content/models/fighter.py:231-238`), validated at `fighter.py:2557-2572`.

The new `content_fighter_override` for #1467 is a **third** pointer that must slot in without
fighting the legacy resolvers or the content-side `Q()` filters. Kept as a **separate FK** (not
a generalised "stack") because legacy is single-axis (equipment list only) and type-change is
wide (statline + base cost + skills + kit + equipment list) — collapsing them would make legacy
semantics ambiguous. Naming trap: "legacy" is already overloaded — `legacy_content_fighter`
(this FK) vs `_legacy_statline` (`fighter.py:367`, old hardcoded-stats format, unrelated).

---

## Data model — two content models (new file `content/models/promotion.py`)

Both inherit `Content` (pack-aware). Registered in `content/admin.py` following the
`ContentAdvancementEquipmentAdmin` pattern.

### `ContentPromotionCategoryPath` — generalises today's relabel (fixes #1596)

```python
name              = CharField(255)                                   # "Promote to Specialist"
from_category     = CharField(choices=FighterCategoryChoices)        # single value
to_category       = CharField(choices=ALLOWED_CATEGORY_OVERRIDES)
rank              = PositiveIntegerField(default=0)   # ordinal — replaces hardcoded Champion>Specialist>None
xp_cost           = PositiveIntegerField()
cost_increase     = IntegerField(default=0)          # flat rating bump (20 / 40 today)
rolls             = JSONField(default=list, blank=True)  # 2d6 totals, e.g. [2, 12]
grants_skill      = CharField(choices=[none|primary_random|primary_chosen|
                                       secondary_random|secondary_chosen|any_random],
                              default="primary_random")
restricted_to_houses = M2M(ContentHouse, blank=True)   # mirrors ContentAdvancementEquipment
```

- `rank` fixes the un-generalisable part: `_recalculate_category_override` becomes
  `ORDER BY rank DESC`.
- `rolls` (list, not scalar) fixes a **latent bug**: today `skill_promote_specialist` has
  `roll=2` with a comment "Also roll 12" that is **not implemented** — rolling a 12 falls through
  to the `stat_willpower` default and never selects Specialist (`get_initial_for_action`,
  `forms/advancement.py:434-464`). Confirm whether this is known/accepted before shipping.

### `ContentPromotionTypeChange` — new, for #1467

```python
source_fighter = FK(ContentFighter, related_name="promotion_sources")
target_fighter = FK(ContentFighter, related_name="promotion_targets")
xp_cost        = PositiveIntegerField()
cost_increase  = IntegerField(default=0)   # optional flat surcharge ON TOP of the live cost swap
grants_skill   = CharField(... , default="none")
# Meta.unique_together = [("source_fighter","target_fighter")]
# clean(): target != source; target.house == source.house OR target.house.generic
```

FKs to specific `ContentFighter` rows (not category enums) because Prospect/Champion are
per-house archetypes — a house's two Champion targets *are* two distinct rows. ≥2 targets is
just multiple rows with the same `source_fighter`.

---

## The `content_fighter_override` primitive + three-pointer precedence

New field: `ListFighter.content_fighter_override = FK(ContentFighter, null=True,
on_delete=PROTECT)`. **PROTECT, not CASCADE** (base FK is CASCADE) — otherwise deleting a
Champion content row would cascade-delete every unrelated promoted `ListFighter`.

**One change does most of the work** — redefine the already-pervasive read primitive:

```python
@cached_property
def content_fighter_cached(self):
    return self.content_fighter_override or self.content_fighter
```

Every site already reading `content_fighter_cached` (statline, base cost, skills, counters,
default kit, psyker access, house-additional gear) follows the promotion automatically. Risk is
confined to sites reading **raw `self.content_fighter`**.

### Precedence table

| Axis | `content_fighter` (raw) | `legacy_content_fighter` | `content_fighter_override` |
|---|---|---|---|
| Statline / base cost / category / kit / skills / counters / psyker | anchor (fallback) | **never** | **wins** |
| Equipment-list cost overrides | anchor (fallback) | **wins (highest)** | wins over base, loses to legacy |
| True identity (`__str__`, stash/vehicle checks, admin) | **anchor, never overridden** | n/a | **never** |

`equipment_list_fighters` (`fighter.py:727-736`) →
`[f for f in (legacy, content_fighter_override, content_fighter) if f]`.

### Highest mechanical surface — the "prefer legacy" tie-breaks

Eight near-identical blocks pick the legacy row on tie today; each needs a **third arm**
(prefer `content_fighter_override` row before base):
- `core/models/list/assignment.py` — six resolvers (~667, ~774, ~840, ~880, ~913)
- `core/cost/pinning.py:248-256` (`_preferred_override`)

**Phase 0: extract one `_preferred_fighter_for(...)` helper** rather than patch eight sites.

### Three-arm `Q()` dirty filters (miss one = silent stale cost)

- `content/models/equipment_list.py:88-89, 154-155, 223-224`
- `content/models/house.py:142-144`
- **`content/models/fighter.py:327-330` (`ContentFighter.set_dirty()`)** — the correctness-critical
  one: without a `Q(content_fighter_override=self)` arm, editing a Champion's `base_cost` never
  marks promoted fighters dirty → `rating_current` drifts stale forever.

### Guardrail
`content_fighter_override` is **advancement-flow-write-only** — never a user-editable
`ModelChoiceField` (unlike `category_override`'s tiny validated enum). An arbitrary
`ContentFighter` target could be a Vehicle/Stash and break `is_stash`/`is_vehicle`/ordering.
Keep out of `ListFighterEditForm.Meta.fields`.

---

## #1826 cost-pinning interaction (the biggest correctness trap)

- **Equipment costs are frozen (pinned) at acquisition** — `pin_assignment()` writes once, never
  overwrites. A promotion changing `equipment_list_fighters` order does **not** reprice
  already-owned gear; only *future* acquisitions price against the Champion's list. Default-kit
  free-by-membership items stay stable (`from_default_assignment` FK is immutable).
- **Base cost is live (pull-based Fact), not pinned** — `_base_cost_int` reads
  `content_fighter_cached.cost_int()` fresh. Setting the override makes the whole base-cost jump
  happen **automatically** from the FK swap. No `cost_increase` arithmetic needed.

**Double-counting danger:** `ListFighterAdvancement.cost_increase` is *added* on top of base cost
(`sq_advancement_cost_sum`). If a type-change row also carries `cost_increase` mirroring the
relabel convention, cost double-counts (once via live swap, once additive).

**Decision:** type-change `ADVANCEMENT_PROMOTION` rows store `cost_increase = 0`. The base jump
is the live FK swap (more correct — respects target house-override, self-heals on content edits).
Any authored surcharge is applied by the handler as a one-time delta, not stored on the row.

Handler (same before/after pattern as the async-race note, all in one transaction):
```
old_base = fighter._base_cost_before_override()
fighter.content_fighter_override = target_fighter
new_base = fighter._base_cost_before_override()
propagate_from_fighter(fighter, Delta(delta=new_base - old_base + promotion.cost_increase, list=lst))
```
Reversal re-derives symmetrically (clear override, propagate `new_base - old_base`) — no stored
delta to go stale. Guard: verify `content_fighter_override_id == promotion_type_change.target_fighter_id`
before clearing (a later unrelated promotion may have overwritten it).

**Edge case (flag, don't silently handle):** if `cost_override` (manual flat cost) is set,
`_base_cost_int` ignores `content_fighter_cached` → promotion computes `delta = 0`, no visible
cost change. Handler should reject-or-warn.

---

## Wizard flow (URL-driven, no JS form mutation)

Reuses the existing 4-step skeleton in `views/fighter/advancements.py` (state in query string via
`AdvancementFlowParams`).

- **Relabel (#1596):** behaves like today — top-level choice → skill-select (if `grants_skill != none`)
  → confirm. No new step.
- **Type-change (#1467):** one new step, slotting where `EquipmentAssignmentSelectionForm` sits
  for "chosen equipment":
  1. Type step injects one entry per `source_fighter` matching the fighter with ≥1
     `ContentPromotionTypeChange` → redirects to
     `...select?advancement_choice=promotion_type_{source_fighter_id}`.
  2. New `PromotionTargetSelectionForm` (`ModelChoiceField` over the matching rows). Always routes
     through this step even for a single target (stable as admins add a 2nd later).
  3. Confirm shows "Prospect → {target.name()}" + the **computed** live delta (not a GET-passed flat
     `cost_increase`).

---

## Choice keys & backward compatibility

- New keys mirror `equipment_chosen_{id}`: `promotion_category_{path.id}`, `promotion_type_{fighter.id}`
  (resolving at confirm to the chosen `ContentPromotionTypeChange.id`).
- Old rows never rewritten. `advancement_choice` is a plain CharField; history keeps
  `"skill_promote_specialist"` / `"skill_promote_champion"` (44 occurrences across 8 files) forever.
  A `resolve_promotion_choice()` helper handles both: new prefixes → id lookup; the two legacy
  strings → query the **seeded** category-path rows by `(from_category, to_category)`. Precedent:
  the `uses_mod_system` dual-path pattern (`models/list/advancement.py:127-133`).
- **New `ADVANCEMENT_PROMOTION` type constant** (stop overloading `ADVANCEMENT_SKILL`, whose
  `clean()` *requires* a skill — type-change often grants none). New FKs `promotion_category_path`,
  `promotion_type_change` (nullable, PROTECT).

**All hardcoded-string sites to change:** `forms/advancement.py` (`ADVANCEMENT_CONFIGS` 185-198,
`ADVANCEMENT_CHOICES` 222-233, `all_advancement_choices` 411-420, `get_initial_for_action` 434-464);
`models/list/advancement.py:262-275`; `handlers/fighter/advancement.py:281, 525-529, 554-580` (the
hierarchy → `rank`-ordered); `views/fighter/advancements.py:369-377, 423-433, 435-442, 444-464`
(→ prefix checks like existing `is_equipment_advancement`).

---

## Migrations

**Content** (after `0176_contentmod_unique_constraints`): schema for both models + admin; data
migration seeds the **two** category paths only (Ganger→Specialist rank 1 rolls `[2,12]`;
Specialist→Champion rank 2) with today's exact numbers. **No `ContentPromotionTypeChange` seeded** —
#1467 targets are house-specific, admin-authored post-deploy.

**Core** (after current head): `ListFighter.content_fighter_override` (nullable, PROTECT); new
`ADVANCEMENT_PROMOTION` choice + two promotion FKs; relax `clean()` to allow skill-less promotion
rows. No historical backfill (string-fallback resolves them).

Add `content_fighter_override` to `with_related_data()` as `select_related` (plain FK, not a new
prefetch) alongside `content_fighter`/`legacy_content_fighter` (`fighter.py:313-321`). Watch
`performance_view_queries.json`.

---

## Build sequence (#1596 closeable at Phase 2)

- [ ] **Phase 0** — extract the 8-site "prefer legacy" tie-break into one helper (no behaviour
  change, ships alone, de-risks Phase 3).
- [ ] **Phase 1** — `ContentPromotionCategoryPath` model + seed migration + admin.
- [ ] **Phase 2** — wire relabel through forms/handler/views; generalise
  `_recalculate_category_override` to `rank`. **Closes #1596** (admin adds a Juve→Specialist row,
  no code change). Cost-neutral, low risk.
- [ ] **Phase 3** — `content_fighter_override` field + `content_fighter_cached` redefinition +
  three-pointer precedence + third-arm `set_dirty()`/`Q()` filters + extend Phase 0 helper. Tests
  only, no UI.
- [ ] **Phase 4** — `ContentPromotionTypeChange` model + admin (no seed data).
- [ ] **Phase 5** — type-change wizard (new select step) + handler (live delta, `cost_override`
  guard) + `ADVANCEMENT_PROMOTION` row. **Closes #1467.**
- [ ] **Phase 6** — clone / hire-transfer propagation of `content_fighter_override`
  (`clone()`, `copy_attributes_to()`, `FighterCloneParams`/`hire_clone.py`, opt-out checkbox in
  `forms/list.py`). No single seam — budget real time (same gap already exists for
  `category_override`).
- [ ] **Phase 7** — reversal + campaign-history display polish; test reversal correctness under
  content drift.

## Test matrix (refactor harness)

**Non-vacuity rules** — every test in this matrix obeys these, else it doesn't earn its place:
- Assert a **value or state transition**, never mere existence (`assert obj.id` / `is not None`)
  and never an echo of the test's own input.
- Cost / XP / category assertions use **exact numbers**, not "> 0" or "changed".
- Each row names the **specific regression it fails on** (Catches:). If you can't name one, delete
  the test.
- **Group A is the harness**: it pins *current* behaviour and must stay green through the entire
  Phase 0→2 refactor. If a Group A test needs editing to make the refactor pass, the refactor
  changed behaviour — stop and check.

### Group A — Refactor lock / characterization (green now, stays green) — Phases 0–2

- **A1 Ganger→Specialist apply** *(exists: `test_ganger_promotion_to_specialist`)* — apply, then
  assert `category_override == "SPECIALIST"`, `get_category() == "SPECIALIST"`, skill ∈ `skills`,
  `xp_current == start-6`. **Catches:** data-driven rewrite changing the outcome category, XP debit,
  or skill grant.
- **A2 Specialist→Champion apply** *(exists)* — `category_override == "CHAMPION"`, `xp == start-12`.
  **Catches:** same, for the higher path.
- **A3 Availability filter** *(exists ×3)* — Ganger sees `skill_promote_specialist` and **not**
  `skill_promote_champion`; Specialist sees champion, **not** specialist; Champion sees neither.
  Assert on `form.fields["advancement_choice"].choices` keys. **Catches:** category restriction lost
  or inverted when moved from `restricted_to_fighter_categories` to `from_category`.
- **A4 ⭐ Seed == current configs (linchpin, new, Phase 1)** — read
  `AdvancementTypeForm.ADVANCEMENT_CONFIGS["skill_promote_specialist"|"skill_promote_champion"]`
  and the shared seed constant `DEFAULT_CATEGORY_PROMOTIONS`; assert `xp_cost`, `cost_increase`
  match exactly and each config's `roll` ∈ the seed's `rolls`. **Catches:** the Phase-2 refactor
  becoming **cost-changing** — if anyone edits a config number without the seed (or vice-versa),
  this fails. This is the single most important anti-regression test in the epic.
- **A5 Reverse cost-neutrality (new — fills a real gap)** — the existing reversal test only checks
  `category_override` clears; extend: record `list.rating_current`, apply promotion, delete it, assert
  `category_override is None` **and** `rating_current` returns to the exact pre-promotion value.
  **Catches:** reversal that clears the label but forgets to reverse the propagated cost delta.
- **A6 Multi-promotion reversal hierarchy** *(exists: `..._multiple_promotions`)* — fighter with both
  Specialist and Champion promotions; delete the Champion one; assert override falls back to
  **`SPECIALIST`** (not `None`, not `CHAMPION`). **Catches:** the Champion>Specialist ordinal
  breaking when it moves from hardcoded hierarchy to data-driven `rank`.
- **A7 Legacy-string backward compat (new, Phase 2)** — persist an advancement with the literal
  `advancement_choice="skill_promote_specialist"`, then apply and reverse via the new resolver; assert
  SPECIALIST then None. **Catches:** the refactor dropping the legacy-string fallback and orphaning
  every historical row.

### Group B — #1596 Juve acceptance — Phase 2 (xfail until the Juve path is wired)

- **B1 Juve sees the promotion** — a JUVE fighter's advancement choices include a Promote-to-Specialist
  entry. `xfail(strict)` at Phase 1, flips green when Phase 2 seeds+wires Juve→Specialist. **Catches:**
  the actual reported bug regressing.
- **B2 Juve apply is a label-only relabel** — promote a Juve (base cost `J`); assert
  `category_override == "SPECIALIST"`, **`_base_cost_int == J` unchanged** (proves relabel does *not*
  swap type/base cost), skill granted, rating delta == `cost_increase` only. **Catches:** a Juve
  promotion accidentally routed through the type-change path and mutating base cost.

### Group C — Roll→promotion prefill — Phase 2

- **C1 Roll 2 → promote** — `get_initial_for_action(action, dice_total=2)` selects the Specialist
  promotion. **Catches:** roll mapping lost in the data-driven move.
- **C2 ⭐ Roll 12 → promote (the latent-bug fix)** — `dice_total=12` selects the Specialist promotion,
  **not** `stat_willpower`. `xfail(strict)` now (documents the current bug), flips green when `rolls`
  drives the prefill. **Catches:** the "Also roll 12" gap reopening.

### Group D — #1467 type-change — Phases 3–5 (defined now, unwritten until code exists)

- **D1 Two-target availability** — Prospect with two `ContentPromotionTypeChange` rows: the select
  step offers **both** target names. Assert both present. **Catches:** dual-Champion paths collapsing
  to one (the original #1467 symptom).
- **D2 ⭐ Apply cost = target base cost** — Prospect (base `P`) → Champion (base `C`, `C>P`); assert
  `content_fighter_override == champion_cf`, **`_base_cost_int == C`** (target's, not `P`), rating
  delta `== C-P`, and the `ADVANCEMENT_PROMOTION` row's `cost_increase == 0`. **Catches:** cost not
  following the type swap, or a stray additive surcharge.
- **D3 Keep-gear + pin frozen** — Prospect owns weapon `W` pinned at price `p`; promote; assert `W`
  still assigned, its resolved cost still `p` (pin unchanged), **and** a fresh post-promotion purchase
  prices against the Champion's equipment list. **Catches:** gear loss or silent repricing of owned kit.
- **D4 Reverse symmetry** — after D2, delete the promotion: `content_fighter_override is None`,
  `_base_cost_int == P`, rating delta reversed, gear retained. **Catches:** asymmetric reversal.
- **D5 `cost_override` warns, doesn't silently no-op** — promote a fighter with `cost_override` set;
  assert a warning is returned **and** the promotion still applies. **Catches:** the silent zero-cost
  promotion (decision #3).
- **D6 Single active type** — apply a second type-change; assert the decided single-active behaviour
  (override reflects only the latest / second is disallowed). **Catches:** accidental stacking that
  breaks the single-active reversal contract.

### Group E — Cost-integrity guards — Phases 3–7

- **E1 ⭐ Reverse-under-drift (protects decision #2)** — apply type-change; **then edit the target's
  `base_cost` in content**; then reverse; assert net `rating_current` vs the pre-promotion baseline is
  **exactly 0**. **Catches:** anyone reintroducing a stored additive `cost_increase` — a stored delta
  would leave a non-zero residue after drift; the live re-derive nets to zero.
- **E2 `set_dirty` third arm** — promote fighter into Champion type; edit that Champion's `base_cost`;
  assert the promoted `ListFighter` is marked dirty / `rating` recomputes. **Catches:** the missing
  `Q(content_fighter_override=self)` arm → silent permanent stale rating.

### Group F — Three-pointer precedence & guards — Phase 3

- **F1 Legacy > override > base for equipment list** — fighter with **both** `legacy_content_fighter`
  and `content_fighter_override`, where all three fighters define a cost override for the same item;
  assert the **legacy** price wins; remove legacy, assert the **override** price wins over base.
  **Catches:** the eight tie-break sites getting the three-way order wrong.
- **F2 Statline/base cost follow override, not legacy** — set only `legacy_content_fighter`; assert
  statline + `_base_cost_int` come from the **base** fighter (legacy is equipment-only). Then set
  `content_fighter_override`; assert statline + base cost now follow the **override**. **Catches:**
  legacy accidentally bleeding into statline, or override failing to.
- **F3 Guard: target can't be stash/vehicle** — `ContentPromotionTypeChange.clean()` rejects a
  target whose `is_stash`/`is_vehicle`; and `content_fighter_override` is absent from
  `ListFighterEditForm.Meta.fields`. **Catches:** the guardrail being dropped, letting a promotion
  turn a fighter into a stash.

### Group G — Phase 1 unit tests (write now, with the model + seed)

- **G1** `__str__` renders `"{name} ({from} → {to})"` — assert the exact string. **Catches:** admin
  changelist rendering by object id/ctype instead of a readable label (cf. #1942).
- **G2** `clean()` rejects `from_category == to_category` (ValidationError). **Catches:** nonsensical
  self-promotions.
- **G3** `clean()` rejects a `to_category` outside `ALLOWED_CATEGORY_OVERRIDES` (e.g. `STASH`).
  **Catches:** a promotion targeting a non-overridable category, which `validate_category_override`
  would later reject at apply time.
- **G4** default `Meta.ordering` returns lower `rank` first (Specialist rank 1 before Champion rank 2)
  — build two rows, assert queryset order. **Catches:** the reversal hierarchy losing its data source.
- **G5** `is_available_to_fighter()` — a GANGER-sourced path is available to a Ganger, **not** to a
  Juve; a `restricted_to_houses`-scoped path is hidden from a fighter of another house. **Catches:**
  restriction logic that Phase 2 will depend on.
- **G6** (= A4) seed constant matches `ADVANCEMENT_CONFIGS`, per above. Written in the content test
  module now since the constant exists at Phase 1.

**Cross-cutting axis (note for later):** the balance-sheet harness (memory: catalog-vs-pack matrix)
implies D/E/F should eventually run with the source/target fighter supplied by a **pack** as well as
the base catalog, since promotions are pack-aware content. Out of scope until Phase 3+, but the
fixtures should be parametrizable on that axis from the start.

## Decisions (resolved with Tom, 2026-07-05)

1. **Kept gear on type-change → KEEP EVERYTHING.** Equipment persists (keyed to `list_fighter`,
   not type); pinned prices stay frozen; only new purchases price against the new type's list. No
   per-type equipment-legality gate is being built.
2. **Type-change cost → TARGET TYPE'S BASE COST.** The jump rides the live FK swap only; the
   `ADVANCEMENT_PROMOTION` row stores `cost_increase = 0`. No authored surcharge knob. Still needs
   the danger comment + reversal-under-drift test so nobody re-adds an additive `cost_increase`
   and double-counts.
3. **`cost_override` + promotion → WARN, let user decide.** Don't block, don't silently clear; warn
   that the manual override masks the promotion's cost change and let the user clear it.
4. **Re-promotion / stacking → SINGLE ACTIVE TYPE.** One type-change at a time; reversal clears
   back to the original hired type (not a prior promotion). Simplest reversal. Category relabels
   can still stack on top.
5. **Roll-12 latent bug → FIX IT.** Seed Ganger→Specialist with `rolls=[2, 12]` so a rolled 12
   correctly offers the promotion (today it falls through to Willpower). Part of Phase 1 seed.
6. **`can_take_legacy` / `can_be_legacy` follow promoted type → PENDING** (Tom checking the rules).
   Non-blocking for Phase 1; the validation is Phase 3. When revisited, first compare the real
   content — the choice is moot if a source type and its targets share the same legacy flags.
7. **Rating jump / "bottle-out" → DEFER (downgraded to display polish).** Gyrinx implements no
   bottle/underdog mechanics and no rating-over-time chart; gang rating is a plain sum
   (`List.rating()`). A promotion just adds its delta like any purchase. Only real work is making
   the Phase 7 campaign-log entry read sensibly.
