# Analytics App - CLAUDE.md

This file provides guidance specific to the analytics app.

## Important Notes

- **ALWAYS look up model definitions before using their fields or properties** - do not assume field names or choices.
  Use the Read tool to check the actual model definition in the `models.py` file before writing queries or filters.
- The analytics app uses hard-coded graphs, not configurable ones
- All graph data methods should use Django ORM, not raw SQL
- The dashboard supports timescale filtering (7d, 30d, 90d, 1y) and edition filtering

## Editions and the noun vocabulary

Two editions write to one events table, so every `Event` carries an `edition`.

- Noun values are defined by the editions, not by this app. `EventNoun` lives in
  `n23/core/events.py`; n26's live in `n26/analytics.py`. Only `PlatformNoun`
  (`user`, `banner`) is the platform's, because an account and a site-wide
  banner are the same thing whichever edition you are reading.
- **A noun value belongs to exactly one edition**, enforced at registration
  (`gyrinx/analytics/nouns.py`). That is what lets `edition` be derived from
  the noun instead of passed in — there is no argument to thread through the
  call sites, and so none to forget. A noun nobody registered is recorded as
  `unknown` with an error logged, never inferred into a real edition.
- `Event.noun`'s `choices` is the registry callable, so adding a noun does
  not require a migration.
- Anything grouping events must group by edition too, or it adds two products
  together. The growth chart's lines each declare an edition for this reason.

## Graph Types

1. **User Registrations** - Shows daily user registration counts
2. **Top Events (Excluding Views)** - Shows top 10 event types over time
3. **Cumulative Creations** - Shows cumulative counts of:
    - Fighters in list-building lists
    - List-building lists
    - Campaigns

## Common Patterns

When working with the analytics queries:

- Use `TruncDate` for date grouping
- Use `Count` for aggregations
- Remember to filter by start_date for timescale support
- Format dates as strings using `strftime("%Y-%m-%d")` for Chart.js compatibility
