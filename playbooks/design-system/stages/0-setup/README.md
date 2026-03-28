# Stage 0: Setup

## Purpose

Validate the environment, establish scope, and take baseline screenshots of every view.

## Execution Model

Interactive — requires human input.

## Steps

### 1. Validate Repository Access

- Confirm the Gyrinx repo is cloned and accessible
- Identify the project root directory
- Check git status is clean (or note uncommitted changes)
- Identify the current branch

### 2. Map the Codebase Structure

- Find all Django template files (`.html` in template directories)
- Find all SCSS files and their import structure
- Find all static JS files
- Find `package.json` and identify the SCSS build command
- Find Django URL configuration and map URL patterns to views to templates
- **Produce:** `output/scope/template-map.md` listing every template, its URL (if any), and its includes

### 3. Validate the Dev Server

- Start the Django dev server (or confirm it's running)
- Confirm it's accessible via browser
- Confirm test data is present by hitting a known populated URL
- Record the base URL (e.g., `http://localhost:8000`)

### 4. Compile SCSS

- Run the npm SCSS build to ensure compiled CSS is current
- Note the build command for future use

### 5. Enumerate All Visitable Views

From the URL map, produce a list of every distinct URL that can be visited:

- For authenticated views, note the login flow
- For views requiring specific data (e.g., a fighter ID), identify suitable test data IDs
- For views with multiple states (tabs, filters), note each state as a separate screenshot target
- **Produce:** `output/scope/view-inventory.md`

### 6. Take Baseline Screenshots

- Visit every URL in the view inventory
- Take a full-page screenshot at 1280px width (desktop)
- Take a mobile screenshot at 375px width for responsive views
- Save to `output/screenshots/baseline/{view-name}-desktop.png` and `{view-name}-mobile.png`
- For multi-state views: `{view-name}-{state}-desktop.png`

### 7. Produce Scope Document

Write `output/scope.md` summarising:

- Number of templates found
- Number of views screenshotted
- Any views that couldn't be reached and why
- SCSS file structure
- Bootstrap version confirmed
- Initial observations (e.g., "print.scss exists, suggesting print styles need consideration")

## Exit Criteria

- [ ] `output/scope/template-map.md` exists and lists all templates
- [ ] `output/scope/view-inventory.md` exists and lists all visitable URLs
- [ ] `output/screenshots/baseline/` contains a screenshot for every view
- [ ] `output/scope.md` exists with the summary
- [ ] Dev server is confirmed accessible

## Human Checkpoint

Present the scope document and screenshot count. Ask:
> "Are there any views, states, or areas I've missed?"
