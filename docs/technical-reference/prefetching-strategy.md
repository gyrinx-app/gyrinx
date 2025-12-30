# Prefetching Strategy Reference

This document explains the prefetching methods used to optimize cost calculations and view performance in Gyrinx.

## Overview

The cost system relies on proper prefetching to:

1. Enable the facts system - The `can_use_facts` property requires `with_latest_actions()`
2. Avoid N+1 queries - List and detail views need related data prefetched
3. Optimize display methods - `cost_display()`, `rating_display()` use cached facts when available

## QuerySet Methods

### List.objects.with_latest_actions()

Lightweight prefetch that enables the facts system:

```python
def with_latest_actions(self):
    """
    Prefetch the latest action for each list.

    This enables the facts system by populating the `latest_actions` attribute,
    which is checked by the `can_use_facts` property.
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

When to use: Any view that displays list costs (campaigns, homepage, list index).

What it enables:

- `list.can_use_facts` returns `True`
- `list.latest_action` returns the most recent action
- `list.facts()` can return cached values

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

## The can_use_facts Property

The facts system is gated by `can_use_facts`:

```python
@property
def can_use_facts(self) -> bool:
    """
    Check if facts system can be used for display methods.

    Returns True only if:
    - latest_actions was prefetched via with_latest_actions()
    - AND there is at least one action (list has action tracking)
    """
    if hasattr(self, "latest_actions"):
        return bool(self.latest_actions)
    return False
```

Important: If you skip the prefetch, `can_use_facts` returns `False` and display methods fall back to direct calculation.

## View Patterns

### Multi-List Views (Campaigns, Homepage)

Use `with_latest_actions()` for fast cost display:

```python
def campaign_detail(request, pk):
    campaign = get_object_or_404(Campaign, pk=pk)
    lists = List.objects.filter(campaign=campaign).with_latest_actions()

    return render(request, "campaign_detail.html", {
        "campaign": campaign,
        "lists": lists,  # Each list can use facts()
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

### 1. Forgetting with_latest_actions()

```python
# BAD: can_use_facts returns False
lists = List.objects.filter(campaign=campaign)
for lst in lists:
    cost = lst.cost_display()  # Falls back to full calculation

# GOOD: can_use_facts returns True
lists = List.objects.filter(campaign=campaign).with_latest_actions()
for lst in lists:
    cost = lst.cost_display()  # Uses cached facts
```

### 2. Not using with_fighters for detail views

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

### 3. Double prefetching

```python
# BAD: Prefetches twice
lst = List.objects.with_related_data().with_latest_actions().get(pk=pk)

# GOOD: with_related_data() already includes with_latest_actions()
lst = List.objects.with_related_data().get(pk=pk)
```

## See Also

- [Fighter Cost System Reference](../fighter-cost-system-reference.md) - Facts API documentation
- [Cost Handler Development Guide](../how-to-guides/handler-development.md) - Handler patterns
