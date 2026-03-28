# Colour Audit

Cross-cutting colour analysis across 48 view audits, SCSS source, and template grep results.

---

## 1. SCSS Source Colours

### Bootstrap Variable Overrides (in `styles.scss`)

These 10 values replace Bootstrap's defaults and define the entire Gyrinx palette:

| Variable   | Hex       | Bootstrap Default | Purpose              |
|------------|-----------|-------------------|----------------------|
| `$blue`    | `#0771ea` | `#0d6efd`         | Primary              |
| `$indigo`  | `#5111dc` | `#6610f2`         | Indigo (unused in UI)|
| `$purple`  | `#5d3cb0` | `#6f42c1`         | Purple (unused in UI)|
| `$pink`    | `#c02d83` | `#d63384`         | Pink (unused in UI)  |
| `$red`     | `#cb2b48` | `#dc3545`         | Danger               |
| `$orange`  | `#ea5d0c` | `#fd7e14`         | Orange (unused in UI)|
| `$yellow`  | `#e8a10a` | `#ffc107`         | Warning              |
| `$green`   | `#1a7b49` | `#198754`         | Success              |
| `$teal`    | `#1fb27e` | `#20c997`         | Teal (unused in UI)  |
| `$cyan`    | `#10bdd3` | `#0dcaf0`         | Info                 |

All overrides shift colours darker/more saturated than Bootstrap defaults.

### Custom CSS Colour References

| Location                         | Colour Value                    | Notes                              |
|----------------------------------|---------------------------------|------------------------------------|
| `.color-radio-input:checked`     | `rgba(13, 110, 253, 0.5)`      | Hardcoded Bootstrap blue, NOT `$blue` override |
| `.color-radio-input:focus`       | `rgba(13, 110, 253, 0.25)`     | Same hardcoded Bootstrap blue      |
| `.img-link-transform:hover`      | `rgba(0, 0, 0, 0.2)`           | Shadow colour                      |
| `.errorlist`                     | `var(--bs-danger)`              | Uses CSS variable (correct)        |
| `.flash-warn` keyframe           | `var(--bs-warning-bg-subtle)`   | Uses CSS variable (correct)        |
| `.table-group-divider`           | `var(--bs-border-color)`        | Uses CSS variable (correct)        |

**Issue:** The `.color-radio-input` selectors use hardcoded `rgba(13, 110, 253, ...)` which is Bootstrap's default `$blue` (`#0d6efd`), not Gyrinx's override (`#0771ea`). These should use `var(--bs-primary-rgb)` instead.

### Inline Style Colours in Templates

| Template                        | Inline Style                                               | Count |
|---------------------------------|------------------------------------------------------------|-------|
| `index.html`                    | `linear-gradient(rgba(0,0,0,0.1), rgba(0,0,0,0.7))`      | 1     |
| `campaign.html`                 | `border-color: {{ group.colour }}; border-width: 2px; opacity: 0.5` | 1 |
| `campaign_lists.html`           | `border-color: {{ group.colour }}`                         | 1     |
| `campaign.html` + related       | `background-color: {{ value.colour }}` (10px, 8px, 16px dots) | ~12 |
| `color_radio_option.html`       | `background-color: {{ widget.color }}`                     | 1     |
| `design_system.html`            | `background:{{ hex }}`                                     | ~10   |

Dynamic colour dots use three different sizes (8px, 10px, 16px) for the same concept.

---

## 2. Bootstrap Colour Class Usage (from template grep)

### Background Classes

| Class Pattern               | Occurrences | Views Using           | Purpose                         |
|-----------------------------|-------------|----------------------|---------------------------------|
| `bg-primary`                | ~5          | stash, gear, skills  | Stash credits badge, skill badge|
| `bg-secondary`              | ~15         | many                 | Status badges, cost badges, pack badges |
| `bg-success`                | ~5          | campaign, injuries   | Active state, campaign status   |
| `bg-danger`                 | ~8          | fighter cards, injuries | Dead state badge              |
| `bg-warning`                | ~12         | fighter cards, injuries | Injured/captured state badge  |
| `bg-info`                   | ~3          | list invitations     | Invitation badge/button         |
| `bg-body-secondary`         | ~20         | section headers      | Section header bar background   |
| `bg-primary-subtle`         | ~2          | pack detail          | Count badge inside button       |
| `bg-secondary-subtle`       | ~3          | list detail          | Fighter group background        |
| `bg-warning-subtle`         | ~25         | statlines, debug     | Stat highlight, card headers    |
| `bg-danger-subtle`          | ~5          | fighter cards, debug | Dead fighter card header        |
| `bg-info-subtle`            | ~2          | skills edit          | Special category card header    |
| `bg-success-subtle`         | 0           | (unused)             | --                              |
| `bg-warning bg-opacity-10`  | ~2          | design system, archive | Warning container background  |

