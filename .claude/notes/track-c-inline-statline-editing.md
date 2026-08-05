# Inline statline editing on the fighter admin (#1861, between C4 and the base-column drop)

## Goal

Editing a fighter type's stats happens on the fighter page, in one grid, instead
of hopping to a separate Statline page. Every new fighter type gets a statline
automatically. The twelve base stat boxes come off the admin form.

This is what unblocks dropping the twelve `<stat>_*` base columns on
`ContentFighter` and deleting `ContentFighter._legacy_statline`.

## What already exists — reuse, don't rebuild

The pack editor (`n23/core/views/pack.py`) already implements this exact UX in
the app's own UI. Four helpers are directly reusable:

| Helper | Does |
| --- | --- |
| `_get_statline_type_for_category` | category → statline type, driven by `ContentStatlineType.default_for_categories`. Raises loudly for VEHICLE / EXOTIC_BEAST rather than silently falling back to Fighter. |
| `_normalize_stat_value` | `4` → `4"`, `3` → `3+`, `2` → `+2`, per `ContentStat` flags. Also folds smart quotes. |
| `_stat_placeholder` | per-stat placeholder example for the input |
| `_create_fighter_statline` | creates the statline + its value rows from POST data |

Their only non-trivial dependency,
`AUTO_EQUIPMENT_CATEGORY_BY_FIGHTER_CATEGORY`, already lives in
`n23/content/models/equipment.py`, so moving them into the content app creates
no import cycle.

## Step 1 — extract the helpers to `n23/content/statlines.py`

Pure move; `pack.py` imports them back. Content admin must not import from
`core.views`, so they need a shared home first. Separate commit so the real
change is readable on its own.

## Step 2 — stat grid on the fighter admin form

`ContentFighterForm.__init__`:

- Resolve the statline type: the existing statline's type, else
  `_get_statline_type_for_category(instance.category)`.
- Add one `CharField` per `ContentStatlineTypeStat` of that type, ordered by
  `position`, named `stat_<type_stat_id>`, initial from the existing
  `ContentStatlineStat`, placeholder from `_stat_placeholder`.
- Reuse the smart-quote validation already in `ContentStatlineStatForm`
  (extract it to a shared validator rather than copy it).

`ContentFighterAdmin.save_related`:

- Ensure a `ContentStatline` exists, creating it with the resolved type.
- Write each submitted value through `_normalize_stat_value`, via
  `update_or_create` on `ContentStatlineStat`.
- Drop `ContentStatlineInline` — replaced by this.
- `fieldsets` to group the stats visibly.

### The variant problem, and the call I'm making

Which inputs to render depends on which statline type, which depends on
category. On a **fresh add form** the category is not yet known, so rendering a
Fighter-shaped grid and then having the admin pick VEHICLE would silently throw
away what they typed.

**Decision: stat inputs on the change form only.** The add form takes name,
category, house etc.; saving creates the statline; the admin lands on the change
form with the grid ready. That is the ordinary Django admin add-then-continue
rhythm, and it has no data-loss trap.

So: *editing* is one page. *Creating* is add → save → stats. Worth being straight
about, since the ask was "one page".

Rejected alternative: render the default type's grid on the add form and rebuild
on bound data. Recoverable only by detecting the type change and warning; more
moving parts for a case that happens once per fighter type.

### Changing statline type on an existing fighter

Values are keyed by `statline_type_stat` id, so switching type orphans the old
rows. The save path must delete rows whose type-stat is not in the new type and
create the missing ones. `ContentStatline.clean()` requires *every* stat of the
type to be present, so missing ones must be created with `-` — the same thing
`ContentStatlineAdmin.save_related` does today.

## Step 3 — take the twelve base boxes off the form

Via `fieldsets`. The columns stay on the model until the next PR. When creating
a statline for a fighter that still has base column values, seed the values from
them so nothing is lost in dev/pack data.

## Step 4 — make "every fighter type has a statline" a real invariant

Production is already at 676/676, and the pack editor creates them. The gap is
admin-created types and anything programmatic (tests, fixtures, scripts).

`post_save` on `ContentFighter`: if no statline, materialise one from the
category's type, seeded from the base columns while they exist. One exists-check
per save.

This is what makes the fallback deletable — without a total guarantee,
`ContentFighter.statline()` still needs its legacy branch.

## Step 5 — tests

- Add via admin creates a statline of the right type for the category
- Change form renders one input per stat, seeded from current values
- Saving normalises (`4` → `4+` on a target stat)
- Smart quotes rejected, naming the stat
- Editing a value moves the card of a `ListFighter` on that template
- A fighter created outside the admin still gets a statline
- Switching statline type drops orphaned values and fills the new ones
- The twelve base boxes are absent from the form

## Risks

- `ContentStatline.clean()` fails if any stat of the type is missing a row —
  the save path must always fill the full set.
- VEHICLE / EXOTIC_BEAST raise if no matching statline type is configured. That
  is deliberate (a wrong-fit fallback produces nonsense companion stats), but the
  admin needs to surface it as a form error, not a 500.
- A `post_save` that creates rows is heavier than it looks on bulk imports;
  check the content sync path (`loaddata_overwrite`) still behaves.

## Sequencing

| PR | Contents |
| --- | --- |
| B | Steps 1–5: helper extraction, admin grid, invariant, boxes off the form |
| C | Drop the twelve base columns and `_legacy_statline` |
