# Code Improvement Checklist

This checklist is used by the automated code improvement workflow to systematically identify issues in the codebase.

## 1. Modularity

- [ ] Are functions/methods focused on a single responsibility?
- [ ] Are modules logically organized and cohesive?
- [ ] Is there clear separation of concerns?
- [ ] Are dependencies minimized and well-defined?
- [ ] Could any large functions be broken down into smaller ones?

## 2. Documentation & Comments

- [ ] Are all public functions/methods documented?
- [ ] Are complex algorithms explained with comments?
- [ ] Is the purpose of each module/class clear?
- [ ] Are edge cases and assumptions documented?
- [ ] Are TODOs and FIXMEs tracked appropriately?

## 3. Test Coverage

- [ ] Are all critical paths covered by tests?
- [ ] Are edge cases tested?
- [ ] Are error conditions tested?
- [ ] Is test coverage adequate (aim for >80%)?
- [ ] Are tests maintainable and well-organized?

## 4. Duplication & DRY

- [ ] Is there duplicated code that could be extracted?
- [ ] Are similar patterns repeated that could be abstracted?
- [ ] Are constants/magic numbers properly defined?
- [ ] Could any repeated logic be moved to utilities?

## 5. Security & Error Handling

- [ ] Are all user inputs validated and sanitized?
- [ ] Are SQL queries protected against injection?
- [ ] Are errors handled gracefully?
- [ ] Are sensitive data properly protected?
- [ ] Are authentication/authorization checks in place?
- [ ] Are redirect URLs validated with safe_redirect?

## 6. Performance

- [ ] Are database queries optimized (using select_related/prefetch_related)?
- [ ] Are appropriate database indexes in place?
- [ ] Is pagination used for large datasets?
- [ ] Are N+1 query problems avoided?
- [ ] Are expensive operations cached when appropriate?

## 7. Accessibility in Templates

- [ ] Do all images have alt text?
- [ ] Are form fields properly labeled?
- [ ] Is semantic HTML used appropriately?
- [ ] Are ARIA attributes used where needed?
- [ ] Is keyboard navigation supported?
- [ ] Are color contrasts sufficient?

## 8. Django-specific Checks

- [ ] Are Django ORM queries efficient (avoiding N+1, using select_related/prefetch_related)?
- [ ] Are model fields using appropriate types and constraints?
- [ ] Are Django signals used appropriately (not overused)?
- [ ] Are forms using Django's built-in validation?
- [ ] Is middleware ordered correctly and necessary?
- [ ] Are Django settings following best practices?
- [ ] Are custom model managers and querysets well-designed?

## 9. Code Consistency

- [ ] Are naming conventions followed consistently (PEP 8 for Python)?
- [ ] Is import ordering consistent (standard library, third-party, local)?
- [ ] Are similar operations handled in similar ways across the codebase?
- [ ] Are code patterns consistent within modules?
- [ ] Are return types and function signatures consistent?

## 10. Technical Debt

- [ ] Are there deprecated functions or libraries being used?
- [ ] Are dependencies up to date with security patches?
- [ ] Is there commented-out code that should be removed?
- [ ] Are there TODO/FIXME comments that need addressing?
- [ ] Are there opportunities to upgrade to newer Django features?
- [ ] Is there legacy code that could be modernized?