### Text-Background Classes (Bootstrap 5.3 pattern)

| Class                | Occurrences | Views Using                    |
|----------------------|-------------|--------------------------------|
| `text-bg-primary`    | ~12         | XP badges, credits badges, home |
| `text-bg-secondary`  | ~8          | cost badges, counter badges    |
| `text-bg-success`    | ~5          | campaign status, advancement   |
| `text-bg-warning`    | ~3          | advancement cost, pending      |
| `text-bg-danger`     | 0           | (not used)                     |
| `text-bg-info`       | ~2          | invitation button              |
| `text-bg-light`      | ~3          | attribute value badges         |
| `text-bg-dark`       | ~1          | design system only             |

### Text Colour Classes

| Class                | Template Files | Total Occurrences | Purpose                     |
|----------------------|----------------|-------------------|-----------------------------|
| `text-muted`         | ~50            | ~120+             | De-emphasised metadata      |
| `text-secondary`     | ~30            | ~60+              | De-emphasised metadata      |
| `text-danger`        | ~15            | ~30               | Error text, destructive     |
| `text-warning`       | ~3             | ~5                | Warning text, email warning |
| `text-success`       | 0              | 0                 | (unused in templates)       |
| `text-info`          | 0              | 0                 | (unused in templates)       |
| `text-light`         | ~2             | ~3                | Hero text                   |
| `text-dark`          | ~3             | ~5                | Badge text contrast         |
| `text-body`          | ~2             | ~3                | Print badge text            |
| `text-body-secondary`| 0              | 0                 | (unused despite being the BS5.3 recommended replacement for text-muted) |

### Link Colour Classes

| Class                | Template Files | Total Occurrences | Purpose                     |
|----------------------|----------------|-------------------|-----------------------------|
| `link-secondary`     | ~15            | ~40               | Edit actions, reset links   |
| `link-danger`        | ~10            | ~25               | Delete/archive/remove       |
| `link-primary`       | ~8             | ~15               | Add/create actions          |
| `link-success`       | ~2             | ~4                | Enable toggle               |
| `link-warning`       | ~2             | ~3                | Sell action                 |
| `link-light`         | ~1             | ~2                | Hero username link          |
| `link-info`          | 0              | 0                 | (unused)                    |

### Alert Classes

| Class                | Template Files | Total Occurrences | Purpose                     |
|----------------------|----------------|-------------------|-----------------------------|
| `alert-danger`       | ~15            | ~20               | Error messages              |
| `alert-warning`      | ~12            | ~19               | Destructive confirmations   |
| `alert-info`         | ~8             | ~11               | Informational callouts      |
| `alert-secondary`    | ~3             | ~4                | XP info bars                |
| `alert-success`      | ~2             | ~2                | Flash messages, sell confirm|
| `alert-primary`      | 0              | 0                 | (unused)                    |

### Border Colour Classes

| Class                | Template Files | Total Occurrences | Purpose                     |
|----------------------|----------------|-------------------|-----------------------------|
| `border-danger`      | ~8             | ~12               | Error containers            |
| `border-warning`     | ~6             | ~8                | Warning containers, debug   |
| `border-info`        | ~1             | ~1                | Info container (list_archive)|
| `border-primary`     | 0              | 0                 | (unused)                    |
| `border-secondary`   | 0              | 0                 | (unused)                    |

---

## 3. Semantic Colour Mapping

### Primary Actions (Blue `#0771ea`)

| Pattern               | Context                              |
|-----------------------|--------------------------------------|
| `btn-primary`         | Submit, search, create, add          |
| `btn-outline-primary` | Add item, filter dropdown            |
| `text-bg-primary`     | XP badges, credits badges            |
| `bg-primary`          | Stash credits badge, skill badges    |
| `link-primary`        | Add/create action links              |
| `bg-primary-subtle`   | Count badges inside buttons          |

### Secondary (Grey)

| Pattern                  | Context                           |
|--------------------------|-----------------------------------|
| `btn-secondary`          | Edit, print, overflow dropdown    |
| `btn-outline-secondary`  | Filter dropdowns, clear search    |
| `text-bg-secondary`      | Cost badges, counter badges, status |
| `bg-secondary`           | Cost badges (old pattern), packs  |
| `text-secondary`         | De-emphasised text                |
| `text-muted`             | De-emphasised text (duplicate!)   |
| `link-secondary`         | Edit actions, reset links         |
| `bg-body-secondary`      | Section header backgrounds        |
| `bg-secondary-subtle`    | Fighter group backgrounds         |

### Success (Green `#1a7b49`)

