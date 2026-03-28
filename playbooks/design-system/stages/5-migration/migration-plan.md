# Migration Plan Guidelines

## Batching Rules

- **Shared includes first:** If a template include is used on N views, migrating it is one PR that fixes N views. Always migrate shared includes before views that use them.
- **Foundation as single PR:** `_tokens.scss` and Bootstrap variable overrides get their own PR (may already exist from Stage 4).
- **Component-level PRs** when a component spans many views and changes are mechanical and low-risk.
- **View-level PRs** when changes are view-specific or structural.
- **Never mix** structural refactors with cosmetic changes in the same PR.

## Plan Format

`output/migration/plan.md` must list every migration unit:

| Unit | What changes | Files affected | Views affected | Risk | Dependencies |
|------|-------------|----------------|----------------|------|--------------|
