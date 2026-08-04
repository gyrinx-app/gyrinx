# Templates

## Design System

Before any non-trivial template work, load the `design-system` skill — it is the canonical
reference for components, colours, typography, spacing, buttons, tables, forms, page shells,
and inline action menus.

- Spec: [docs/DESIGN-SYSTEM.md](../../../docs/DESIGN-SYSTEM.md)
- Live HTML reference: [core/debug/design_system.html](core/debug/design_system.html) — render at `/_debug/design-system/` to see real components in context
- Semantic colour vocabulary: [_tokens.scss](../static/core/scss/_tokens.scss)

Working rules:

- Extend `core/layouts/base.html` for full-page layouts and `core/layouts/page.html` for
  simple content pages. Don't roll a new top-level layout.
- **Use the cotton components in [gyrinx/templates/cotton/](../../templates/cotton/)
  rather than hand-writing Bootstrap.** Read the component file first — each carries its
  props and traps in a comment block at the top.

  | Instead of | Use |
  | --- | --- |
  | `<button class="btn btn-primary btn-sm">` | `<c-btn variant="primary" size="sm">` |
  | `<span class="badge text-bg-warning">` | `<c-badge variant="warning">` / `state="injured"` |
  | `<div class="alert alert-danger alert-icon">` | `<c-callout variant="danger">` |
  | `<div class="border rounded p-3">` | `<c-box>` (`compact` for `p-2`) |
  | label + widget + help + errors by hand | `<c-form.field :field="form.x" />` |
  | `{% include "core/includes/back.html" %}` | `<c-back>` |
  | a `bg-body-tertiary rounded px-2 py-2 d-flex …` bar | `class="section-header"` |

  Raw `btn btn-*` should not appear outside `gyrinx/templates/cotton/` — that is what
  `scripts/check_raw_markup.py` counts. Within the library `cotton/btn.html` owns the
  variant classes (`cotton/form/stepper.html` still writes its own and could compose
  `<c-btn>`; `btn-close` in `cotton/callout.html` is Bootstrap's dismiss control).
- Reach for an existing snippet in `core/includes/` before writing new markup. The fighter
  card lives at [core/includes/fighter_card_content_inner.html](core/includes/fighter_card_content_inner.html).
- Keep template comments sparse. Markup is mostly self-explanatory, so comment only where
  the reason for something genuinely isn't visible — a non-obvious ordering constraint, a
  workaround, a rule that will look wrong to the next reader. Don't narrate what the markup
  already says.

### Component call sites: the mistakes that fail SILENTLY

Cotton renders something plausible, djlint lints it clean, and the page returns 200 with a
control that doesn't work — so none of these show up in manual testing. Static gates
(`scripts/check_cotton.py`, `test_cotton_call_site_gates.py`) catch them; don't work around
the gate, fix the call site.

- **A filter or expression inside a `:prop` resolves to nothing.** `:url="a|default:b"` and
  `:disabled="not can_roll"` both evaluate to empty — the second ships the control
  **enabled**. Use `url="{{ a|default:b }}"` / `disabled="{% if not can_roll %}1{% endif %}"`.
  A `:prop` may only be a bare dotted path.
- **A `{% if %}` in attribute position renders as literal text**, and the browser parses the
  braces as junk attributes. `<c-btn {% if x %}disabled{% endif %}>` ships enabled.
- **A `:prop` the component doesn't declare skips escaping** — undeclared attributes go out
  through `{{ attrs }}`, which is `mark_safe`'d, so `:id="value"` is an injection hole.
- **A form passed without the colon is stringified.** `field="{{ form.x }}"` renders the
  widget to HTML; every `field.*` lookup then resolves to nothing and the field ships with
  no label, no help text and **no errors**. Always `:field="form.x"`.
- **Multi-line comments must use `{% comment %}`** — Django's `{# #}` is single-line only,
  and a multi-line one renders into the page as visible text.
- **Files in `gyrinx/templates/cotton/` are byte-significant**: dense, no trailing newline,
  excluded from djlint and `end-of-file-fixer` because a newline there renders as a stray
  space between inline elements. Don't reformat them.
- Mobile-first; responsive utilities scale up. Left-aligned content typically `col-12 col-xl-6`.
- Feedback goes in `<c-callout>`; neutral grouped content goes in `<c-box>`. Don't reach for
  `alert` classes or hand-write a bordered box. Bootstrap `card` stays reserved for fighter
  grids and equipment categories.
- Never apply `|safe` directly to user-supplied content. Sanitize first — the project ships
  the `safe_rich_text` template filter (in `core/templatetags/custom_tags.py`) for this.
  Only use `|safe` on values you control or that have already been sanitized.
- **No client-side form mutation.** Variant pickers (kind/mode switches that
  change which fields are visible, which options a `<select>` has, or which
  fields are required) are server-rendered `<a>` links pointing at the same
  view with the new state in the query string. The page reloads and the
  server returns the correct form. JS is only for enhancements that fail
  gracefully. See the "URL-Driven UI" section in
  `.claude/skills/gyrinx-conventions/SKILL.md`, and `house_rule_form.html` /
  `add_house_rule` view for the canonical example.

## Microcopy Guidelines

### Casing

Use sentence case for UI text. Title case proper nouns only.

**Proper nouns (title case):**

- Campaign
- Action
- Asset
- Gang
- Fighter
- Territory
- Resource

**Linking words (lowercase):**

- from, to, and, or, the, a, an, in, on, for, with

### Examples

| Correct | Incorrect |
|---------|-----------|
| Copy from another Campaign | Copy From Another Campaign |
| Add a Gang to this Campaign | Add A Gang To This Campaign |
| Assets and Resources | Assets And Resources |
| Copy to Campaign | Copy To Campaign |
| Create new Asset | Create New Asset |

### Button Labels

- Use action verbs: "Add", "Create", "Copy", "Remove"
- Keep labels concise: "Next", "Cancel", "Save"
- Arrow icons go after text for forward actions: "Next →"
- Arrow icons go before text for back actions: "← Back"
