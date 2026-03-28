# Cross-View Audit: Feedback, Messaging, Cards & Callouts

This is a supplementary audit focused on how the app communicates feedback to users — success messages, errors, warnings, and informational callouts — and how cards and container patterns are used.

## 1. Flash Messages (Django Messages Framework)

**Location:** Rendered in `core/layouts/base.html` (line 131-144) and duplicated in `allauth/layouts/base.html`.

**Pattern:** `alert alert-{tag} alert-dismissible fade show` at the top of the content container, above all page content.

| Django Tag | CSS Class | Icon | Notes |
|------------|-----------|------|-------|
| `success` | `alert-success` | None | Most common — used after redirects from POST views |
| `error` | `alert-danger` | None | |
| `warning` | `alert-warning` | None | |
| `info` | `alert-info` | None | |
| `debug` | `alert-secondary` | None | |

**Inconsistencies:**

- **No icons on flash messages** — contrast with inline callouts which always use icons
- **Position is always top-of-page** — success messages after adding equipment appear far from the relevant fighter card
- Flash messages are the **only place** where `alert-success` is used (other than one inline case in equipment sell)

---

## 2. Inline Error Patterns (4 distinct approaches)

### Pattern A: `border border-danger rounded p-2 text-danger` (preferred by design system)

Used for `error_message` context var on equipment/pack add pages.

| File | Content |
|------|---------|
| `list_fighter_gear_edit.html` | `<strong>Error:</strong> {{ error_message }}` |
| `list_fighter_weapon_edit.html` | Same |
| `list_fighter_weapons_accessories_edit.html` | Same |
| `pack_fighter_default_weapons_add.html` | Same |
| `pack_fighter_default_gear_add.html` | Same |
| `pack_fighter_equipment_list_weapons_add.html` | Same |
| `pack_fighter_equipment_list_gear_add.html` | Same |
| `campaign_add_lists.html` | With `bi-exclamation-triangle` icon (unique) |

### Pattern B: `alert alert-danger` (Bootstrap alert)

Used for the same `error_message` var AND for form errors — inconsistent with Pattern A.

| File | Error Source | Icon |
|------|-------------|------|
| `list_fighter_stats_edit.html` | `error_message` | None |
| `list_fighter_weapons_edit.html` | `error_message` | `bi-exclamation-triangle` |
| `list_fighter_assign_delete_confirm.html` | `error_message` | `bi-exclamation-triangle-fill` |
| `list_fighter_advancement_other.html` | `form.non_field_errors` | None |
| `list_fighter_advancement_type.html` | `form.non_field_errors` | None |
| `list_fighter_advancement_dice_choice.html` | `form.non_field_errors` | None |
| `list_attribute_edit.html` | `form.errors` (entire dict!) | None |
| `battle_edit.html` | `form.non_field_errors` | `bi-exclamation-triangle` |
| `allauth/elements/fields.html` | Form-level errors | None |

### Pattern C: `text-danger small` or `text-danger fs-7` (inline field error)

Used near individual form fields in multi-field forms.

| File | Variant |
|------|---------|
| `campaign_copy_to.html` (6 instances) | `text-danger small` |
| `campaign_copy_from.html` (6 instances) | `text-danger small` |
| `pack_permissions.html` | `text-danger` (no size class) |
| `list_fighter_counters_edit.html` | `text-danger fs-7` |

### Pattern D: `invalid-feedback d-block` (Bootstrap validation)

Used via `core/includes/form_field.html` shared include and in manual field rendering.

Files: `form_field.html`, `advancement_skill_form.html`, `list_fighter_stats_edit.html`, `list_fighter_edit.html`, `list_fighter_narrative_edit.html`, `change_username.html`, and many campaign form includes.

**Summary:** The same `error_message` context variable is rendered with Pattern A on 7 pages and Pattern B on 3 pages. Form errors use Pattern B, C, or D depending on the template. One page (`list_attribute_edit.html`) renders `form.errors` (the entire dict including field errors) inside `alert-danger`, which is redundant when field errors are also shown inline.

---

## 3. Warning Patterns (5 distinct approaches)

### Pattern A: `alert alert-warning` (most common — 19 instances)

Used for destructive action confirmations and cautionary notes.

Sub-variants:

- **With `alert-heading` h4** — campaign remove pages (remove list, remove asset type, remove resource type, etc.)
- **Without heading** — simpler warnings (campaign start/end, fighter mark-captured, advancement warnings)
- **With `p-2 fs-7`** — compact inline warning (advancement skill form)
- **Icons vary:** `bi-exclamation-triangle`, `bi-exclamation-triangle-fill`, or none

### Pattern B: `border border-warning rounded p-3 bg-warning bg-opacity-10`

Multi-paragraph warning with structured content (list_archive, pack default assignment remove).

### Pattern C: `border border-warning rounded p-3 bg-warning-subtle`

