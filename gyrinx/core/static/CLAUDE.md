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

**Never commit `.css` files.** They are generated from SCSS by `npm run css` (one-shot) or
`npm run watch` (rebuild on change). The pre-commit hooks and CI will fail on committed CSS.

## JavaScript

Vanilla JS only — no framework. Use it for one-off enhancements; default to server-rendered
HTML and form submissions for behaviour. Format with `npm run js-fmt`.
