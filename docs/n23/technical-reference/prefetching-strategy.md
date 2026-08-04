# Prefetching Strategy Reference

This document explains the prefetching methods used to optimize cost calculations and view performance in Gyrinx.

## Overview

The cost system relies on proper prefetching to:

1. Avoid N+1 queries - List and detail views need related data prefetched
2. Keep `latest_action` reads cheap - the staff debug header and maintenance tooling read the newest ListAction, and `with_latest_actions()` turns that into a prefetch instead of a query per list

Display methods (`cost_display()`, `rating_display()`, `stash_fighter_cost_display`) read the persisted cache fields (`rating_current`, `stash_current`, `credits_current`) directly and need no prefetch at all. A dirty list shows its last-good numbers until the write-time heal (`List.set_dirty` enqueues `refresh_list_facts`) or a detail-page view (`get_clean_list_or_404`) recomputes them.

## QuerySet Methods

### List.objects.with_latest_actions()

Lightweight prefetch for latest-action reads:

```python
def with_latest_actions(self):
    """
    Prefetch the latest action for each list.

    Populates the `latest_actions` attribute so callers of
    `latest_action` (the staff debug header, maintenance tooling) read
    from the prefetch instead of issuing a query per list.
    """
    return self.prefetch_related(
        Prefetch(
            "actions",
            queryset=ListAction.objects.order_by(
                "list_id", "-created", "-id"
            ).distinct("list_id"),
            to_attr="latest_actions",
        ),
    )
```

When to use: Any flow that reads `latest_action` for multiple lists (e.g. maintenance tooling walking many chains).

What it enables:

- `list.latest_action` returns the most recent action without an extra query

### List.objects.with_related_data()

Full optimization for list detail pages:

```python
def with_related_data(self, with_fighters=False):
    """
    Optimize queries by selecting related content_house and owner,
    and prefetching fighters with their related data.
    """
    qs = (
        self.with_latest_actions()  # Includes facts prefetch
        .select_related(
            "content_house",
            "owner",
            "campaign",
        )
    )
    if with_fighters:
        qs = qs.with_fighter_data()
    return qs
```

When to use: List detail views, edit views.

Parameters:

- `with_fighters=False` (default): Just list-level data
- `with_fighters=True`: Also prefetch all fighters and their equipment

### List.objects.with_fighter_data()

Prefetch fighters with their full related data:

```python
def with_fighter_data(self):
    """Prefetch related fighter data for each list."""
    return self.prefetch_related(
        Prefetch(
            "listfighter_set",
            queryset=ListFighter.objects.with_group_keys().with_related_data(),
        ),
    )
```

When to use: Combined with `with_related_data(with_fighters=True)`.

### ListFighter.objects.with_related_data()

Fighter-level optimization:

```python
def with_related_data(self):
    """
    Optimize queries by selecting related content_fighter and list,
    and prefetching injuries and equipment assignments.
    """
    return (
        self.select_related(
            "content_fighter",
            "content_fighter__house",
            "content_fighter__fighter_type",
            "list",
            "list__content_house",
        )
        .prefetch_related(
            "injuries",
            "skills",
            Prefetch(
                "listfighterequipmentassignment_set",
                queryset=ListFighterEquipmentAssignment.objects.with_related_data(),
            ),
        )
    )
```

When to use: Fighter detail views, lists of fighters.

### ListFighterEquipmentAssignment.objects.with_related_data()

Equipment assignment optimization:

```python
def with_related_data(self):
    """
    Optimize queries by selecting related content_equipment and list_fighter,
    and prefetching weapon profiles, accessories, and upgrades.
    """
    return self.select_related(
        "content_equipment", "list_fighter"
    ).prefetch_related(
        "weapon_profiles_field",
        "weapon_accessories_field",
        "upgrades_field",
    )
```

When to use: Equipment lists, assignment detail views.

## View Patterns

### Multi-List Views (Campaigns, Homepage)

Cost display needs no prefetch — the display methods read persisted fields:

```python
def campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    lists = List.objects.filter(campaign=campaign)

    return render(request, "campaign_detail.html", {
        "campaign": campaign,
        "lists": lists,  # cost_display/rating_display read cached fields
    })
```

### List Detail Views

Use `with_related_data()` for full data:

```python
def list_detail(request, pk):
    lst = get_object_or_404(
        List.objects.with_related_data(with_fighters=True),
        pk=pk
    )

    return render(request, "list_detail.html", {
        "list": lst,
        # Fighters are already prefetched with all related data
    })
```

### Fighter Detail Views

Use fighter-level prefetch:

```python
def fighter_detail(request, pk):
    fighter = get_object_or_404(
        ListFighter.objects.with_related_data(),
        pk=pk
    )

    return render(request, "fighter_detail.html", {
        "fighter": fighter,
        # Equipment assignments are already prefetched
    })
```

## The _prefetched_objects_cache Check

The `facts_from_db()` method checks for prefetched data to avoid redundant queries:

```python
def facts_from_db(self, update: bool = True) -> ListFacts:
    # Use prefetched fighters if available
    if "_prefetched_objects_cache" in self.__dict__:
        fighters = list(self.listfighter_set.all())
    else:
        fighters = list(self.listfighter_set.select_related(...))
```

This means:

- If you've already prefetched fighters, `facts_from_db()` reuses them
- If you haven't, it fetches them with appropriate optimization

## Performance Impact

| Scenario | Without Prefetch | With Prefetch |
|----------|-----------------|---------------|
| Campaign page (10 lists) | 30+ queries | 3 queries |
| List detail page | 50+ queries | 5-10 queries |
| Fighter detail page | 20+ queries | 3-5 queries |

## Common Mistakes

### 1. Not using with_fighters for detail views

```python
# BAD: N+1 queries when accessing fighters
lst = List.objects.get(pk=pk)
for fighter in lst.fighters():  # New query per fighter
    print(fighter.name)

# GOOD: Single query for all fighters
lst = List.objects.with_related_data(with_fighters=True).get(pk=pk)
for fighter in lst.listfighter_set.all():  # Already loaded
    print(fighter.name)
```

### 2. Double prefetching

```python
# BAD: Prefetches twice
lst = List.objects.with_related_data().with_latest_actions().get(pk=pk)

# GOOD: with_related_data() already includes with_latest_actions()
lst = List.objects.with_related_data().get(pk=pk)
```

## See Also

- [Fighter Cost System Reference](../fighter-cost-system-reference.md) - Facts API documentation
- [Cost Handler Development Guide](../how-to-guides/handler-development.md) - Handler patterns
