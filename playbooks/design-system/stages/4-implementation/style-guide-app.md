# Living Style Guide App

## Process

### 1. Create Django App: `gyrinx/designsystem/`

- `views.py` with a single view rendering the style guide
- URL: `/design-system/` (only accessible in DEBUG mode or to staff users)
- `templates/designsystem/styleguide.html`

### 2. Style Guide Must Render

- Colour palette (swatches with hex values and token names)
- Type scale (each step rendered at its actual size)
- Spacing scale (visual boxes showing each spacing value)
- Every component in every variant and size
- Each component section includes the Django template code to use it

### 3. Live Rendering

The style guide must use the actual SCSS and component templates — not screenshots. This keeps it always in sync with the real implementation.
