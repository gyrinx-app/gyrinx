# Static Assets

Stylesheets, JavaScript, and image assets for the core app.

## Styles (SCSS)

Before changing styles, load the `design-system` skill. The semantic vocabulary it documents
maps to tokens defined here.

- Tokens: [core/scss/_tokens.scss](core/scss/_tokens.scss) — semantic aliases (state, action,
  surface) layered on top of Bootstrap. Prefer extending tokens over hard-coded colours,
  spacing, or font sizes.
- Entry points: `screen.scss`, `print.scss`, `styles.scss`.
- Spec: [docs/DESIGN-SYSTEM.md](../../../docs/DESIGN-SYSTEM.md)

**Don't commit generated CSS.** It is built from SCSS by `npm run css` (one-shot) or
`npm run watch` (rebuild on change), and the build outputs (e.g. `core/css/styles.css`,
`core/css/styles.css.map`) are listed in `.gitignore`. Committing CSS bypasses the build
and causes drift between source and what's served.

## JavaScript

Vanilla JS only — no framework. Use it for one-off enhancements; default to server-rendered
HTML and form submissions for behaviour. Format with `npm run js-fmt`.
