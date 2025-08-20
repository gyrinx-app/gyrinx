# SQL Debugging Guide

This guide explains how to debug SQL queries in the Gyrinx application, including logging configuration, performance analysis, and troubleshooting slow queries.

## Overview

The application includes a comprehensive SQL logging system that captures:
- All SQL queries executed by Django
- Query execution times
- Slow query analysis with PostgreSQL EXPLAIN plans
- Separate logging for debugging vs. production

## Quick Start

To enable SQL debugging, add these lines to your `.env` file:

```bash
# Enable SQL query logging
SQL_DEBUG=True

# Set slow query threshold (in seconds, default 0.01 = 10ms)
SQL_MIN_DURATION=0.01

# Optional: Enable EXPLAIN ANALYZE (executes queries!)
SQL_EXPLAIN_ANALYZE=False
```

Then restart your Django development server. SQL queries will be logged to:
- `logs/sql.log` - All SQL queries
- `logs/slow_sql.log` - Slow queries with EXPLAIN plans

## Configuration Options

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SQL_DEBUG` | `False` | Enable/disable SQL query logging |
| `SQL_MIN_DURATION` | `0.01` | Threshold for slow queries (seconds) |
| `SQL_EXPLAIN_ANALYZE` | `False` | Add ANALYZE to EXPLAIN (executes SELECT queries!) |
| `SQL_EXPLAIN_DB_ALIAS` | `default` | Database alias for EXPLAIN queries |

### Log Files

All SQL logs are written to the `logs/` directory:

- **`sql.log`**: Complete SQL query log
  - Includes all queries when `SQL_DEBUG=True`
  - Shows query text, parameters, and execution time
  - Rotates at 10MB, keeps 5 backup files

- **`slow_sql.log`**: Slow query analysis
  - Only queries exceeding `SQL_MIN_DURATION`
  - Includes PostgreSQL EXPLAIN output
  - Shows query plan and estimated costs
  - Rotates at 10MB, keeps 5 backup files

## Common Use Cases

### 1. Finding N+1 Query Problems

Enable SQL debugging and look for repeated patterns in `sql.log`:

```bash
# Enable logging
echo "SQL_DEBUG=True" >> .env

# Run your code, then analyze patterns
grep "SELECT.*FROM.*content_contentfighter" logs/sql.log | wc -l
```

If you see hundreds of similar queries, you likely have an N+1 problem. Use `select_related()` or `prefetch_related()` to fix it.

### 2. Identifying Slow Queries

Set a low threshold to catch all potentially slow queries:

```bash
# Catch queries slower than 5ms
echo "SQL_MIN_DURATION=0.005" >> .env

# Check slow query log
tail -f logs/slow_sql.log
```

Look for queries with:
- Sequential scans on large tables
- Missing indexes
- Complex joins
- Large result sets

### 3. Analyzing Query Plans

The slow query log includes EXPLAIN output. Key things to look for:

```
Seq Scan on core_list  (cost=0.00..1.33 rows=1 width=0)
  Filter: (upper((name)::text) ~~ '%TEST%'::text)
```

- **Seq Scan**: Table scan, slow on large tables
- **Index Scan**: Using an index, generally good
- **cost**: First number is startup cost, second is total cost
- **rows**: Estimated number of rows

### 4. Query Performance Comparison

To compare query performance with different approaches:

```bash
# Enable EXPLAIN ANALYZE for actual execution times
echo "SQL_EXPLAIN_ANALYZE=True" >> .env

# Run your code with different implementations
# Compare the actual time vs. estimated costs in slow_sql.log
```

**Warning**: `SQL_EXPLAIN_ANALYZE=True` executes SELECT queries twice (once for EXPLAIN ANALYZE, once for the actual query).

### 5. Debugging Specific Views

To debug SQL queries for a specific view:

```python
# In your view or shell
from django.db import connection, reset_queries

# Reset query log
reset_queries()

# Run your code
lists = List.objects.filter(name__icontains='test').count()

# Check queries
print(f"Query count: {len(connection.queries)}")
for query in connection.queries:
    print(f"{query['time']}s: {query['sql'][:100]}...")
