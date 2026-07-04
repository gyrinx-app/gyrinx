# Plan — wire the classic print card into the real print-config flow (#1726)

## Where things stand

Two disconnected systems:

**Real print flow (user-facing).**
- `PrintConfig` model (`core/models/print_config.py`) — per-list, named, archivable.
  Toggles: `include_assets/attributes/stash/actions/dead_fighters`,
  `blank_fighter_cards`/`blank_vehicle_cards` (0–20), `fighter_selection_mode`
  (all/specific/none) + `included_fighters` M2M.
- `PrintConfigForm` (`core/forms/print_config.py`) + views
  (`core/views/print_config.py`): index / create / edit / delete(soft) /
  `print_config_print` → redirects to `core:list-print?config_id=…`.
- `ListPrintView` (`core/views/list/views.py:~450`) → `list_print.html` →
  `includes/list.html` with `print=True`, rendering the **web** fighter cards
  (`fighter_card.html`) styled by `print.css`; `window.print()` on load.
  It already computes the config-filtered fighter queryset
  (selection mode, dead exclusion) and the blank-card ranges.

**Classic card (new, #1726).**
- `ClassicCard`, `StatCell`, `WeaponRow`, `card_from_fighter()` + helpers live in
  `core/views/print_lab.py`. `synthetic_presets()`/`PRESET_LABELS` are lab-only.
- Rendered by `core/includes/classic_card.html` inside
  `core/debug/print_lab_sheet.html` (`.print-sheet` grid = 4 per A4, plus the
  fit-to-box JS), styled by `print_classic.css` (compiled from
  `scss/print_classic.scss`, a top-level entry → picked up by `npm run css`
  and collectstatic, no build change needed).
- Only reachable via staff/DEBUG `/_debug/print-lab/`.

Goal: a real user selects "classic cards" on a PrintConfig and prints their gang.

## Decisions (locked)

- **D1 — opt-in = `card_style` on `PrintConfig`** (`web` default / `classic`).
  The config already *is* the print settings object, so it's the natural home and
  keeps a single `list-print` URL. Persists per saved config.
- **D2 — fighter cards only.** The classic sheet renders just the fixed-size
  classic fighter cards + blank cards. The assets/attributes/actions/stash toggles
  don't apply to classic output — the form notes they're web-style-only (and can be
  visually de-emphasised when classic is selected). Stash stays out
  ("will never render classic").
- **D3 — single uniform theme for the whole sheet.** No per-card alternation.
  Add a `card_theme` field to `PrintConfig`, defaulting to **`blank`** ("Plate
  (blank)"), applied uniformly to every card on the sheet. One picker, one look.
  (Kept as a config field rather than hard-coded so the default can be changed
  without a migration, but it is deliberately *not* alternating.)

## Work breakdown

### 1. Extract the card builder into a shared, non-debug module
Move `ClassicCard`/`StatCell`/`WeaponRow`/`card_from_fighter()` + private helpers
(`_weapon_rows`, `_wargear_names`, `_gear_categories`, `_card_kind`, stat builders)
from `views/print_lab.py` into `core/print_cards.py` (name TBD). Keep
`synthetic_presets()`/`PRESET_LABELS` in the debug view. `views/print_lab.py`
re-imports from the new module (existing 31 lab tests keep passing).

### 2. Extract the sheet scaffold into a reusable partial
Pull the `.print-sheet` card loop + fit-to-box `<script>` out of
`print_lab_sheet.html` into `core/includes/classic_sheet.html`
(params: `cards`, `theme`, `show_grid`, `paged`). Both the debug lab sheet and the
new real print path `{% include %}` it. The `print_classic.css` link stays on the
page templates.

### 3. Model + form + migration
- Add `card_style` + `card_theme` (default `blank` = "Plate (blank)") to
  `PrintConfig`; makemigrations core.
- Add field(s) to `PrintConfigForm` + `form.html` (radio "Card style"; theme
  picker shown for classic). Update `card_summary()` to mention the style.

### 4. Branch the print view on card_style
In `ListPrintView`: when `print_config.card_style == "classic"`, reuse the
already-filtered `fighters_qs` to build
`cards = [card_from_fighter(f, list_obj) for f in fighters_qs]`, append the blank
classic cards (see §5), set theme, and render a classic sheet template
(extends `base_print.html`, includes `classic_sheet.html`, links `print_classic.css`).
Default/`web`/no-config → unchanged. Cleanest: switch `template_name` in the view
(`list_print_classic.html`) rather than a big `{% if %}` in the template.

### 5. Blank classic cards
`card_from_fighter` needs a fighter, so add `blank_classic_card(kind)` to the shared
module returning an empty `ClassicCard` with the right statline shape (humanoid vs
vehicle/crew) — model it on the lab's existing `blank` preset. Emit
`blank_fighter_cards` humanoid + `blank_vehicle_cards` vehicle blanks.

### 6. Static/build
No build wiring change (see above). Add a smoke test that the classic print URL
200s and references `print_classic.css`.

### 7. Tests
- `card_style=classic` config → `ListPrintView` emits `classic-card` markup,
  honours selection mode + dead-fighter exclusion, and produces the right count of
  blank cards.
- Default/omitted config → still web cards (regression guard).
- Migration applies; debug lab still works after the builder move.

### 8. UI polish
Print-config index + form: label the style; if D2 = fighter-only, note that
assets/attributes/actions/stash are web-style only. Optional "Preview classic" link.

## Risks / notes
- Fit-to-box JS must run on DOMContentLoaded *before* `window.print()` — preserve
  ordering in the real print page.
- N+1: `ListPrintView` already prefetches via `with_related_data(packs=…)`;
  confirm `card_from_fighter`'s reads (weapons/skills/rules/wargear) hit the
  prefetch cache on large gangs.
- Real vehicles/crew must map through `_card_kind`/`card_from_fighter` correctly
  (lab presets are synthetic).
- Stash explicitly excluded from classic output.
