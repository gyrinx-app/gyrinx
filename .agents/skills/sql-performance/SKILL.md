---
name: sql-performance
description: Inspect the SQL cascade of Gyrinx Django pages with the Debug Toolbar and guard meaningful N+1 fixes with query-growth tests. Load after creating or materially changing a database-backed page, view, queryset, or repeated template component, and when diagnosing duplicate or slow SQL.
---

# SQL performance

Check the query shape of a database-backed page before calling the work complete. The aim is to catch query growth
caused by the new path while its data flow is still familiar. Do not turn the check into an open-ended cleanup of
unrelated, pre-existing queries.

## Exercise a representative page

Use local data that exercises the page's repeated structures: fighters, cards, assignments, campaign gangs,
authoring entries, or whatever the template loops over. An empty state cannot expose a per-row cascade. Check the
important URL-driven variants when they render meaningfully different data.

Run the page through the toolbar-backed inspection command. Use `manage` normally; Codex worktrees need their wrapper:

```bash
manage inspect_page '/path/to/page/?variant=value'
# Codex: .codex/run.sh manage inspect_page '/path/to/page/?variant=value'
```

The command authenticates as the local `agent` user, makes one warm-up request, then measures two requests. Its
compact default output covers response status, stability, elapsed and CPU time, SQL, templates, cache use, static
files, queued tasks, alerts, and the resolved view. It also works for JSON and HTML fragments because it reads the
toolbar data inside the request process instead of scraping the injected interface.

Add only the detail needed for the current question:

```bash
# Repeated SQL families and the longest individual queries
manage inspect_page '/path/' --panel sql --limit 5

# Repeated templates and cache operations
manage inspect_page '/path/' --panel templates --panel cache --limit 10

# Route, request values, headers, timing, settings, and other toolbar data
manage inspect_page '/path/' --panel request --panel headers
manage inspect_page '/path/' --panel settings --setting CACHE --limit 10

# Every supported panel, bounded to three entries each, as structured data
manage inspect_page '/path/' --all --limit 3 --json
```

Use `--anonymous` for a signed-out page, `--username agent-<purpose>` for another local agent, `--header NAME=VALUE`
for a request variant such as HTMX, `--no-follow` for the first redirect response, and `--warmup` or `--repeat` when
the defaults do not stabilise the page. Run `manage inspect_page --help` for the complete interface.

## Read the SQL cascade

Use `--panel sql` to show bounded lists of similar groups, duplicate groups, and longest queries. Each entry includes
compact SQL, combined time, and the deepest project source frame or triggering template line when the toolbar records
one.

Start with these signals:

1. Note total queries and total SQL time as context. There is no project-wide good query count, and local timings are
   noisy. A new page at 60 queries is not automatically worse than one at 20.
2. Look for **similar** groups: the same raw SQL shape executed with different parameters. A group that follows the
   number of rendered objects is the clearest N+1 signal.
3. Look for **duplicate** groups: the exact same SQL and parameters executed again. These often indicate repeated
   property, context, permission, or template work.
4. Inspect the longest list for individual queries that dominate SQL time. Use the browser timeline when query order
   matters; it shows order and each query's share of SQL time, not idle gaps in the whole request.
5. Follow the reported source frame or template line to the loop, property, or middleware that caused the query.

The similar and duplicate totals count every query in a repeated family, not just the extra executions. Repetition
is a lead rather than proof: session and permission checks may be bounded, while an N+1 can vary enough to escape the
grouping heuristic.

Test the scaling question directly: if the page rendered more of the repeated object, would this query family grow
with it? Compare a small and larger local case when the answer is unclear. Query growth with collection size matters
more than the absolute total from one request.

## Inspect the exact browser state when needed

`inspect_page` makes a fresh Django test-client GET. Use the browser toolbar when the state depends on earlier browser
interactions, JavaScript, or a session that the command does not reproduce. Load the `dev-server` skill. Start the
worktree server in one terminal:

```bash
./scripts/dev.sh
```

Create a one-click login link for the exact page in another terminal:

```bash
manage agent_login_url '/path/to/page/?variant=value'
# Codex: .codex/run.sh manage agent_login_url '/path/to/page/?variant=value'
```

The toolbar starts collapsed. Open the corner handle, select **SQL**, and use **History** to switch between recent
request snapshots, including requests before a redirect. The detailed panels load on demand.

Do not open a separate Django shell after a browser request and expect `connection.queries` to contain it. The query
log belongs to the current process and connection, and Django clears it when a request starts. If browser automation
is unavailable, retain its authenticated cookie jar, extract the request ID from the page's toolbar markup, and fetch
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
counts, and say what changed after any fix. Name the regression test when one was added. State whether `inspect_page`
or the browser toolbar captured the result when the difference matters.
