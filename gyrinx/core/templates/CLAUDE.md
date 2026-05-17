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
- Reach for an existing snippet in `core/includes/` before writing new markup. The fighter
  card lives at [core/includes/fighter_card_content_inner.html](core/includes/fighter_card_content_inner.html).
- Use the Bootstrap 5 button classes documented in the root `CLAUDE.md` (`btn btn-primary
  btn-sm`, etc.) rather than inventing new ones.
- Mobile-first; responsive utilities scale up. Left-aligned content typically `col-12 col-xl-6`.
- Avoid `alert` classes — prefer `border rounded p-2`. Cards are reserved for fighter grids.
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
