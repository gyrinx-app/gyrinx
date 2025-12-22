# Query Patterns

Common query patterns extracted from the Gyrinx application codebase.

## User & Registration Metrics

### Daily user registrations

```sql
SELECT
    date_trunc('day', date_joined) as date,
    count(*) as registrations
FROM auth_user
WHERE date_joined >= NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
```

### User signups and confirmations

```sql
SELECT
    date_trunc('day', created) as date,
    verb,
    count(*) as count
FROM core_event
WHERE noun = 'user'
  AND verb IN ('signup', 'confirm', 'login')
  AND created >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY 1, 2;
```

## Event Analytics

### Top events by type (excluding views)

```sql
SELECT
    noun || '.' || verb as event_type,
    count(*) as count
FROM core_event
WHERE verb != 'view'
  AND created >= NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

### Events over time by type

```sql
SELECT
    date_trunc('day', created) as period,
    noun || '.' || verb as event_type,
    count(*) as count
FROM core_event
WHERE created >= NOW() - INTERVAL '30 days'
GROUP BY 1, 2
ORDER BY 1, 2;
```

### Events by user

```sql
SELECT
    u.username,
    e.noun,
    e.verb,
    count(*) as count
FROM core_event e
JOIN auth_user u ON e.owner_id = u.id
WHERE e.created >= NOW() - INTERVAL '7 days'
GROUP BY 1, 2, 3
ORDER BY 4 DESC
LIMIT 50;
```

## List & Fighter Metrics

### List creation over time

```sql
SELECT
    date_trunc('day', created) as date,
    count(*) as lists_created
FROM core_list
WHERE status = 'list-building'  -- Active lists only
  AND created >= NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
```

### Lists by house

```sql
SELECT
    h.name as house,
    count(*) as list_count,
    sum(l.total_cost) as total_credits
FROM core_list l
JOIN content_contenthouse h ON l.content_house_id = h.id
WHERE l.archived = false
GROUP BY 1
ORDER BY 2 DESC;
```

### Fighter creation over time

```sql
SELECT
    date_trunc('day', lf.created) as date,
    count(*) as fighters_created
FROM core_listfighter lf
JOIN core_list l ON lf.list_id = l.id
WHERE l.status = 'list-building'
  AND lf.created >= NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
```

### Most popular fighter types

```sql
SELECT
    cf.name as fighter_type,
    h.name as house,
    count(*) as usage_count
FROM core_listfighter lf
JOIN content_contentfighter cf ON lf.content_fighter_id = cf.id
JOIN content_contenthouse h ON cf.house_id = h.id
WHERE lf.archived = false
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 20;
```

## Campaign Metrics

### Campaign creation over time

```sql
SELECT
    date_trunc('day', created) as date,
    count(*) as campaigns_created
FROM core_campaign
WHERE created >= NOW() - INTERVAL '30 days'
GROUP BY 1
ORDER BY 1;
```

### Campaign participation

```sql
SELECT
    c.name as campaign,
    count(DISTINCT cl.list_id) as list_count,
    count(DISTINCT l.owner_id) as player_count
FROM core_campaign c
LEFT JOIN core_campaign_lists cl ON c.id = cl.campaign_id
LEFT JOIN core_list l ON cl.list_id = l.id
WHERE c.archived = false
GROUP BY 1
ORDER BY 3 DESC
LIMIT 20;
```

## Equipment Analytics

### Most used equipment

```sql
SELECT
    ce.name as equipment,
    count(*) as assignment_count
FROM core_listfighterequipmentassignment lea
JOIN content_contentequipment ce ON lea.content_equipment_id = ce.id
WHERE lea.archived = false
GROUP BY 1
ORDER BY 2 DESC
LIMIT 30;
```

## Cumulative Metrics

### Cumulative growth (fighters, lists, campaigns)

```sql
WITH daily_counts AS (
    SELECT
        date_trunc('day', created) as date,
        'fighters' as metric,
        count(*) as daily_count
    FROM core_listfighter
    GROUP BY 1
    UNION ALL
    SELECT
        date_trunc('day', created) as date,
        'lists' as metric,
        count(*) as daily_count
    FROM core_list
    WHERE status = 'list-building'
    GROUP BY 1
    UNION ALL
    SELECT
        date_trunc('day', created) as date,
        'campaigns' as metric,
        count(*) as daily_count
    FROM core_campaign
    GROUP BY 1
)
SELECT
    date,
    metric,
    sum(daily_count) OVER (PARTITION BY metric ORDER BY date) as cumulative
FROM daily_counts
ORDER BY date, metric;
```

## Useful Status Values

### List statuses

- `list-building` - Active list being built
- `campaign` - List in a campaign
- `retired` - Retired list

### Event verbs

- `view` - Page/item viewed
- `create` - Item created
- `update` - Item updated
- `delete` - Item deleted
- `login` - User logged in
- `signup` - User signed up
- `confirm` - User confirmed email
- `clone` - Item cloned
