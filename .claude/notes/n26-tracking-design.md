# Event tracking across two editions

Status: **implemented and committed locally to `main` as `6e61389c`. Not pushed.**
This document describes what is in that commit and flags the decisions worth
overturning before it goes anywhere.

## The two systems

Both live in `gyrinx/analytics/`. Both fire from one place — `Event.save()`.

1. **The database row.** `Event` (`gyrinx/analytics/models.py`), an `AppBase`
   model in table `core_event`, written by `log_event(...)`. Production holds
   ~640k rows.
2. **The log stream.** `gyrinx.tracker.track()` emits a structured JSON line
   through Python `logging`; in production `StructuredLogHandler` turns it into
   a Cloud Logging entry. `Event.save()` calls it and swallows any failure with
   `logger.exception("Failed to log event to stream")`.

An event that reaches one sink and not the other is half tracked, so the
edition dimension had to reach both.

## Decision 1 — the noun vocabulary: edition-scoped, via a registry

**Rejected:** one flat `EventNoun` holding both editions' words, disambiguated
by the edition column. It works, but it leaves the platform owning n26's
vocabulary, and every future noun is a platform change. It also makes the
edition column and the noun independently settable, which is how they come to
disagree.

**Chosen:** each edition declares its own nouns and claims them in a platform
registry. This matches where the codebase is already going — the last three
refactors on this branch (maintenance console, growth-chart series, task
routes) all moved to "platform owns the mechanism, edition registers its
contribution".

| Module | Owns |
|---|---|
| `gyrinx/analytics/nouns.py` | `Edition`, `register_nouns()`, `edition_for_noun()`, `noun_choices()`, and `PlatformNoun` |
| `n23/core/events.py` | `EventNoun` — this edition's words |
| `n26/analytics.py` | `N26Noun` — that edition's words |

`PlatformNoun` holds exactly two: `user` and `banner`. Signing in and
dismissing a site-wide banner happen on the way to either edition and belong to
neither. Everything else that was in `EventNoun` moved to n23.

**The rule that makes it work: a noun value belongs to exactly one edition.**
Registering a value another edition already claimed raises
`ImproperlyConfigured` at import, so the app refuses to boot rather than filing
an n26 gang under n23's "list".

**Cost of the move:** 44 files in `n23/` changed an import line
(`gyrinx.analytics.models` → `n23.core.events`), plus `EventNoun.USER` and
`EventNoun.BANNER` becoming `PlatformNoun.*` in a dozen of them. Nothing else
about those files changed.

**Known constraint, worth knowing before authoring n26's next noun:** the day
n26 wants a word n23 already holds — `battle` is the obvious one — the app will
not boot until one of them is renamed. That is loud rather than silent, which
is the trade taken, but it is a real constraint on the vocabulary.

## Decision 2 — how the edition gets set, and what happens if it is forgotten

**It is not a parameter.** There is no `edition=` on `log_event`. `Event.save()`
derives it from the noun:

```python
if not self.edition or self.edition == Edition.UNKNOWN:
    self.edition = edition_for_noun(self.noun)
```

Threading an argument through ~200 call sites was the alternative, and it fails
the same way every time: the next call site omits it, and the row is wrong in a
way nothing notices. Deriving removes the thing to forget.

Deriving in `save()` rather than in `log_event` means anything writing an
`Event` — a signal, a shell, a test — gets the dimension filled in.

**Failure mode.** The one way to get it wrong is to log a noun nobody
registered. Then:

- `edition_for_noun` returns `Edition.UNKNOWN` and logs an error naming the
  noun and the fix.
- The row is still written. Tracking must not break what it observes.
- On the dashboard it appears as its own "Unknown" slice, never merged into a
  real edition.

So a missed registration is visible in the data and shouty in the logs, and it
never produces a wrong graph — only an incomplete one.

## Decision 3 — the schema change

One new field on `Event`:

```python
edition = models.CharField(
    max_length=20, choices=Edition.choices,
    default=Edition.UNKNOWN, db_index=True,
)
```

`Edition` values: `platform`, `n23`, `n26`, `unknown`. `platform` is a real
answer, not a fallback; `unknown` is the fallback.

`Event.noun`'s `choices` becomes the registry callable `noun_choices`, grouped
by edition. Django deconstructs the callable by reference, so **adding a noun
never writes a migration**, and `makemigrations --check` stays clean.

### Migration and backfill — the assumption was wrong

`gyrinx/analytics/migrations/0002_event_edition.py`: `AddField`, then
`RunPython`, then the `AlterField` for the choices callable.

I checked production rather than assuming. 640k rows, 14 distinct nouns:

| noun | rows | edition |
|---|---:|---|
| `user` | 117,926 | **platform** |
| `banner` | 3,707 | **platform** |
| `list_fighter` | 291,509 | n23 |
| `equipment_assignment` | 166,332 | n23 |
| `list` | 27,643 | n23 |
| `campaign_asset` | 13,725 | n23 |
| `campaign_resource` | 7,555 | n23 |
| `campaign` | 2,866 | n23 |
| `campaign_action` | 2,657 | n23 |
| `campaign_invitation` | 2,219 | n23 |
| `content_pack` | 1,852 | n23 |
| `battle` | 1,591 | n23 |
| `print_config` | 685 | n23 |
| `upload` | 264 | n23 |

**"They are all n23" is false for about a fifth of the table.** Filing account
and banner events under n23 would have overstated it by 121,633 rows.

The mapping is spelled out in the migration rather than read from the registry,
so re-running it on an old database gives the same answer it gave the first
time. It is two `UPDATE` statements, not a row walk. A module-level
`edition_for_existing_noun()` makes it testable (tests run `--nomigrations`, so
data migrations never execute under pytest).

Applied to the worktree database: 1021 n23 / 548 platform / 0 unknown.

