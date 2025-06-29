# Bootstrap Usage Guide

This guide establishes consistent patterns for using Bootstrap 5 classes throughout the Gyrinx codebase.

## Core Principles

1. **Mobile-first**: Design for mobile, scale up to desktop
2. **Prefer utility stacks**: Use `hstack`/`vstack` over `d-flex` for most layouts
3. **Consistent spacing**: Use gap utilities instead of margin classes within stacks
4. **Minimal card usage**: Reserve cards primarily for fighter cards in list grids
5. **Semantic HTML**: Use appropriate HTML elements with Bootstrap utilities

## Layout Patterns

### Horizontal and Vertical Stacks

**DO**: Use `hstack` and `vstack` for simple layouts
```html
<div class="vstack gap-2">
  <div class="hstack gap-2">
    <span>Label:</span>
    <span>Value</span>
  </div>
</div>
```

**DON'T**: Use `d-flex` for simple layouts
```html
<!-- Avoid this pattern -->
<div class="d-flex flex-column">
  <div class="d-flex flex-row">
    ...
  </div>
</div>
```

**EXCEPTION**: Use `d-flex` only for complex responsive layouts
```html
<!-- OK for responsive behavior -->
<div class="d-flex flex-column flex-md-row align-items-start align-items-md-center">
  ...
</div>
```

### Spacing

**DO**: Use gap utilities on stacks
```html
<div class="vstack gap-2">
  <div>Item 1</div>
  <div>Item 2</div>
</div>
```

**DON'T**: Use margin classes inside stacks
```html
<!-- Avoid this pattern -->
<div class="vstack gap-2">
  <div class="mb-2">Item 1</div>  <!-- Redundant margin -->
  <div>Item 2</div>
</div>
```

**EXCEPTION**: Use `mb-0` on headings to remove default margins
```html
<h2 class="mb-0">Title</h2>
```

### Standard Header Pattern

For list/campaign detail pages:
```html
<div class="vstack gap-0 mb-2">
  <!-- Title row with status badges -->
  <div class="hstack gap-2 mb-2 align-items-start align-items-md-center">
    <div class="d-flex flex-column flex-md-row flex-grow-1 align-items-start align-items-md-center gap-2">
      <h2 class="mb-0">Page Title</h2>
      <div class="ms-md-auto">
        <span class="badge bg-success">Active</span>
      </div>
    </div>
  </div>
  
  <!-- Metadata row -->
  <div class="d-flex flex-column flex-sm-row row-gap-1 column-gap-2 align-items-sm-center">
    <div class="text-secondary">
      <i class="icon"></i> Metadata
    </div>
  </div>
</div>
```

## Component Usage

### Cards

**DO**: Use cards for fighter cards in list grids
```html
<div class="card">
  <div class="card-header p-2">
    <div class="hstack gap-2">
      ...
    </div>
  </div>
  <div class="card-body">
    ...
  </div>
</div>
```

**DON'T**: Use cards for general content sections
```html
<!-- Avoid using cards for non-fighter content -->
<!-- Use simple divs with borders instead -->
<div class="border rounded p-3">
  <h3>Section Title</h3>
  <p>Content...</p>
</div>
```

### Buttons

All buttons should use the small size for consistency:

- Primary actions: `btn btn-primary btn-sm`
- Secondary actions: `btn btn-secondary btn-sm`
- Danger actions: `btn btn-danger btn-sm`
- Outline variants: `btn btn-outline-secondary btn-sm`

```html
<button class="btn btn-primary btn-sm">Add Fighter</button>
<button class="btn btn-secondary btn-sm">Edit</button>
<a href="#" class="btn btn-outline-secondary btn-sm">View Details</a>
```

### Messages and Alerts

**DO**: Use simple text for informational messages
```html
<p class="text-secondary">No fighters in this list yet.</p>
<div class="text-muted">Optional helper text</div>
```

**DON'T**: Use Bootstrap alerts for simple messages
```html
<!-- Avoid for simple messages -->
<div class="alert alert-info">
  No fighters in this list yet.
</div>
```

**DO**: Use bordered divs for important callouts
```html
<div class="border rounded p-2 text-secondary">
  <i class="icon"></i> Important information here
</div>
```

### Links

Use consistent link styling:
```html
<a href="#" class="link-secondary link-underline-opacity-25 link-underline-opacity-100-hover">
  Link text
</a>
```

## Responsive Patterns

### Responsive Column Classes

Both grid systems are acceptable for different use cases:

- `g-col-12 g-col-md-6`: CSS Grid (for grid layouts)
- `col-12 col-md-6`: Flexbox Grid (for row/column layouts)

### Responsive Utilities

Use responsive utility classes for different screen sizes:

```html
<!-- Stack on mobile, inline on larger screens -->
<div class="d-flex flex-column flex-sm-row gap-2">
  ...
</div>

<!-- Hide on mobile, show on medium and up -->
<div class="d-none d-md-block">
  ...
</div>
```

## Common Patterns

### Form Groups
```html
<div class="vstack gap-3">
  <div>
    <label for="name" class="form-label">Name</label>
    <input type="text" class="form-control" id="name">
  </div>
</div>
```

### Action Button Groups
```html
<div class="hstack gap-2">
  <button class="btn btn-primary btn-sm">Save</button>
  <button class="btn btn-secondary btn-sm">Cancel</button>
  <div class="ms-auto">
    <button class="btn btn-danger btn-sm">Delete</button>
  </div>
</div>
```

### Empty States
```html
<div class="text-center py-5">
  <p class="text-secondary mb-2">No items found</p>
  <a href="#" class="btn btn-primary btn-sm">Add First Item</a>
</div>
```

## Migration Checklist

When updating existing templates:

1. Replace `d-flex` with `hstack`/`vstack` where appropriate
2. Remove redundant margin classes inside stacks
3. Ensure all buttons use `btn-sm`
4. Replace `alert` divs with simpler text or bordered divs
5. Add consistent `p-2` padding to card headers
6. Use gap utilities instead of individual margins
7. Apply responsive utility classes for mobile-first design

## Testing

After making Bootstrap changes:

1. Test on mobile viewport (375px)
2. Test on tablet viewport (768px)
3. Test on desktop viewport (1200px)
4. Verify interactive elements are touch-friendly
5. Check for consistent spacing and alignment