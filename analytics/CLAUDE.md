# Analytics - CLAUDE.md

This directory contains tools for analyzing production data locally.

## Quick Start

```bash
# Start analytics database
docker compose --profile analytics up -d postgres-analytics

# Restore latest export
./scripts/analytics_restore.sh

# Run Streamlit dashboard
streamlit run analytics/streamlit/app.py
```

## Directory Structure

- @structure.sql - Full database schema (regenerated on each restore)
- @query_patterns.md - Common query patterns from the application
- `streamlit/` - Streamlit analytics dashboard

## Database Connection

```
Host: localhost
Port: 5433
User: postgres
Password: postgres
Database: dump_YYYY_MM_DD (e.g., dump_2025_12_22)
```

Python connection string:

```python
postgresql://postgres:postgres@localhost:5433/dump_2025_12_22
```

## Key Tables

### User Data (core_*)

| Table | Description |
|-------|-------------|
| `core_list` | User-created gangs/rosters |
| `core_listfighter` | Fighters in user lists |
| `core_listfighterequipmentassignment` | Equipment assigned to fighters |
| `core_campaign` | User campaigns |
| `core_event` | User activity events (noun + verb) |
| `auth_user` | User accounts |

### Content Data (content_*)

| Table | Description |
|-------|-------------|
| `content_contenthouse` | Gang factions |
| `content_contentfighter` | Fighter templates |
| `content_contentequipment` | Equipment/weapons |
| `content_contentweaponprofile` | Weapon stats |
| `content_contentskill` | Skills |

### Historical Tables (core_historical*)

All core models have `core_historical*` counterparts for audit trails (django-simple-history).

## Common Joins

```sql
-- List with house name
SELECT l.*, h.name as house_name
FROM core_list l
JOIN content_contenthouse h ON l.content_house_id = h.id;

-- Fighter with template info
SELECT lf.*, cf.name as fighter_type, cf.base_cost
FROM core_listfighter lf
JOIN content_contentfighter cf ON lf.content_fighter_id = cf.id;

-- Events with user info
SELECT e.*, u.username
FROM core_event e
LEFT JOIN auth_user u ON e.owner_id = u.id;
```

## See Also

- @query_patterns.md - More query examples from the codebase
- @structure.sql - Full schema reference
