# Linting Rules

## Process

### 1. Stylelint Configuration

Create `.stylelintrc.json`:

- Disallow hardcoded colour values (must use tokens)
- Disallow font-size declarations outside the defined scale
- Warn on `!important` usage
- Enforce SCSS variable naming convention (`$gy-*` prefix)

### 2. Template Linter

Create a Python script that scans Django templates for anti-patterns:

- Inline `style=""` attributes
- Hardcoded colour classes that should use the semantic system
- Component patterns that should use `{% include %}` instead of raw HTML

Output: list of violations with file, line, and suggested fix.

### 3. Documentation

Document how to run both linters in the design system spec.