| Pattern               | Context                              |
|-----------------------|--------------------------------------|
| `btn-success`         | Start campaign, confirm advancement  |
| `text-bg-success`     | Campaign "In Progress", advancement count, staff badge |
| `bg-success`          | Active fighter state                 |
| `link-success`        | Enable toggle buttons                |

### Danger (Red `#cb2b48`)

| Pattern               | Context                              |
|-----------------------|--------------------------------------|
| `btn-danger`          | End campaign                         |
| `btn-outline-danger`  | Remove/unsubscribe                   |
| `text-danger`         | Error messages, destructive actions  |
| `bg-danger`           | Dead fighter state badge             |
| `bg-danger-subtle`    | Dead fighter card header             |
| `link-danger`         | Delete/archive/remove links          |
| `border-danger`       | Error containers                     |
| `alert-danger`        | Error alerts                         |

### Warning (Yellow `#e8a10a`)

| Pattern                  | Context                           |
|--------------------------|-----------------------------------|
| `text-bg-warning`        | Pending badge, cost override badge, advancement cost |
| `bg-warning`             | Injured state badge, captured badge |
| `bg-warning-subtle`      | Modified stat highlights, captured/injured card headers |
| `text-warning`           | Trophy icon, email warning        |
| `link-warning`           | Sell action                       |
| `border-warning`         | Warning containers, debug         |
| `alert-warning`          | Destructive confirmations         |

### Info (Cyan `#10bdd3`)

| Pattern               | Context                              |
|-----------------------|--------------------------------------|
| `btn-info`            | Invitations button                   |
| `text-bg-info`        | Invitations button                   |
| `bg-info`             | Invitation badge                     |
| `bg-info-subtle`      | Special skill category header        |
| `alert-info`          | Informational callouts               |
| `border-info`         | Info container                       |
| `link-underline-info` | `.tooltipped` class underline        |

---

## 4. Inconsistencies

### 4.1 `text-muted` vs `text-secondary` (Critical)

The most widespread inconsistency. Both classes produce grey de-emphasised text. Bootstrap 5.3 deprecated `text-muted` in favour of `text-body-secondary`, but neither migration has happened.

| Usage                  | `text-muted`     | `text-secondary`  |
|------------------------|------------------|--------------------|
| Last edit timestamps   | Yes              | No                 |
| Empty states           | Yes (some)       | Yes (some)         |
| Owner metadata         | Yes              | No                 |
| Pack summaries         | No               | Yes                |
| Campaign descriptions  | No               | Yes                |
| Activity metadata      | Yes              | No                 |
| Section labels         | Yes (caps-label) | Yes (group headers)|
| Design system debug    | No               | Yes (preferred)    |

**Total usage:** `text-muted` ~120 occurrences vs `text-secondary` ~60 occurrences.

### 4.2 Badge Pattern: `bg-*` vs `text-bg-*`

Two different patterns for the same purpose. `text-bg-*` is Bootstrap 5.3's recommended approach as it automatically sets contrast text colour.

| Pattern         | Occurrences | Views                              |
|-----------------|-------------|------------------------------------|
| `text-bg-*`     | ~30         | XP, credits, home, advancement     |
| `bg-*` (old)    | ~25         | Injuries, captured, skills, stash, campaign status |

Mixed within the same view: `fighter_card_cost.html` uses `text-bg-secondary bg-secondary` (redundant double-class).

### 4.3 Alert Usage vs Convention

CLAUDE.md says "Avoid `alert` classes -- use `border rounded p-2` instead." But alerts are used in 30+ locations:

- `alert-danger`: 20 occurrences across 15 files
- `alert-warning`: 19 occurrences across 12 files
- `alert-info`: 11 occurrences across 8 files

The alternative pattern (`border border-{colour} rounded p-2 text-{colour}`) is used in only ~8 files. Both patterns coexist for the same purpose.

### 4.4 Inline Dynamic Colours

Colour dots for campaign groups/attributes use inline `style="background-color: {{ value.colour }}"` at three different sizes:

- **16px**: Campaign attributes value cards
- **10px**: Campaign group headers, resource group headers
- **8px**: Campaign lists attribute badge dots

These should be standardised to a single size with a CSS class.

### 4.5 Hardcoded Colour Values

| Location                     | Value                        | Should Be                      |
|------------------------------|------------------------------|--------------------------------|
| `.color-radio-input:checked` | `rgba(13, 110, 253, 0.5)`   | `rgba(var(--bs-primary-rgb), 0.5)` |
| `.color-radio-input:focus`   | `rgba(13, 110, 253, 0.25)`  | `rgba(var(--bs-primary-rgb), 0.25)` |
| Hero gradient                | `rgba(0,0,0,0.1/0.7)`       | Acceptable (generic dark overlay) |