## Decision 4 — the boundary

n26 calls the platform, through **one file**: `n26/analytics.py`. No view or
model in `n26/` imports `gyrinx.analytics`; they import `record()` from there.

The case: tracking is genuinely platform infrastructure. One events table, one
log stream, one dashboard, and every question anyone asks ("how many people did
X this week") is asked of the site. A second store in n26 would answer none of
those and would give the two editions incompatible histories.

Why one file rather than scattered imports: the seam can be read, tested and
moved in one place, and the file also holds n26's noun declarations and its
growth-chart lines — so the whole of n26's relationship with analytics is one
screen of code.

Recorded as a fifth exception in the boundary section of `n26/CLAUDE.md`, in
the same register as the existing four, and mirrored from the platform side in
`gyrinx/analytics/CLAUDE.md`.

`record()` is deliberately thin:

```python
def record(request, noun, verb, obj=None, **context):
    return log_event(user=request.user, noun=noun, verb=verb,
                     object=obj, request=request, **context)
```

## Decision 5 — what n26 records

**This is the list most worth trimming or extending.** Each is one event per
press, recorded *after* the operation commits (an event written inside
`operation(...)` would be rolled back with a refused purchase, and a database
error raised while writing it would take the purchase down with it).

| noun | verb | where | context carried |
|---|---|---|---|
| `gang` | `create` | `create_gang` | gang type, starting credits |
| `gang` | `delete` | `delete_gang` | — |
| `model` | `create` | `hire_fighter` | gang, profile, price read off the ledger |
| `assignment` | `create` | `equip` | gang, model, item, collection, total paid, parts count |
| `choice` | `confirm` | `choose` | the offer's label, what was picked |
| `print_run` | `export` | `print_gang` | card count, saved-config flag, stash flag |
| `ingest` | `import` | `library.ingest` | sheet names, rows created, rows updated |

Query-cost discipline: a print carries a card count rather than a row per card;
an ingest carries totals rather than an event per imported row; a weapon bought
with three paid ammo types is one event with `parts=3`, not four. n26's budget
guard tests still pass unchanged.

Deliberately not instrumented: **selling/removing** (no view exists yet), and
**per-row authoring creates** in the library — staff-only, low analytic value,
and the file is under active edit by another agent. Both are cheap to add.

Judgement calls open to the maintainer:

- `delete` vs `archive` for a gang. The row is archived; the player deleted it.
  I chose `delete` because it names what the player did.
- `model` as a noun value is generic on a chart. It is n26's user-facing word
  for a `Miniature`, and the vocabulary rules say to use the glossary's words.
- `print_run` fires on every render of the print page, including reloads.
  Crawlers are already excluded by `log_event`'s bot check.

## Decision 6 — the dashboard

- An `?edition=` filter in the URL beside the timescale. An unrecognised value
  shows everything.
- `GrowthSeries` gains an `edition` field; the chart shows only the chosen
  edition's lines. Nothing is ever summed across editions.
- n26 registers two lines (gangs, models, both counting archived rows too — the
  chart is about what people made).
- n23's three lines are relabelled "N23 Fighters/Lists/Campaigns", because
  "Fighters" beside "Models" says nothing about which game either belongs to.
- User registrations deliberately ignore the filter: an account is the site's,
  and the same sign-up reaches both editions. The heading says so.
- `EventAdmin` gains `edition` in `list_display`, `list_filter` and the
  read-only fieldset.

The top-events graph cannot double-count, because a noun belongs to one edition
— the filter is there so one edition's busiest actions do not crowd the other's
out of the top ten.

## A bug found on the way

`log_event` could not point at an n26 row at all. `Event.object_id` is a
`UUIDField`; n26's primary keys are ULIDs, whose canonical 26-character form the
field rejects with a `ValidationError` — and inside an ambient transaction that
error poisons the request. A ULID is the same 128 bits and knows how to say so,
so `log_event` now converts on the way in:

```python
as_uuid = getattr(object.pk, "to_uuid", None)
event_data["object_id"] = object.pk if as_uuid is None else as_uuid()
```

Duck-typed, so the platform learns nothing about ULIDs — the rule is "a primary
key that is 128 bits under another name". The generic FK resolves back to the
n26 row correctly (`ULIDField.to_python` accepts a `uuid.UUID`).

## Tests

`pytest n26 gyrinx n23 -q -n 4` → **6164 passed, 12 skipped**.
`./scripts/fmt.sh` clean, `git status` re-checked after it.
`manage makemigrations --check` clean.

- `gyrinx/tests/test_analytics_editions.py` (13) — collision refused, no noun
  in two editions, derivation per edition, unknown noun still records, both
  sinks carry it, broken stream keeps the row, the migration's mapping is total
  over the old vocabulary.
- `n26/tests/test_analytics.py` (8) — right noun and edition, never filed as
  n23, the event points at the gang, a dead stream and an unwritable event both
  leave the founding intact, one press is one event.
- `gyrinx/tests/test_analytics_dashboard.py` — the edition filter narrows the
  chart; a nonsense edition shows everything.
- n23's existing event and banner-click tests gained edition assertions.

## What would change under review

- **The 44-file import move** is the largest reversible piece. Keeping
  `EventNoun` in the platform would shrink the diff a lot, at the cost of the
  platform continuing to own one edition's vocabulary.
- **The instrumented list** (Decision 5) is a judgement call and is cheap to
  change in either direction.
- **`PlatformNoun` holding `banner`** rests on the banner being rendered above
  both editions, which it is (`n26/core/templates/n26/layouts/base.html`). If
  that is wrong, `banner` moves to n23 and the migration's mapping changes with
  it.
- **The no-collision rule** is the one thing that is awkward to change later,
  because the derivation depends on it.
