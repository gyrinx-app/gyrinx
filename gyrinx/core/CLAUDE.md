# Core App

User-data domain: lists, fighters, campaigns, battles, assignments. The hot core of the app.

Load the `gyrinx-conventions` skill before non-trivial work — it documents the layered
architecture (views → handlers → models), form/test conventions, cost system, and state
machines.

## Models

- All core models inherit from `AppBase` ([models/base.py](models/base.py)) — UUID PK,
  `Owned`, `Archived`, `HistoryMixin`, history-aware manager. Don't subclass `models.Model`
  directly.
- Every concrete model declares `history = HistoricalRecords()` for django-simple-history.
- For state-bearing models (campaigns, battles), use [models/state_machine.py](models/state_machine.py)
  rather than rolling status fields by hand.

### Prefetch invariant

The fighter list view is the project's hottest query path. When you add a FK or M2M to
`ListFighter` (or anything fetched alongside it), you **must** update both:

1. `ListFighterQuerySet.with_related_data()` in [models/list.py](models/list.py) — the
   central prefetch method.
2. The query-count snapshot at [tests/fixtures/performance_view_queries.json](tests/fixtures/performance_view_queries.json).

Tests will fail if the snapshot drifts. If a relation isn't prefetched, the view degrades
into N+1 territory silently in dev and shows up only under load.

## Views and permissions

- Views are split by domain: `views/fighter/`, `views/campaign/`, `views/list/`, plus
  root-level views.
- The owner-or-arbitrator permission pattern (`Q(owner=user) | Q(campaign__owner=user)`) has
  a helper: `get_list_and_fighter()` in [views/fighter/permissions.py](views/fighter/permissions.py).
  Prefer it for new code. Older modules (`state.py`, `xp.py`) still inline the `Q()` and may
  be migrated when touched.
- Validate redirect targets with `safe_redirect` from [gyrinx/util.py](../util.py) whenever
  a `next=` or similar comes from user input.

## Tests

Use the canonical fixtures in [gyrinx/conftest.py](../conftest.py) — `user`, `make_user`,
`content_house`, `content_fighter`, `make_list`, `make_list_fighter`, `make_campaign`,
`campaign`, `list_with_campaign`. Read the conftest before writing fixture setup inline.

Tests are module-level pytest functions with `@pytest.mark.django_db`; no `TestCase`.

## Templates and static

Template and SCSS work has its own localized guidance — see
[templates/CLAUDE.md](templates/CLAUDE.md) and [static/CLAUDE.md](static/CLAUDE.md). Both
point at the `design-system` skill, which should be loaded before changing UI.
