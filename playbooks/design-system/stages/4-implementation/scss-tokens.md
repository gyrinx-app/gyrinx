# SCSS Tokens Implementation

## Process

### 1. Create `static/scss/_tokens.scss`

- Semantic `$gy-` tokens that alias Bootstrap variables
- Organised by category with comment headers
- Reference comments for typography, spacing, and layout conventions

### 2. Update the SCSS Import Chain

- `_tokens.scss` is imported AFTER Bootstrap's `utilities/api` (tokens are semantic aliases, not variable overrides)
- Bootstrap variable overrides (colours, `$card-cap-bg`, etc.) go before the Bootstrap imports in `styles.scss`
- Verify the compiled CSS correctly reflects the token values

### 3. Verify Nothing Breaks

- Compile SCSS
- Load 3 key pages in the browser
- Visually confirm no regressions