### 4.6 Missing Semantic Consistency

Same concept, different colours:

- **Remove action**: `link-danger` (advancements) vs `link-secondary` (advancement remove link)
- **Empty state text**: `text-muted` (most views) vs `text-secondary` (pack detail, campaigns, design system)
- **Content empty state**: `text-center text-secondary` (pack detail) vs left-aligned `text-muted` (most views)
- **Activity metadata**: `text-muted` (pack detail) vs `text-secondary` (pack detail content empty state) -- different classes on the same page

---

## 5. Colour Palette Summary

### Colours Actually Used in UI

| Semantic Role         | Hex       | Source Variable | CSS Variable           |
|-----------------------|-----------|-----------------|------------------------|
| Primary               | `#0771ea` | `$blue`         | `--bs-primary`         |
| Secondary             | Bootstrap default | -- | `--bs-secondary`       |
| Success               | `#1a7b49` | `$green`        | `--bs-success`         |
| Danger                | `#cb2b48` | `$red`          | `--bs-danger`          |
| Warning               | `#e8a10a` | `$yellow`       | `--bs-warning`         |
| Info                  | `#10bdd3` | `$cyan`         | `--bs-info`            |

### Colours Overridden but Not Directly Used

| Variable   | Hex       | Notes                                |
|------------|-----------|--------------------------------------|
| `$indigo`  | `#5111dc` | Only affects Bootstrap's internal colour map |
| `$purple`  | `#5d3cb0` | Only affects Bootstrap's internal colour map |
| `$pink`    | `#c02d83` | Only affects Bootstrap's internal colour map |
| `$orange`  | `#ea5d0c` | Only affects Bootstrap's internal colour map |
| `$teal`    | `#1fb27e` | Only affects Bootstrap's internal colour map |

These overrides change the colour swatches on the design system debug page but are not used in any UI pattern. They could be removed to simplify the palette, or retained for future use.

---

## 6. Consolidation Recommendation

### Proposed Semantic Colour Tokens

Create a `_variables.scss` partial with `$gy-` prefixed semantic tokens:

```scss
// Semantic colour tokens
$gy-text-muted:        var(--bs-secondary-color);  // Replace both text-muted and text-secondary
$gy-surface-section:   var(--bs-secondary-bg);     // Section header bars
$gy-surface-group:     var(--bs-secondary-bg-subtle); // Fighter groups
$gy-surface-highlight: var(--bs-warning-bg-subtle);   // Modified stat highlights

// Action colours (already handled by Bootstrap semantics)
$gy-action-primary:    var(--bs-primary);     // Add, create, submit
$gy-action-edit:       var(--bs-secondary);   // Edit, secondary actions
$gy-action-destroy:    var(--bs-danger);      // Delete, remove, archive
$gy-action-enable:     var(--bs-success);     // Enable, start, confirm
$gy-action-warn:       var(--bs-warning);     // Sell, caution

// State colours
$gy-state-active:      var(--bs-success);     // Active/alive fighter
$gy-state-injured:     var(--bs-warning);     // Injured/captured fighter
$gy-state-dead:        var(--bs-danger);      // Dead fighter

// Dot indicator size
$gy-dot-size:          10px;                  // Standardise colour dots
```

### Migration Steps

1. **Unify `text-muted` and `text-secondary`**: Pick one class (recommend `text-body-secondary` for BS5.3 forward-compat) and replace all ~180 occurrences. Short-term: create a `$gy-text-muted` CSS custom property and a `.gy-text-muted` class.

2. **Standardise badge pattern**: Replace all `bg-*` badge usage with `text-bg-*`. Affects ~25 occurrences across injuries, captured state, skills, stash, campaign status, and cost badges.

3. **Migrate alerts to bordered containers**: Replace `alert alert-danger` with `border border-danger rounded p-2 text-danger` (8 files for error_message display). Keep `alert-warning` for confirmation dialogs. Keep `alert-info` for prominent informational callouts.

4. **Standardise colour dot size**: Create `.gy-dot` class with `width: 10px; height: 10px; display: inline-block; border-radius: 50%` and replace all inline-style colour dots.

5. **Fix hardcoded colour values**: Replace `rgba(13, 110, 253, ...)` in `styles.scss` with `rgba(var(--bs-primary-rgb), ...)`.

6. **Remove unused colour overrides**: Consider removing `$indigo`, `$purple`, `$pink`, `$orange`, `$teal` overrides since they are not referenced in any UI pattern. Or keep them but document they are "available but unused."

7. **Create empty state pattern**: Standardise on `text-body-secondary` with consistent alignment (left-aligned, not centred) and size (no `small` class unless in a dense context like a table).