Conflict detection boxes (campaign copy-to/from). Uses `text-warning-emphasis` heading.

### Pattern D: `bg-warning-subtle text-warning-emphasis rounded p-2 small`

JS-toggled compact warning (pack equipment list zero-cost items). Hidden by default with `d-none`.

### Pattern E: `border border-warning rounded p-3` (no background)

Campaign add-lists pack confirmation prompt.

---

## 4. Info Callout Patterns (4 distinct approaches)

### Pattern A: `alert alert-info` (11 instances)

Action-log notices, empty states, advancement info. Icon: usually `bi-info-circle`.

### Pattern B: `border rounded p-2 text-secondary`

Subtle inline notes (fighter state edit, remove injury). Icon: `bi bi-info-circle me-1`.

### Pattern C: `border rounded p-2` (no colour)

Neutral container for empty state (campaign battles).

### Pattern D: `p.text-muted.small` with icon

Inline text notes in battle views.

---

## 5. Card Usage Summary

### Legitimate card uses (per design system convention: "cards only for fighters in grids")

| Use | Card Classes | Where |
|-----|-------------|-------|
| Fighter display | `card g-col-12 g-col-md-6 g-col-xl-4` | `fighter_card_content.html` |
| Equipment categories | `card g-col-12 g-col-md-6` | Weapons/gear edit pages |
| Allauth panels | `card col-12 col-md-8 col-lg-6` | Auth forms |

### Questionable card uses (could be `border rounded p-*` instead)

| Use | File | Notes |
|-----|------|-------|
| Stats edit form | `list_fighter_stats_edit.html` | `card` with `card-body` only |
| Injury state display | `list_fighter_state_edit.html` | `card` with `card-body` only |
| Campaign action outcome | `campaign_action_outcome.html` | Info display |
| Campaign resource modify | `campaign_resource_modify.html` | Current amount display |
| Campaign asset transfer | `campaign_asset_transfer.html` | Current holder display |
| Campaign filter form | `campaign_actions.html` | Filter controls |
| User profile | `user.html` | User info panel |
| Advancement dice cards | `advancement_dice_choice.html` | **Only cards with `shadow-sm`** |
| Lore/Notes TOC sidebar | `list_about.html`, `list_notes.html` | `nav card card-body` pattern |

### Card body padding inconsistencies

| Padding | Used On |
|---------|--------|
| `p-0` | Fighter card (interactive) |
| `p-0 p-sm-2` | Fighter card sections, skills/rules edit |
| `p-0 p-sm-2 pt-2` | Fighter card stash, fighter card gear |
| `p-0 px-sm-2 py-sm-1` | Gear edit categories |
| `p-2` | Pack equipment categories |
| `card-body` (default) | Stats edit, state edit, campaign info cards |
| `py-2 px-2` | Weapon detail edit card |

---

## 6. Container Patterns (non-card)

| Pattern | Purpose | Frequency |
|---------|---------|-----------|
| `border rounded p-3` | Grouped content (preferred by design system) | ~10 pages |
| `border rounded p-2` | Compact inline container | ~5 pages |
| `bg-body-secondary rounded px-2 py-1` | Section header bar | ~20 instances |
| `border border-danger rounded p-2 text-danger` | Inline error box | 8 pages |
| `border border-warning rounded p-3` + bg variants | Warning callout | 5 pages |
| `border border-info rounded p-3 bg-info bg-opacity-10` | Info callout | 1 page (list_archive) |

---

## 7. Empty State Patterns (4 distinct approaches)

| Pattern | Used For | Example |
|---------|----------|---------|
| `text-muted fst-italic` "None" | Fighter card table cells | Skills, Rules, Gear with no value |
| `text-muted` "No X added yet." | Lore/notes tabs and pages | With optional edit link |
| Unstyled `<p>` or `<div>` | Home/user/list empty states | No consistent styling |
| `alert-info` | Campaign captured fighters | Only 1 instance |

---

## 8. Recommended Consolidations

1. **Error display:** Standardise on Pattern A (`border border-danger rounded p-2 text-danger`) for all inline errors. Remove `alert alert-danger` usage for `error_message`.
2. **Warning display:** Standardise on `alert alert-warning` for simple warnings and `border border-warning rounded p-3` with appropriate background for complex/structured warnings.
3. **Info callouts:** Standardise on `alert alert-info` for prominent notes and `border rounded p-2 text-secondary` for subtle notes.
4. **Flash messages:** Add icons to match inline callout conventions. Consider whether success messages should appear closer to the action.
5. **Cards:** Migrate non-fighter-grid card uses to `border rounded p-3` per the documented convention.
6. **Empty states:** Create a unified empty-state component with consistent styling.
7. **Icons:** Standardise: `bi-exclamation-triangle` for warnings, `bi-x-circle` for errors, `bi-info-circle` for info, `bi-check-circle` for success.
