# CLAUDE.md — n26/designsystem

The living component gallery at `/n26/design/`. It documents the
components; it owns none of them — they live in
`n26/core/templates/cotton/`. Two principles carry the whole app:

1. **The file you read is the file that rendered.** A demo page renders
   a template *and* prints its source; there is no second copy to
   drift.
2. **Nothing is transcribed.** A component's props are parsed at
   runtime from its own `<c-vars>` block; its documentation panel is its
   own leading `{% comment %}` block. The catalog never restates props.

Read `demos.py` (101 lines) first, then `introspect.py`.

## Adding or changing a component

1. Write the cotton template in `n26/core/templates/cotton/n26/` (or a
   directory with `index.html` plus part templates). Two things are
   mandatory because the gallery reads them: a `<c-vars … />` block
   declaring every public prop, and a leading `{% comment %}` block
   documenting the component.
2. Register it in `catalog.py` in the right `Group` — slug, tag,
   template path, summary, notes, `Part(...)` entries for
   subcomponents, `needs=(…)` for runtime dependencies. Do not restate
   props here.
3. Create `templates/designsystem/demos/<slug>/` with at least one
   `NN-name.html`. The directory name must match the catalog slug
   exactly — nothing checks this, and a mismatch silently yields a
   "No examples yet" page.
4. If the component takes domain objects, add fixed sample data to
   `sampledata.py` — real dataclasses built by the real functions, no
   database (the gallery must render on an empty database).
5. Add that context to *every* view that renders the demo — both the
   component page and the plain preview. A form built in one and
   forgotten in the other renders an empty select and looks like a
   component bug.

## Demo files

```
{# title: Solid and pill #}
{# note: Both are spellings of variant, so you can't have a solid pill. #}
{# layout: col #}
<c-ui.badge variant="solid" color="green">solid</c-ui.badge>
```

- Metadata is a run of `{# key: value #}` comments at the top: `title`,
  `note`, `layout` (`row` default, `col`, or `full` for whole screens).
- The body must be a copy-pasteable fragment: no `{% extends %}`, no
  wrapper markup a call site wouldn't have.
- One demo per axis of variation. `demos/badge/` is the shape to copy
  for a primitive; `demos/action-links/` for a composition;
  `demos/view-gang-sheet/` for a whole screen.
- Prefer rendering from a registry over writing instances out — the
  icon demo loops the icon registry, so new icons appear without the
  demo going stale.

## The `notes` register

A catalog entry's `notes` are not a description — they are the argument
for the design decision: what you would have done instead, and what
broke when you tried. Write new ones in that register.

## Traps

- Most failures here are silent by design: a missing demo directory, a
  catalog path that doesn't resolve, and an undeclared prop all render
  soft fallbacks, not errors. After any change, load the component's
  gallery page and check the props table and demos actually appear.
- A demo that raises takes the whole component page down with it.
- Print styling is its own world: read the header comment in
  `assets/print.css` before touching anything print-shaped, and use
  `printlab` (every control is a query parameter) to test it.
  `sampledata`, `printlab`, and the token pages deliberately hold no
  values that live elsewhere — tokens are read from the browser,
  geometry mirrors the stylesheet.
- The gallery depends on `n26.core`; core must never import the
  gallery.

## Comments

A comment states a constraint, an invariant, or a consequence the code
cannot show — briefly, in plain words. It must make sense to a reader
who has never seen any earlier version of this code: no people, no
tickets or PRs, no changelog narration. This app is currently the
cleanest in the repo by that rule — keep it that way. Django `{# #}`
comments are single-line only; multi-line prose uses `{% comment %}`
(a multi-line `{# #}` renders as literal page text).
