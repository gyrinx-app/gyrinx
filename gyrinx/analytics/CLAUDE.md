# Analytics App - CLAUDE.md

This file provides guidance specific to the analytics app.

## Important Notes

- **ALWAYS look up model definitions before using their fields or properties** - do not assume field names or choices.
  Use the Read tool to check the actual model definition in the `models.py` file before writing queries or filters.
- The analytics app uses hard-coded graphs, not configurable ones
- All graph data methods should use Django ORM, not raw SQL
- The dashboard supports timescale filtering (7d, 30d, 90d, 1y)

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
