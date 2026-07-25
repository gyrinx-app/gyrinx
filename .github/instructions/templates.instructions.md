---
applyTo: "**/*.html"
---

# Reviewing Django templates

## Prefer the cotton components

UI primitives live in `gyrinx/templates/cotton/` and are invoked as HTML tags. Read
the component file before commenting on a call site — each one carries its props
and traps in a comment block at the top.

| Instead of | Use |
| --- | --- |
| `<button class="btn btn-primary btn-sm">` | `<c-btn variant="primary" size="sm">` |
| `<span class="badge text-bg-warning">` | `<c-badge variant="warning">` or `state="injured"` |
| `<div class="alert alert-danger alert-icon">` | `<c-callout variant="danger">` |
| `<div class="border rounded p-3">` | `<c-box>` (`compact` for `p-2`) |
| label + widget + help + errors by hand | `<c-form.field :field="form.x" />` |
| `{% include "core/includes/back.html" %}` | `<c-back>` |
| a `bg-body-tertiary rounded px-2 py-2 d-flex …` bar | `class="section-header"` |

Adding raw markup for one of these patterns should be questioned — the
`check-raw-markup` hook fails the build when the count rises. Converting nearby
markup while editing a template is welcome but not mandatory.

Raw `btn btn-*` should not appear outside `gyrinx/templates/cotton/` — that is exactly
what the ratchet counts. Inside the library, `cotton/btn.html` owns the variant classes;
`cotton/form/stepper.html` still writes its own and could compose `<c-btn>` instead, and
the `btn-close` in `cotton/callout.html` is Bootstrap's dismiss control, not a variant.

## Component call-site mistakes that fail SILENTLY

These are the reason the static gates exist. In every case cotton renders something
plausible, djlint lints it clean and the page returns 200 with a control that does
not work — so they will not show up in manual testing.

- **A filter or expression inside a `:prop` resolves to nothing.**
  `:url="a|default:b"` and `:disabled="not can_roll"` both silently evaluate to
  empty — the second ships the control **enabled**. Use interpolation instead:
  `url="{{ a|default:b }}"`, `disabled="{% if not can_roll %}1{% endif %}"`.
  A `:prop` may only be a bare dotted path.
- **A `{% if %}` in attribute position renders as literal text.**
  `<c-btn {% if x %}disabled{% endif %}>` does not error; the braces land in the
  markup as junk attributes and the control ships enabled.
- **A `:prop` the component does not declare skips escaping.** Undeclared
  attributes go out through `{{ attrs }}`, which is `mark_safe`'d — `:id="value"`
  is an attribute-injection hole. Declared props are autoescaped and safe.
- **A form object passed without the colon is stringified.** `field="{{ form.x }}"`
  renders the widget to HTML, after which every `field.*` lookup resolves to
  nothing and the field ships with no label, no help text and **no errors**. Always
  `:field="form.x"`.

## Other template rules

- **Multi-line comments must use `{% comment %}`.** Django's `{# #}` is
  single-line only; spread over two lines it is not a comment and the whole block,
  delimiters included, renders into the page as visible text.
- **Component files are byte-significant.** Files in `gyrinx/templates/cotton/` are
  hand-formatted, dense, and end with no trailing newline — a newline there is
  emitted verbatim and collapses to a rendered space between adjacent inline
  elements. The directory is excluded from djlint and `end-of-file-fixer` so this
  survives; do not suggest reformatting them. See
  `.claude/notes/cotton-whitespace-and-toolchain-decisions.md`.
- **No client-side form mutation.** Variant pickers are server-rendered links with
  the state in the query string, not JS that rewrites the form.
- **`|safe` never touches user content.** Use `safe_rich_text`.
- One `<h1>` per page; heading levels do not skip. Use `.h3`/`.h5` to change size.
- Icons are hyphenated Bootstrap Icons (`bi-pencil`, not `bi bi-pencil`) and
  decorative ones need `aria-hidden="true"`. Icon-only controls need an accessible
  name.
- Badges use `text-bg-*`; `bg-*` alone is deprecated and fails dark-mode contrast.
- `fs-7` for small text (not `.small`); `text-secondary` for de-emphasis (not
  `text-muted`).
