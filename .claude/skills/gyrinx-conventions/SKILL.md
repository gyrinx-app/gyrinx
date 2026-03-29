---
description: |
  Established architectural conventions and patterns for the Gyrinx Django project. Load this skill
  when working on the Gyrinx codebase to ensure consistency with existing patterns. Useful for
  feature planning, code review, architecture analysis, and any work that needs to follow the
  project's established patterns.
---

# Gyrinx Project Conventions

These are the canonical conventions for the Gyrinx project. All new code should follow these patterns. Deviations should be intentional and justified.

## Architecture Layers

- **Views** handle HTTP: forms, sessions, redirects, event logging (with `request` context)
- **Handlers** handle business logic: validation, state changes, cost operations, action creation
- **Models** encapsulate data and core logic
- **Templates** receive simple, pre-computed context — no business logic
- Views call handlers with clean domain objects, never pass `request` to handlers
- Handlers return result dataclasses, never HTTP responses

## Model Conventions

- All user-data models inherit from `AppBase` (UUID pk, owner, archive, history tracking)
- All content/game-data models inherit from `Content` (UUID pk, timestamps only)
- Use `HistoryAwareManager` as default manager (provides `create_with_user`, `bulk_create_with_history`)
- Custom QuerySets with optimization methods (e.g., `with_related_data()`, `with_fighter_data()`)
- `@cached_property` for computed values
- `db_index=True` on frequently queried fields
- Choice fields use Django enums (e.g., `FighterCategoryChoices`)

## View Conventions

- **FBVs** for form handling and complex operations, decorated with `@login_required`
- **CBVs** for list/detail pages, using `LoginRequiredMixin`
- Ownership via `get_clean_list_or_404(List, id=id, owner=request.user)` helper
- Standard form flow: validate -> `form.save(commit=False)` -> set ownership fields -> call handler -> catch `ValidationError` -> redirect with flash or re-render with error
- Redirects use `HttpResponseRedirect(reverse(...))` with flash param: `?flash=<id>#<id>`
- `safe_redirect()` for any user-provided redirect URLs
- `@transaction.atomic` on views with complex write operations
- `@traced("view_name")` for performance tracing
- `log_event()` called in views AFTER successful handler completion (includes request context)

## Handler Conventions

- Keyword-only arguments (`*` in signature) to force clarity at call sites
- Decorator stack: `@traced("operation_name")` then `@transaction.atomic`
- Return dedicated `@dataclass` result objects (never bool/dict): contains modified objects, costs, description string, created actions
- Raise `ValidationError` for business logic failures (views catch and convert to messages)
- Return `None` for idempotent no-op cases
- **Operation ordering**: Validate -> Capture before values -> Calculate deltas -> Spend/gain credits -> Create CampaignAction -> Propagate costs -> Create ListAction(s) -> Return result
- Campaign mode awareness: check `lst.is_campaign_mode`, spend credits via `lst.spend_credits()`, create `CampaignAction` alongside `ListAction`
- Cost routing: stash fighters -> `stash_delta`, regular fighters -> `rating_delta`, campaign mode -> also `credits_delta`
- Cost propagation: call `propagate_from_assignment()` or `propagate_from_fighter()` after credit spending but before ListAction creation

## Form Conventions

- `ModelForm` with `Meta` class defining fields, labels, help_texts, widgets
- Pop custom kwargs before `super().__init__()` in plain forms
- Widget classes: `form-control`, `form-select`, `form-check-input` (Bootstrap 5)
- Custom `ModelChoiceField` subclasses with `label_from_instance()` for display formatting
- `group_select()` helper for grouped select dropdowns
- Dynamic field creation in `__init__` based on instance state
- Three validation levels: field-level `clean_*` methods, form-level `clean()`, model-level `full_clean()`

## URL Conventions

- Transaction pages: `noun[-noun]-verb` (e.g., `list-archive`, `list-fighter-edit`)
- Index pages: pluralized noun (e.g., `lists`, `campaigns`)
- Detail pages: singular noun (e.g., `list`, `campaign`)
- Nested resources: `parent/<id>/child/<child_id>` (e.g., `list/<id>/fighter/<fighter_id>`)
- Names use hyphens, not underscores
- Path params: `<id>` for primary resource, `<fighter_id>`, `<skill_id>` for nested
- `kwargs=dict(...)` for view configuration parameters

## Template Conventions

- Extend `core/layouts/base.html` for full pages, `core/layouts/page.html` for simple content
- Reusable components via `{% include "core/includes/..." with key=value %}`
- Back button: `{% include "core/includes/back.html" with url=target_url text="Back Text" %}`
- Mobile-first responsive: `col-12 col-md-8 col-lg-6`
- `vstack gap-3` / `gap-5` for vertical spacing
- Button classes: `btn btn-primary btn-sm`, `btn btn-secondary btn-sm`, `btn btn-danger btn-sm`
- Link style: `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover`
- Custom template tags: `{% load custom_tags %}`, `{% safe_referer '/fallback/' %}`
- Context variable naming: plural for lists, singular for detail, `has_`/`is_`/`can_` for booleans

## Test Conventions

- `@pytest.mark.django_db` on every test function — no test classes
- Use existing fixtures from `conftest.py`: `user`, `make_user`, `content_house`, `content_fighter`, `make_list`, `make_list_fighter`, `make_campaign`, `campaign`, `list_with_campaign`
- `client.force_login(user)` for authentication
- Factory fixtures for custom data: `make_user(username, password)`, `make_list(name, **kwargs)`, `make_list_fighter(list_, name, **kwargs)`
- Direct assertions with `assert`, not `self.assertEqual`
- `pytest.raises(ValidationError, match="...")` for exception testing
- Performance testing with `CaptureQueriesContext`
- Session-level setup: `StaticFilesStorage`, `MD5PasswordHasher`, tracing off, debug off

## Cost System

- Two systems keep cached values in sync: **Facts** (pull-based, recalculates from DB) and **Propagation** (push-based, incremental deltas)
- Only ONE system should update cached values for any operation
- `Delta(delta=int, list=List)` dataclass for propagation
- Always check `_should_propagate()` guard before propagating
- `save(update_fields=[...])` for selective updates

## State Machine

- `StateMachine` descriptor on models: defines states, initial state, transitions
- API: `obj.states.current`, `obj.states.transition_to("STATE")`, `obj.states.can_transition_to("STATE")`, `obj.states.is_terminal`
- Transitions are atomic, recorded in auto-generated transition model with metadata
