# Scope Document — Gyrinx Design System Playbook

## Environment

- **Repository:** `/Users/tom/code/gyrinx/gyrinx`
- **Branch:** `design-system-playbook`
- **Dev server:** `http://localhost:8000` (Django 6.0.2)
- **Bootstrap version:** 5.3.8
- **Logged in as:** admin (superuser with full data access)

## Codebase Surface Area

### Templates

- **Total template files:** 314 `.html` files
- **Primary app:** `gyrinx/core/templates/core/` (~250 templates)
- **Auth:** `gyrinx/core/templates/allauth/`, `account/`, `mfa/` (~50 templates)
- **Other:** `pages/`, `admin/`, `analytics/`, `content/` (~14 templates)

### SCSS

- **3 SCSS files:**
  - `styles.scss` — main stylesheet, Bootstrap imports, custom styles
  - `screen.scss` — screen-specific overrides (base font size: `0.875rem`)
  - `print.scss` — print-specific styles
- **Build command:** `npm run css` (sass + autoprefixer)
- **Bootstrap source:** compiled from `node_modules/bootstrap/` SCSS

### JavaScript

- **1 JS file:** `core/static/core/js/index.js` (vanilla JS)
- **Bootstrap JS:** tabs, dropdowns, tooltips, collapse (from CDN/npm)

### Layout Chain

```
foundation.html → base.html → page.html (simple pages)
                             → base_print.html (print/embed)
                             → allauth/layouts/base.html (auth pages)
```

### Template Composition

- **Deepest include chain:** 7 levels (list → fighter_card → weapons → weapon_rows → weapon_assign_name)
- **Most included template:** `core/includes/back.html` (~50 pages)
- **Key component templates:** fighter_card_content.html, fighter_card_gear.html, list_fighter_weapons.html, form_field.html

## Views Screenshotted

### Desktop (1280px) — 40 screenshots

| Category | Count | Views |
|----------|-------|-------|
| Home/General | 5 | home, lists index, campaigns index, dice, user profile |
| List Pages | 9 | detail (x2), about, notes, edit, print, new, packs, new fighter |
| Fighter Pages | 10 | edit, weapons, gear, skills, rules, xp, advancements, narrative, notes, stats, injuries |
| Campaign Pages | 9 | detail, edit, new, add-lists, packs, assets, resources, attributes |
| Pack Pages | 3 | index, detail, edit |
| Auth/Other | 4 | login, signup, account home, design system debug |

### Mobile (375px) — 3 screenshots

- Home (logged in)
- List detail (Cawdor)
- Campaign detail

**Total: 43 baseline screenshots**

## Views Not Screenshotted

These views exist but weren't captured (lower priority or require specific state):

- **Confirmation pages:** archive, delete, clone, kill, resurrect, mark-captured (~15 views)
- **Equipment sub-pages:** weapon cost edit, accessory edit, weapon profile delete, reassign (~10 views)
- **Campaign sub-pages:** action log, action outcome, battle detail/new/edit, captured fighters, sub-assets (~15 views)
- **Pack sub-pages:** permissions, activity, item add/edit/delete, weapon profiles, equipment list management (~15 views)
- **Vehicle flow:** select, crew, confirm (3 views)
- **Advancement flow:** dice choice, type select, advancement select, other, confirm (5 views)
- **Print configs:** index, form, delete (3 views)

These are mostly form/confirmation pages that share common patterns with the screenshotted views. They can be captured in Stage 1 if needed.

## Initial Observations

1. **Heavy use of Bootstrap utilities** — most styling is via utility classes (text-muted, fs-7, hstack, vstack, gap-*, etc.) rather than custom CSS
2. **Custom extensions exist:** `fs-7` (smaller font), `caps-label` (section headers), `icon-link` class
3. **Base font size is `0.875rem`** (14px) — smaller than Bootstrap's default `1rem`
4. **Print styles exist** — `print.scss` and `base_print.html` layout suggest print is a first-class concern
5. **No alerts component** — uses `border rounded p-2` callout pattern instead
6. **No modals** — all interactions are full-page navigations
7. **Fighter card is the most complex component** — deeply nested includes with multiple modes (interactive, print, compact, gear-edit)
8. **Debug toolbar visible in dev** — hidden via JS for screenshots but will appear in computed style extraction
9. **Django debug design system page exists** at `/_debug/design-system/` — already has some colour/typography reference
