# N26 templates and Cotton components

Load the `design-system`, `microcopy` and `n26-react` skills before changing an
interactive template. The component gallery instructions live in
[`../../designsystem/AGENTS.md`](../../designsystem/AGENTS.md).

## Template layout

- `n26/…` contains pages and layouts.
- `cotton/n26/…` contains edition components used as `<c-n26.foo>`. A directory
  is a namespace: `record_table/index.html` is `<c-n26.record-table>`, while
  `gang_row.html` beside it is `<c-n26.record-table.gang-row>`.
- `cotton/ui/…` contains deliberate overrides of installed kit components.
  They win because `n26.core` appears before `django_cotton_ui` in
  `INSTALLED_APPS`; reordering the apps silently reverts the overrides.

## Component contract

- Start every component with a `{% comment %}` block containing the tag, an
  example, the reason for the component and its props.
- New components must declare every public prop in `<c-vars>`. Include
  `class=""` and pass it through. The gallery reads the comment and `<c-vars>`
  block to build its documentation.
- Register each new or renamed component in `n26/designsystem/catalog.py` and
  add demos so it appears in the gallery.
- Use `<c-n26.icon>` for new or edited general-purpose interface icons. Choose
  a Lucide name from `/n26/design/c/icon/`; add `label` when adjacent text does
  not explain the icon. Bespoke edition marks and data illustrations may own
  their SVG. `core/brand_icons.py` remains the exception for brand marks.

## Silent Cotton failures

- A `{% block %}` inside a component attribute renders nothing. Use `<c-slot>`.
- Write `&amp;`, not `&`, in attributes.
- Pass form fields as `:field="form.x"`; the platform Cotton checker does not
  scan N26 templates.
- A `:prop` takes a variable or literal, not a filter, comparison or negation.
  Compute the value in the view or render cases with `{% if %}`, then inspect
  the rendered markup.
- Declare `class` in `<c-vars>` before passing it. An undeclared `class` can
  produce a second attribute that the browser drops with the component styles.
- Comments inside `<c-vars>` must contain no quote marks, apostrophes or angle
  brackets. The tokenizer can otherwise swallow later declarations and render
  the component empty.
