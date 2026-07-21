# Content-Driven Promotions — Epic Design

Unifies **#1596** (Promote to Specialist missing for Juves) and **#1467** (Promote to
Champion missing for some Prospects). Milestone #6 "Powered-up Campaigns" ("Better
promotions"). Written 2026-07-05; **revised 2026-07-21 to the RAW-faithful, single-mechanism
design** after the rules research in `promotions-rules-spec.md` (canonical — read it first).

## TL;DR — one mechanism, RAW-faithful

The rules research settled it: **every promotion is one pattern.** Category and
type-for-access change; **statline and base cost never change** ("their existing
characteristics do not change"); cost is a flat stated bump (+20/+40) or silent. #1596 and
#1467 differ only in whether the player picks among target types:

| | #1596 Juve → Specialist | #1467 Prospect → Champion |
|---|---|---|
| Category label | changes (`category_override`) | changes |
| Type-for-access (equipment / skills / special rules) | changes → target type | changes → **chosen** target |
| Statline / base cost | **never** | **never** |
| Cost | flat `cost_increase` | flat `cost_increase` (RAW: silent → 0) |
| Choice involved | usually single target | **pick 1 of ≥2** target types |

One content model expresses both: `ContentPromotionPath` with `kind = RELABEL | TYPE_CHANGE`
and 0..n `targets`. The earlier two-model / base-cost-swap design (see git history of this
note) was made before the rules were read and is retired.

## The collision to respect: `legacy_content_fighter`

There is already a **second `ContentFighter` pointer** on `ListFighter`:
`legacy_content_fighter` (`core/models/list/fighter.py:523-530`). It grants **equipment-list
access + equipment-list item costs** from another fighter — **not** statline, **not** base
cost (confirmed: `_base_cost_before_override` at `fighter.py:976-999` only reads
`content_fighter_cached.cost_int()` / `ContentFighterHouseOverride`). Gated by `can_take_legacy`
/ `can_be_legacy` (`content/models/fighter.py:231-238`), validated at `fighter.py:2557-2572`.

The promotion access pointer for #1467 is a **third** pointer that must slot in without
fighting the legacy resolvers or the content-side `Q()` filters. Kept as a **separate FK** (not
a generalised "stack") because legacy and promotion have different axes: legacy is
equipment-list-only, promotion is equipment list + skill access + special rules. Neither
touches statline or base cost. Naming trap: "legacy" is already overloaded —
`legacy_content_fighter` (this FK) vs `_legacy_statline` (`fighter.py:367`, old
hardcoded-stats format, unrelated).

---

## Data model — one content model (`content/models/promotion.py`, SHIPPED Phase 1)

`ContentPromotionPath` inherits `Content` (pack-aware); admin registered in
`content/admin.py`. See the module itself for the authoritative field list; the shape:

```python
name, kind (RELABEL | TYPE_CHANGE)
from_category                      # generic core paths (Ganger→Specialist)
source_fighter (FK, nullable)      # house-specific paths (Orlock Wrecker)
to_category (blank for TYPE_CHANGE — chosen target's category decides)
targets (M2M ContentFighter, 0..n) # the "Forge Boss or Stimmer" choice
rank                               # reversal ordinal; Meta.ordering [rank, name]
xp_cost, cost_increase             # flat — the ONLY cost impact
rolls (JSON list)                  # 2d6 totals, e.g. [2, 12]
grants_skill
advancements_threshold, timing     # guidance only — warn, don't block
restricted_to_houses (M2M)
```

- `rank` fixes the un-generalisable part: `_recalculate_category_override` becomes
  `ORDER BY rank DESC`, with a deterministic secondary key so ties never flip on content edits.
  Multiple paths can match one `(from, to)` transition (house-restricted variants — so **no**
  global unique constraint on the pair); Phase 2 must apply precedence (most-specific wins).
- `rolls` `[2, 12]` matches the rulebook (a Ganger roll of 2 **or** 12 promotes) and fixes the
  latent bug where the hardcoded config only implemented 2 (`get_initial_for_action`).
- `clean_target()` guardrail: a target may never be a stash or vehicle type.
- Family-C per-house paths (Wrecker → Road Sergeant | Arms Master, etc. — full table in the
  rules spec) are admin-authored, not seeded.

---

## The promotion access pointer (Phase 3) — access-only, three-pointer precedence

New field on `ListFighter` (name TBD — e.g. `promoted_content_fighter`): FK → ContentFighter,
null, **PROTECT** (base FK is CASCADE; cascading here would delete every unrelated promoted
`ListFighter` when a Champion content row is removed).

**RAW-faithful: the pointer is consulted for access only.** `content_fighter_cached` — the
statline/base-cost read primitive — is **NOT redefined**; statline and base cost always come
from the base fighter. The pointer feeds exactly three resolution surfaces:

| Axis | `content_fighter` (base) | `legacy_content_fighter` | promotion pointer |
|---|---|---|---|
| Statline / base cost / true identity | **always** | never | **never** |
| Equipment-list access + cost overrides | anchor (fallback) | **wins (highest)** | wins over base, loses to legacy |
| Skill-set access, special rules | anchor (fallback) | never | **wins** |
| Category label | — | — | — (carried by `category_override`, not this pointer) |

`equipment_list_fighters` (`fighter.py:727-736`) →
`[f for f in (legacy, promotion, base) if f]`.

### Mechanical surface

- **"Prefer legacy" tie-breaks** — eight near-identical blocks
  (`core/models/list/assignment.py` six resolvers ~667/~774/~840/~880/~913;
  `core/cost/pinning.py:248-256`) need a third arm: legacy > promotion > base.
  **Phase 0: extract one `_preferred_fighter_for(...)` helper** rather than patch eight sites.
- **Equipment-list `Q()` filters** need a third arm for access/dirty invalidation:
  `content/models/equipment_list.py:88-89, 154-155, 223-224`; `content/models/house.py:142-144`.
- **NOT needed under RAW-faithful** (was required by the retired cost-swap design):
  no `set_dirty()` cost arm, no base-cost delta handler, no double-count guard, no
  `cost_override` interaction, no #1826 pinning involvement. Cost is the flat
  `cost_increase` on the advancement row, summed by the existing `sq_advancement_cost_sum`.
- **Pinning note (unchanged behaviour, worth a test):** pinned equipment prices stay frozen
  across promotion; only new purchases price against the new type's list.

### Guardrail
The promotion pointer is **advancement-flow-write-only** — never a user-editable
`ModelChoiceField` (unlike `category_override`'s tiny validated enum). `clean_target()`
rejects stash/vehicle targets; keep the field out of `ListFighterEditForm.Meta.fields`.

---

## Wizard flow (URL-driven, no JS form mutation)

Reuses the existing 4-step skeleton in `views/fighter/advancements.py` (state in query string via
`AdvancementFlowParams`).

- **Relabel:** behaves like today — top-level choice → skill-select (if `grants_skill != none`)
  → confirm. No new step.
- **Type-change:** one new step, slotting where `EquipmentAssignmentSelectionForm` sits
  for "chosen equipment":
  1. Type step injects one entry per applicable `ContentPromotionPath` (kind=TYPE_CHANGE) →
     redirects to `...select?advancement_choice=promotion_{path_id}`.
  2. New `PromotionTargetSelectionForm` (`ModelChoiceField` over `path.targets`). Always routes
     through this step even for a single target (stable as admins add a 2nd later).
  3. Confirm shows "Prospect → {target.name()}" + the flat `cost_increase` and the guidance
     text (advancement threshold, timing) — warn, don't block.

---

## Choice keys & backward compatibility

- New keys mirror `equipment_chosen_{id}`: `promotion_{path.id}` (the chosen target fighter,
  where the path has one, travels as a separate query param / stored FK).
- Old rows never rewritten. `advancement_choice` is a plain CharField; history keeps
  `"skill_promote_specialist"` / `"skill_promote_champion"` (44 occurrences across 8 files) forever.
  A `resolve_promotion_choice()` helper handles both: new prefix → id lookup; the two legacy
  strings → query the **seeded** rows by `(from_category, to_category)`. Precedent:
  the `uses_mod_system` dual-path pattern (`models/list/advancement.py:127-133`).
- **New `ADVANCEMENT_PROMOTION` type constant** (stop overloading `ADVANCEMENT_SKILL`, whose
  `clean()` *requires* a skill — some promotions grant none). New FKs `promotion_path` and
  `promotion_target` (nullable, PROTECT) on `ListFighterAdvancement`.

**All hardcoded-string sites to change:** `forms/advancement.py` (`ADVANCEMENT_CONFIGS` 185-198,
`ADVANCEMENT_CHOICES` 222-233, `all_advancement_choices` 411-420, `get_initial_for_action` 434-464);
`models/list/advancement.py:262-275`; `handlers/fighter/advancement.py:281, 525-529, 554-580` (the
hierarchy → `rank`-ordered); `views/fighter/advancements.py:369-377, 423-433, 435-442, 444-464`
(→ prefix checks like existing `is_equipment_advancement`).

---

## Migrations

**Content (SHIPPED Phase 1):** `0180_add_content_promotion_path` (schema) +
`0181_seed_promotion_paths` (frozen inline seed — no app imports, for reproducibility):
Ganger→Specialist RELABEL rank 1 rolls `[2,12]` +20; Specialist→Champion TYPE_CHANGE rank 2
+40, no targets. Per-house family-C paths and per-house Champion target sets are
admin-authored post-deploy (table in the rules spec).

**Core (Phase 3):** the promotion access pointer on `ListFighter` (nullable, PROTECT); new
`ADVANCEMENT_PROMOTION` choice + `promotion_path`/`promotion_target` FKs; relax `clean()` to
allow skill-less promotion rows. No historical backfill (string-fallback resolves them).

Add the pointer to `with_related_data()` as `select_related` (plain FK, not a new prefetch)
alongside `content_fighter`/`legacy_content_fighter` (`fighter.py:313-321`). Watch
`performance_view_queries.json`.

---

## Build sequence (#1596 closeable at Phase 2)

- [ ] **Phase 0** — extract the 8-site "prefer legacy" tie-break into one helper (no behaviour
  change, ships alone, de-risks Phase 3).
- [x] **Phase 1** — `ContentPromotionPath` model (unified: kind/source/targets/threshold/timing)
  + frozen seed migration + admin. PR #1952.
- [ ] **Phase 2** — wire the advancement flow through `ContentPromotionPath` (forms/handler/
  views); generalise `_recalculate_category_override` to `rank`; `rolls`-driven 2d6 prefill.
  **Closes #1596** (admin adds a Juve→Specialist path, no code change). Cost-neutral, low risk.
- [ ] **Phase 3** — promotion access pointer on `ListFighter` (access-only: equipment
  `legacy > promotion > base`; skills/special rules `promotion > base`; statline/cost base
  only) + third-arm `Q()` filters + extend Phase 0 helper. Tests only, no UI.
- [ ] **Phase 4** — target-selection wizard step + `ADVANCEMENT_PROMOTION` row + apply/reverse.
  **Closes #1467.**
- [ ] **Phase 5** — clone / hire-transfer propagation of the pointer (`clone()`,
  `copy_attributes_to()`, `FighterCloneParams`/`hire_clone.py`, opt-out checkbox in
  `forms/list.py`). No single seam — budget real time (same gap already exists for
  `category_override`).
- [ ] **Phase 6** — special-rules display polish + campaign-log wording; per-house content
  authoring pass (family-C paths + Champion target sets, from the rules-spec table).

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
- **A4 ⭐ Seed reproduces current configs (linchpin, new, Phase 1)** — read
  `AdvancementTypeForm.ADVANCEMENT_CONFIGS["skill_promote_specialist"|"skill_promote_champion"]`
  and the shared seed constant `DEFAULT_PROMOTIONS`; assert `xp_cost` and `cost_increase`
  match **exactly**, and the config's scalar `roll` is a **member** of the seed's `rolls` (membership,
  not set-equality — deliberate: the seed's `rolls` is a superset that *adds* the missing 12). **Catches:** the Phase-2 refactor
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

### Group D — #1467 type-change — Phases 3–4 (defined now, unwritten until code exists)

- **D1 Two-target availability** — a path with two `targets`: the select step offers **both**
  target names. Assert both present. **Catches:** dual-Champion paths collapsing to one (the
  original #1467 symptom).
- **D2 ⭐ RAW cost invariant** — Prospect (base `P`) promotes to Champion target (base `C`,
  `C>P`); assert the promotion pointer is set, **`_base_cost_int == P` unchanged** and the
  statline still reads from the base fighter; rating delta `== cost_increase` exactly.
  **Catches:** the pointer bleeding into statline/base cost (reintroducing the retired
  cost-swap design), or cost applied twice.
- **D3 Keep-gear + pin frozen + access retarget** — Prospect owns weapon `W` pinned at price
  `p`; promote; assert `W` still assigned at `p`, **and** a fresh post-promotion purchase
  prices against the **target's** equipment list. **Catches:** gear loss, silent repricing, or
  access failing to follow the new type.
- **D4 Reverse symmetry** — after D2, delete the promotion: pointer cleared,
  `category_override` recomputed, rating delta reversed (flat), gear retained. **Catches:**
  asymmetric reversal.
- **D5 Single active type** — apply a second type-change; assert the decided single-active
  behaviour (pointer reflects only the latest / second is disallowed). **Catches:** accidental
  stacking that breaks the single-active reversal contract.

### Group F — Three-pointer precedence & guards — Phase 3

- **F1 Legacy > promotion > base for equipment list** — fighter with **both**
  `legacy_content_fighter` and the promotion pointer, where all three fighters define a cost
  override for the same item; assert the **legacy** price wins; remove legacy, assert the
  **promotion** price wins over base. **Catches:** the eight tie-break sites getting the
  three-way order wrong.
- **F2 Statline/base cost NEVER follow legacy or promotion** — set legacy only, then promotion
  too; assert statline + `_base_cost_int` come from the **base** fighter in every combination.
  **Catches:** either auxiliary pointer bleeding into statline/cost.
- **F3 Guard: target can't be stash/vehicle** — `clean_target()` rejects `is_stash`/vehicle
  targets *(shipped Phase 1)*; the pointer is absent from `ListFighterEditForm.Meta.fields`.
  **Catches:** the guardrail being dropped, letting a promotion turn a fighter into a stash.

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
implies D/F should eventually run with the source/target fighter supplied by a **pack** as well as
the base catalog, since promotions are pack-aware content. Out of scope until Phase 3+, but the
fixtures should be parametrizable on that axis from the start.

## Decisions (resolved with Tom, 2026-07-05; revised 2026-07-21)

1. **Kept gear on type-change → KEEP EVERYTHING.** Equipment persists (keyed to `list_fighter`,
   not type); pinned prices stay frozen; only new purchases price against the new type's list. No
   per-type equipment-legality gate is being built. (Matches RAW + FAQs.)
2. **Promotion cost → RAW-FAITHFUL FLAT `cost_increase` (revised 2026-07-21; supersedes
   "target type's base cost").** Statline and base cost never change on any promotion; the only
   cost impact is the flat, content-authored `cost_increase` on the advancement row, summed by
   the existing `sq_advancement_cost_sum`. Rationale + retired alternative:
   `promotions-rules-spec.md` § Statline & cost policy.
3. **`cost_override` + promotion → MOOT (was: warn).** Under the flat-cost design the
   advancement `cost_increase` displays regardless of a manual base-cost override — there is no
   masked jump to warn about.
4. **Re-promotion / stacking → SINGLE ACTIVE TYPE.** One type-change at a time; reversal clears
   back to the original hired type (not a prior promotion). Simplest reversal. Category relabels
   can still stack on top.
5. **Roll-12 latent bug → prepare the data in Phase 1, fix the live flow in Phase 2.** Seed
   Ganger→Specialist with `rolls=[2, 12]` as the canonical data so the wired flow can offer the
   promotion on a rolled 12. Phase 1 is inert — the live path still falls through to Willpower
   until Phase 2 reads `rolls` in `get_initial_for_action`.
6. **`can_take_legacy` / `can_be_legacy` follow promoted type → PENDING** (Tom checking the rules).
   Non-blocking for Phase 1; the validation is Phase 3. When revisited, first compare the real
   content — the choice is moot if a source type and its targets share the same legacy flags.
7. **Rating jump / "bottle-out" → DEFER (downgraded to display polish).** Gyrinx implements no
   bottle/underdog mechanics and no rating-over-time chart; gang rating is a plain sum
   (`List.rating()`). A promotion just adds its delta like any purchase. Only real work is making
   the Phase 6 campaign-log entry read sensibly.
