---
name: sql-performance
description: Inspect the SQL cascade of Gyrinx Django pages with the Debug Toolbar and guard meaningful N+1 fixes with query-growth tests. Load after creating or materially changing a database-backed page, view, queryset, or repeated template component, and when diagnosing duplicate or slow SQL.
---

# SQL performance

Check the query shape of a database-backed page before calling the work complete. The aim is to catch query growth
caused by the new path while its data flow is still familiar. Do not turn the check into an open-ended cleanup of
unrelated, pre-existing queries.

## Exercise a representative page

Load the `dev-server` skill, start the worktree server, and use its one-click `agent` login link for the exact page:

```bash
./scripts/dev.sh
.codex/run.sh manage agent_login_url '/path/to/page/?variant=value'
```

Use local data that exercises the page's repeated structures: fighters, cards, assignments, campaign gangs,
authoring entries, or whatever the template loops over. An empty state cannot expose a per-row cascade. Check the
important URL-driven variants when they render meaningfully different data.

Load the final page at least twice. Treat the first request as cache warm-up. If the query count still moves, reload
until two consecutive requests agree, then use the stable request in the checks below. The toolbar's **History** panel
can switch between recent request snapshots, including requests before a redirect.

## Read the SQL panel

The toolbar starts collapsed in Gyrinx. Open the corner handle, then select **SQL**; the detailed panel loads on
demand. If the response is JSON or an HTML fragment without a `<body>`, inspect the full page that triggers it or use
`CaptureQueriesContext`, because the toolbar is only inserted into full HTML pages.

Start with these signals:

1. Note total queries and total SQL time as context. There is no project-wide good query count, and local timings are
   noisy. A new page at 60 queries is not automatically worse than one at 20.
2. Look for **similar** groups: the same raw SQL shape executed with different parameters. A group that follows the
   number of rendered objects is the clearest N+1 signal.
3. Look for **duplicate** groups: the exact same SQL and parameters executed again. These often indicate repeated
   property, context, permission, or template work.
4. Scan the timeline for a long run of same-coloured queries and for individual queries that dominate SQL time. The
   chart shows query order and each query's share of SQL time; it does not show idle gaps in the whole request.
5. Expand a suspicious query with `+`. Read the first frame in this repository, plus any template context, to find
   the loop or property that caused it. The SQL comment names the controller and route where available.

The similar and duplicate totals count every query in a repeated family, not just the extra executions. Repetition
is a lead rather than proof: session and permission checks may be bounded, while an N+1 can vary enough to escape the
grouping heuristic.

Test the scaling question directly: if the page rendered more of the repeated object, would this query family grow
with it? Compare a small and larger local case when the answer is unclear. Query growth with collection size matters
more than the absolute total from one request.

## Inspect from a command line

Do not open a separate Django shell after a browser request and expect `connection.queries` to contain that request.
The query log belongs to the current process and connection, and Django clears it when a request starts. A new
`manage shell` therefore sees only SQL executed by that shell.

For a command-line-only check, make the page request inside the same shell process and capture it explicitly:

```python
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

client = Client()
client.force_login(get_user_model().objects.get(username="agent"))
with CaptureQueriesContext(connection) as captured:
    response = client.get("/path/to/page/")

response.status_code, len(captured), captured.captured_queries
```

This is a fresh test-client request, not the browser's most recent load. It is useful for counts and raw SQL but does
not provide the toolbar's similar and duplicate groups, timeline, or stack traces. Prefer the toolbar for the real
browser path. If browser automation is unavailable, retain its authenticated cookie jar, extract the request ID from
the page's toolbar markup, and request
`/__debug__/render_panel/?request_id=<id>&panel_id=SQLPanel` from the running server. That reads the toolbar snapshot
for the actual page request; importing the toolbar's default in-memory store from another shell process does not.

## Fix the source of growth

Put related-object loading at the queryset boundary that owns the page:

- Use `select_related()` for forward foreign-key and one-to-one data used during rendering.
- Use `prefetch_related()` or a tailored `Prefetch()` for reverse and many-to-many collections.
- Prefer a named custom QuerySet method when the same render shape has more than one caller.
- Pass templates prepared data. Do not hide database access inside a template tag or a property called from a loop.

Fetch only what the page consumes. A large unconditional prefetch can replace many small queries with excessive work.
Reload the same representative state and confirm the repeated family is gone or bounded and that the page still
renders correctly.

Use **Expl** only after the cascade is bounded and one individual `SELECT` is still slow. In this project's
PostgreSQL toolbar it runs `EXPLAIN ANALYZE`, so it executes the selected query again. **Sel** also reruns the query.
Do not use either action for writes or for a query whose execution has side effects. An execution plan can diagnose a
slow query or missing index; it does not diagnose N+1 growth.

## Keep a regression test when it earns one

Add a focused query-growth test when the change fixes an N+1, introduces a repeated rendering path, or depends on a
non-obvious prefetch. Use `CaptureQueriesContext` around the real `client.get()` and compare stable counts with less
and more repeated data. Assert that growth stays flat or within the small constant that the feature intentionally
adds; accept a lower count after cache warming.

Avoid exact whole-page query counts by default. They are brittle when unrelated middleware or page features change
and can miss the property that matters. Existing examples:

- `n23/core/tests/test_crew.py::_stable_query_count` stabilises one-shot lazy work before comparing page renders.
- `test_crew_page_opponent_fighter_count_does_not_raise_query_count` grows the repeated collection and requires a flat
  count.
- `n23/core/tests/test_equipment_sets.py::test_active_sets_add_no_per_fighter_queries_on_list_page` compares a plain
  baseline with the feature and allows only constant overhead.

The test suite disables the Debug Toolbar, so captured counts measure application behaviour rather than toolbar work.
For ad hoc callable-level diagnostics, `gyrinx.query.capture_queries()` is available, but a page-level regression
should exercise the view and rendered template together.

## Report the check

In the handoff or PR, name the URL and representative data shape, give the stable query total and repeated-group
counts, and say what changed after any fix. Name the regression test when one was added. If browser tooling was not
available and only `CaptureQueriesContext` was used, describe that accurately rather than claiming a toolbar review.
