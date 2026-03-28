# Design System Playbook — Summary

## What was done

Stages 0–5 of the design system playbook were executed:

1. **Setup** — 314 templates mapped, 51 baseline screenshots, Bootstrap 5.3.8 confirmed
2. **Per-View Audit** — 48 views audited across 6 parallel agents, 6,302 lines of analysis
3. **Cross-Cutting Audit** — 7 dimension reports (colour, typography, spacing, components, icons, layout, custom CSS) + summary
4. **Design System Spec** — 236-line compressed spec, tokens.json, detailed section files
5. **Implementation** — `_tokens.scss`, `.alert-icon` CSS class, comprehensive living style guide at `/_debug/design-system/`, checkbox form field template, template linter script
6. **Migration** — 188+ template files migrated across all phases

## Key Statistics

| Metric | Before | After |
|--------|--------|-------|
| `text-muted` occurrences | ~242 | 0 |
| Badge `bg-*` (old format) | ~77 | 0 |
| `.small` class usage | ~233 | 0 (deprecated, use `fs-7`) |
| Icon `bi bi-*` format | ~22 | 0 |
| `bi-check-circle` / `bi-plus-circle` | ~30 | 0 |
| Feedback patterns | 13 variants | 1 (`alert alert-icon`) |
| Unused `{% load allauth %}` | ~78 | 0 |
| Template linter errors | n/a | 0 |
| Template linter warnings | n/a | 12 (advisory) |

## Design Decisions Made

| Decision | Rationale |
|----------|-----------|
| `text-secondary` over `text-muted` | Bootstrap 5.3 recommendation, clearer semantics |
| `fs-7` over `.small` | 0.35px difference not worth two classes |
| `alert alert-icon` for all feedback | Unified icon layout with flexbox, dismissible or not |
| `btn-success` for form submit | Green = create/save/confirm; blue = navigate/open |
| `btn-primary` for all toolbar buttons | No `btn-success` in toolbars; lifecycle actions are separate primary buttons |
| `bg-body-tertiary` for section headers | Matches card-header lightness, lighter than `bg-body-secondary` |
| Cards only for fighter grids | Everything else uses `border rounded p-3` |
| `py-2` on section header bars | Enough vertical space for btn-sm actions |
| `px-2` under section header bars | Content aligns with heading text |
| `lighten($secondary, 15%)` in light mode | Softer grey for de-emphasised text |
| Checkbox-first in forms | Override `field.html` for Bootstrap `form-check` pattern |

## Files Created

| File | Purpose |
|------|---------|
| `gyrinx/core/static/core/scss/_tokens.scss` | Semantic `$gy-*` design tokens |
| `gyrinx/core/templates/core/includes/alert.html` | Alert component include |
| `gyrinx/core/templates/core/includes/_alert_inner.html` | Alert inner template |
| `gyrinx/core/templates/core/includes/empty_state.html` | Empty state component include |
| `gyrinx/templates/django/forms/field.html` | Override for checkbox-first form rendering |
| `scripts/lint_templates.py` | Template linter for design system conventions |
| `docs/DESIGN-SYSTEM.md` | Permanent copy of design system spec |
| `.markdownlint-cli2.mjs` | Updated to ignore playbook output files |

## Remaining Work

- **Extract section header bar as include** — used ~18 times inline, but action content varies too much for a simple include without Django template blocks
- **Dead CSS removal** — ~147 unused generated responsive utility classes identified in audit
- **Icon accessibility** — 97.8% of icons lack `aria-hidden="true"`
- **Visual regression tooling** — before/after screenshot comparison automation
- **Print styles audit** — `print.scss` and `zoom: 50%` approach needs separate review

## How to Maintain

1. **Design system page** — `/_debug/design-system/` is the living reference. Update it when patterns change.
2. **DESIGN-SYSTEM.md** — `docs/DESIGN-SYSTEM.md` is the spec. Keep the Updates table current.
3. **Template linter** — run `python scripts/lint_templates.py` to check for regressions. 0 errors expected.
4. **SCSS tokens** — `_tokens.scss` documents semantic conventions as comments. Update when adding new tokens.
