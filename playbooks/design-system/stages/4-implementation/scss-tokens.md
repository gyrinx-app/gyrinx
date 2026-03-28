# SCSS Tokens Implementation

## Process

### 1. Create `static/scss/_tokens.scss`

- Every token from `tokens.json` as an SCSS variable
- Organised by category with comment headers
- Bootstrap variable overrides at the top (so they take effect before Bootstrap compiles)
- Custom `$gy-` tokens below

### 2. Update the SCSS Import Chain

- `_tokens.scss` must be imported before Bootstrap's source
- Verify the compiled CSS correctly reflects the token values

### 3. Verify Nothing Breaks

- Compile SCSS
- Load 3 key pages in the browser
- Visually confirm no regressions