```

## Understanding the Log Format

### sql.log Format

```
DEBUG 2025-08-20 07:14:21,426 utils 46103 8350441664 (0.005) SELECT COUNT(*) AS "__count" FROM "core_list" WHERE UPPER("core_list"."name"::text) LIKE UPPER('%test%'); args=('%test%',); alias=default
```

- **DEBUG**: Log level
- **2025-08-20 07:14:21,426**: Timestamp
- **utils**: Logger name
- **46103**: Process ID
- **8350441664**: Thread ID
- **(0.005)**: Query execution time in seconds
- **SELECT...**: The SQL query
- **args=**: Query parameters
- **alias=**: Database alias

### slow_sql.log Format

```
DEBUG 2025-08-20 07:14:21,426 utils 46103 8350441664 (0.005) SELECT COUNT(*) AS "__count" FROM "core_list" WHERE UPPER("core_list"."name"::text) LIKE UPPER('%test%'); args=('%test%',); alias=default
Aggregate  (cost=1.33..1.34 rows=1 width=8)
  ->  Seq Scan on core_list  (cost=0.00..1.33 rows=1 width=0)
        Filter: (upper((name)::text) ~~ '%TEST%'::text)
--------------------------------------------------------------------------------
```

Includes the same query information plus the PostgreSQL EXPLAIN output showing the query execution plan.

## Best Practices

1. **Development Only**: Keep `SQL_DEBUG=False` in production to avoid performance impact and large log files.

2. **Threshold Tuning**: Start with a higher threshold (0.1 seconds) and gradually lower it as you optimize queries.

3. **Regular Monitoring**: Check slow_sql.log regularly during development to catch performance issues early.

4. **Index Analysis**: Use EXPLAIN output to identify missing indexes:
   ```sql
   -- If you see Seq Scan on large tables, consider adding an index
   CREATE INDEX idx_list_name ON core_list(name);
   ```

5. **Query Optimization**: Common optimizations based on EXPLAIN:
   - Use `select_related()` for foreign keys
   - Use `prefetch_related()` for many-to-many and reverse foreign keys
   - Use `only()` or `defer()` to limit fields
   - Use `exists()` instead of `count()` for existence checks

## Troubleshooting

### Logs Directory Not Created

If the logs directory doesn't exist, the system will try to create it. If that fails, it falls back to the system temp directory. Check the Django logs for:

```
INFO: Using logs directory: /path/to/logs
```

### Empty Log Files

If log files are empty:
1. Verify `SQL_DEBUG=True` in `.env`
2. Restart the Django server after changing settings
3. Check that queries are actually being executed
4. Verify file permissions on the logs directory

### EXPLAIN Errors

If you see `[EXPLAIN ERROR: ...]` in slow_sql.log:
- The query might not be a SELECT statement (EXPLAIN only works with SELECT)
- The query might be too complex for automatic EXPLAIN
- Try running the query manually with EXPLAIN in `manage shell`

### Performance Impact

SQL logging has minimal performance impact, but:
- File I/O for logging can slow down high-traffic applications
- `SQL_EXPLAIN_ANALYZE=True` doubles SELECT query execution
- Log rotation happens at 10MB, which may cause brief pauses

## Advanced Configuration

### Custom Slow Query Threshold per View

You can temporarily adjust the threshold for specific code:

```python
import os
from contextlib import contextmanager

@contextmanager
def slow_query_threshold(threshold):
    old_value = os.environ.get('SQL_MIN_DURATION', '0.01')
    os.environ['SQL_MIN_DURATION'] = str(threshold)
    try:
        yield
    finally:
        os.environ['SQL_MIN_DURATION'] = old_value

# Usage
with slow_query_threshold(0.001):  # 1ms threshold
    # Your code here
    expensive_query()
```

### Analyzing Log Files

Use command-line tools to analyze patterns:

```bash
# Top 10 slowest queries
grep "^DEBUG" logs/slow_sql.log | sort -t'(' -k2 -rn | head -10

# Count queries by table
grep "FROM" logs/sql.log | sed 's/.*FROM "\([^"]*\)".*/\1/' | sort | uniq -c | sort -rn

# Find N+1 patterns (repeated queries)
grep "^DEBUG" logs/sql.log | sed 's/([0-9.]*)//' | sort | uniq -c | sort -rn | head -20
```

## Implementation Details

The SQL logging system is implemented in `gyrinx/settings_dev.py`:

1. **SlowQueryFilter**: Filters queries based on execution time
2. **ExplainFileHandler**: Custom handler that adds EXPLAIN output
3. **Logging Configuration**: Configures Django's database backend logger

The system hooks into Django's database layer to capture all SQL queries automatically, requiring no changes to application code.
