# Issue #1468 — "Nominate as leader" (Death of a Leader)

Planned 2026-07-31 with Tom. Driver for closing out the promotions epic's deferred
"family D / Death of a Leader — conditional-target story"
(`promotions-epic-design.md` § Out of scope for initial ingest).

## Status correction (epic doc is stale — refresh it as part of this work)

Phases 3–5 of the promotions epic SHIPPED on main via PR #2019
(`a7b35bf4`, commits `92cd62c2` Phase 0 helper, `5622943c` Phase 2, `cdf17aaa`
Phases 3+4, `48fdc513` Phase 5, plus hardening `196fa96b`/`810498e9`/`5bf2edca`).
PR #2023 added `ContentRule.shed_on_promotion` (rules kept on promotion by default).
Already on main and reusable as-is:

- `ListFighter.promoted_content_fighter` access pointer (equipment: legacy > promotion
  > base; skills/special rules: promotion > base; statline/base cost: base only).
- `ADVANCEMENT_PROMOTION` rows with `promotion_path`/`promotion_target` FKs,
  apply/reverse, rank-based category fallback, clone/campaign-entry propagation.
- Wizard target-selection step (`PromotionTargetSelectionForm`).
- Special rules merge ⇒ **"Gang Leader" comes free from pointing at the house's Leader
  type** — no custom_rules hack (the Feb-2026 in-issue plan is obsolete; it predates all
  of this).

## Decisions (Tom, 2026-07-31)

1. **Dynamic target resolution** — new content field; one seeded generic path resolves
   targets at offer time to the gang-house's LEADER-category types. No per-house
   authoring.
2. **Offered only in campaign mode AND when the gang has no living leader** (no
   fighter currently holding LEADER category who is alive and still in the gang).
3. **Entry point: fighter action link** ("Nominate as leader", shown only when
   offerable) deep-linking into the existing advancement wizard with the path
   preselected. Wizard route remains too. Reversal = existing advancement delete.
4. **Scope**: #1468 + epic-doc refresh. Phase 6 polish and per-house ingest stay
   separate.

From the issue thread (Louis): campaign-only ✓ (decision 2), player chooses among
multiple leader types ✓ (existing target step), free (0 XP / 0 credits) ✓, must be
reversible ✓ (advancement row).

## Build plan

### Stage 1 — Content model: any-category sources + dynamic targets

`gyrinx/content/models/promotion.py`:

- `from_category`: `blank=True` ⇒ "offered to any category". Update `__str__`
  ("Any → …") and `clean()` (RELABEL must still name `to_category`; the
  from==to check only when from is set).
- New field `dynamic_targets_category` (CharField, FighterCategoryChoices, blank).
  `clean()`: only meaningful for TYPE_CHANGE; mutually exclusive with explicit
  `targets` rows (admin form enforces, like `clean_target`).
- New `resolve_targets(list_fighter)` helper: explicit `targets` if any, else
  `ContentFighter.objects.filter(house=list_fighter.list.content_house,
  category=dynamic_targets_category)` excluding stash/vehicle. All target-consuming
  sites switch to it.
- `is_available_to_fighter()`: skip category check when `from_category` blank; keep the
  docstring contract (content gate only).
- `available_promotion_paths()` (`core/forms/advancement.py:40`) SQL pre-filter becomes
  `Q(from_category=fighter.get_category()) | Q(from_category="")`, and gains the
  flow-level gates for `timing == LEADER_DEATH` paths:
  - list is `CAMPAIGN_MODE`;
  - no living leader: no fighter in the list with `get_category() == LEADER`,
    `injury_state != DEAD`, not archived, not captured/sold (check existing
    capture-state helpers at implementation time);
  - fighter has no `promoted_content_fighter` already (single-active type change);
  - `resolve_targets(fighter)` non-empty.
- Migrations: content schema migration + frozen-inline seed (0181 pattern):
  "Nominate as leader" — kind TYPE_CHANGE, from_category "", dynamic_targets_category
  LEADER, xp_cost 0, cost_increase 0, grants_skill none, rolls [], timing LEADER_DEATH,
  **rank 3** (above Champion=2, so reversal fallback ordering is right).
- Admin: expose the new field.

### Stage 2 — Flow plumbing

- Swap `path.targets.all()` reads for `resolve_targets(fighter)` in:
  `PromotionTargetSelectionForm` (`forms/advancement.py:726`), the multi-target
  gate at `forms/advancement.py:515`, `promotion_needs_target()` /
  target-integrity checks in `views/fighter/advancements.py`, and the apply handler's
  target validation (`handlers/fighter/advancement.py`).
- Roll-driven flow untouched (path has no rolls; the `len(targets) > 1` skip already
  excludes multi-target from prefill).
- Apply/reverse: no new logic expected — `effective_to_category(target)` yields LEADER
  from the chosen target's category. Verify:
  - a fighter with `xp_current == 0` can take an `xp_cost == 0` advancement (find and
    check the XP eligibility gate);
  - reversal with stacked prior promotions falls back by rank (Specialist ganger →
    nominated leader → undo ⇒ back to SPECIALIST).

### Stage 3 — Entry point (URL-driven, logic in Python)

- View computes an `offerable` flag + prebuilt wizard URL (deep link with
  `advancement_choice=promotion_{path_id}` — confirm exact `AdvancementFlowParams`
  query params). No JS.
- "Nominate as leader" action rendered with cotton components in the fighter's
  actions area (exact placement per design system; check
  `/_debug/design-system/` inline-action patterns).

### Stage 4 — Tests (extend `core/tests/test_promotion_paths.py`, matrix non-vacuity rules)

- **L1 availability**: ganger AND juve see the path in campaign mode with dead leader;
  NOT with a living leader; NOT in list-building mode; NOT when already type-changed;
  NOT when the house has no leader types.
- **L2 dynamic targets**: house with two leader types → target step offers both;
  resolution keys off the gang's house.
- **L3 apply invariants**: `category_override == LEADER`, pointer == chosen type,
  `_base_cost_int` unchanged (exact), statline from base, rating delta == 0 exactly,
  XP unchanged, new purchases price against the leader's equipment list, leader skill
  trees accessible, "Gang Leader" rule present via rules resolution.
- **L4 reverse symmetry**: pointer cleared, category falls back correctly (None, and
  SPECIALIST in the stacked case), `rating_current` restored to the exact prior value.
- **L5 entry point**: action link present/absent per the L1 conditions.
- Seed-shape test (A4 style) for the new row. Watch
  `performance_view_queries.json` (should be untouched — resolution runs on
  advancement pages, not list pages).

### Stage 5 — Doc refresh + ship

- Update `promotions-epic-design.md`: tick Phases 0/3/4 (PR #2019), note #2023, record
  this design under family D.
- `./scripts/fmt.sh`; `pytest -n auto`; manual browser test of the full nominate →
  undo loop via dev server; ship with `commit-push-pr`.

## Verify-during-implementation list (not blockers)

- Captured/sold leader semantics for the "no living leader" gate (existing helpers).
- Exact wizard deep-link parameter shape.
- The XP eligibility gate for 0-cost advancements.
- Whether `restricted_to_houses` / pack-awareness needs a carve-out in
  `resolve_targets` (catalog leaders only vs pack leader types — pack fighters are
  excluded from authored paths by `_exclude_pack_fighters`, but dynamic resolution
  queries fighters directly).
