# Cost Propagation Architecture

**Status**: Design
**Date**: 2025-12-06
**Issue**: #1158

## Problem Statement

The current cost calculation system has major performance problems:

1. **Multi-list pages are painful** - Campaigns, home page require computing costs for many lists
2. **List pages require full tree traversal** - Every `cost_int()` call walks the entire tree
3. **Signal-based caching is incomplete** - We've tried in-memory cache updates via signals but haven't covered everything
4. **No cached costs on intermediate nodes** - Only `List` has `rating_current`/`stash_current`; `ListFighter` and `ListFighterEquipmentAssignment` have no cached values

### Current Tree Structure

```
List
├── rating_current ✓ (cached)
├── stash_current ✓ (cached)
├── credits_current ✓ (cached)
└── ListFighter
      ├── (no cached cost)
      └── ListFighterEquipmentAssignment
            └── (no cached cost)
```

### Goals

1. **Instant read of all costs** through the hierarchy - O(1) at every level
2. **Underlying source of truth** for bottom-up calculations when needed
3. **Strong consistency** for user operations
4. **Eventual consistency** acceptable for content model changes (with dirty flags)

---

## Solution Overview

### Core Concepts

1. **Facts Interface** - Every cost-bearing model has:
   - `facts()` → Returns cached values as dataclass, None if dirty
   - `facts_from_db()` → Full recalculation, updates cache, returns dataclass

2. **Cached Fields** - Add `rating_current` and `dirty` to intermediate models

3. **Write-Time Tree Walk** - Mutations propagate deltas up the tree immediately

4. **Transaction Wrapper** - Rename `create_action` to `transact()`, takes lambda for mutation

5. **Content Dirty Flags** - Content model changes mark affected objects dirty

### New Tree Structure

```
List
├── rating_current ✓ (existing)
├── stash_current ✓ (existing)
├── credits_current ✓ (existing)
├── dirty (NEW)
└── ListFighter
      ├── rating_current (NEW)
      ├── dirty (NEW)
      └── ListFighterEquipmentAssignment
            ├── rating_current (NEW)
            └── dirty (NEW)
```

---

## Detailed Design

Note that this design is not in implementation order. See Implementation Phases at the end.

### 1. Facts Dataclasses

```python
# gyrinx/core/models/facts.py

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AssignmentFacts:
    """Immutable facts about an equipment assignment."""
    rating: int


@dataclass(frozen=True)
class FighterFacts:
    """Immutable facts about a fighter."""
    rating: int
    base_cost: int
    equipment_cost: int
    advancement_cost: int


@dataclass(frozen=True)
class ListFacts:
    """Immutable facts about a list."""
    rating: int
    stash: int
    credits: int

    @property
    def wealth(self) -> int:
        return self.rating + self.stash + self.credits
```

### 2. Model Changes

#### ListFighterEquipmentAssignment

```python
class ListFighterEquipmentAssignment(...):
    # Existing fields...

    # NEW: Cached rating and dirty flag
    rating_current = models.IntegerField(
        default=0,
        help_text="Cached total rating of this assignment",
    )
    dirty = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if cached values may be stale",
    )

    def facts(self) -> Optional[AssignmentFacts]:
        """
        Return cached facts about this assignment.

        Returns None if the cached values may be stale (dirty=True).
        Callers should fall back to facts_from_db() when None is returned.

        This method is O(1) and does NOT hit the database.
        """
        if self.dirty:
            return None
        return AssignmentFacts(rating=self.rating_current)

    def facts_from_db(self) -> AssignmentFacts:
        """
        Recalculate facts from the database and update cache.

        This performs a full cost calculation using the existing
        rating_int() logic, updates rating_current, clears dirty,
        and returns the facts.

        Use this when facts() returns None, or when you need
        guaranteed-fresh values.
        """
        # Use existing calculation logic
        self.rating_current = self._calculate_rating()
        self.dirty = False
        self.save(update_fields=["rating_current", "dirty"])
        return AssignmentFacts(rating=self.rating_current)

    def _calculate_rating(self) -> int:
        """
        Calculate rating from components. This is the source of truth.

        Extracted from existing cost_int() logic.

        TODO: Should this just use cost_int() directly?
        """
        if self.has_total_cost_override():
            return self.total_cost_override

        return (
            self._equipment_cost_with_override()
            + self._profile_cost_with_override()
            + self._accessory_cost_with_override()
            + self._upgrade_cost_with_override()
        )
```

#### ListFighter

```python
class ListFighter(...):
    # Existing fields...

    # NEW: Cached rating and dirty flag
    rating_current = models.IntegerField(
        default=0,
        help_text="Cached total rating of this fighter (base + equipment + advancements)",
    )
    dirty = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if cached values may be stale",
    )

    def facts(self) -> Optional[FighterFacts]:
        """
        Return cached facts about this fighter.

        Returns None if the cached values may be stale.
        """
        if self.dirty:
            return None

        # Base cost and advancement cost are cheap to compute
        # (cached_property or simple field access)
        base = self._base_cost_int
        adv = self._advancement_cost_int
        equip = self.cost_current - base - adv

        return FighterFacts(
            cost=self.cost_current,
            base_cost=base,
            equipment_cost=equip,
            advancement_cost=adv,
        )

    def facts_from_db(self) -> FighterFacts:
        """
        Recalculate facts from the database and update cache.
        """
        self.cost_current = self._calculate_cost()
        self.cost_dirty = False
        self.save(update_fields=["cost_current", "cost_dirty"])
        return self.facts()  # Safe because we just cleared dirty

    def _calculate_cost(self) -> int:
        """
        Calculate cost from components. Source of truth.
        """
        if self.should_have_zero_cost:
            return 0

        base = self._base_cost_int
        adv = self._advancement_cost_int

        # Sum assignment costs - use facts where available
        equip = 0
        for assignment in self.assignments():
            facts = assignment.facts()
            if facts:
                equip += facts.cost
            else:
                equip += assignment.facts_from_db().cost

        return base + adv + equip
```

#### List

```python
class List(...):
    # Existing: rating_current, stash_current, credits_current

    # NEW: Dirty flag for content model changes
    dirty = models.BooleanField(
        default=True,
        db_index=True,
        help_text="True if cached values may be stale due to content changes",
    )

    def facts(self) -> Optional[ListFacts]:
        """
        Return cached facts about this list.

        Returns None if the cached values may be stale.
        """
        if self.dirty:
            return None
        return ListFacts(
            rating=self.rating_current,
            stash=self.stash_current,
            credits=self.credits_current,
        )

    def facts_from_db(self) -> ListFacts:
        """
        Recalculate facts from the database and update cache.
        """
        fighters = list(self.fighters())

        rating = 0
        stash = 0

        for fighter in fighters:
            facts = fighter.facts()
            if facts is None:
                facts = fighter.facts_from_db()

            if fighter.content_fighter.is_stash:
                stash += facts.rating
            else:
                rating += facts.rating

        self.rating_current = rating
        self.stash_current = stash
        self.dirty = False
        self.save(update_fields=["rating_current", "stash_current", "dirty"])

        return ListFacts(
            rating=self.rating_current,
            stash=self.stash_current,
            credits=self.credits_current,
        )
```

### 3. Write-Time Propagation

```python
# gyrinx/core/cost/propagation.py

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gyrinx.core.models.list import (
        List,
        ListFighter,
        ListFighterEquipmentAssignment,
    )


@dataclass
class TransactDelta:
    """Represents a rating change to propagate."""
    old_rating: int
    new_rating: int
    is_stash: bool = False

    @property
    def delta(self) -> int:
        return self.new_rating - self.old_rating

    @property
    def has_change(self) -> bool:
        return self.delta != 0


def propagate_from_assignment(
    assignment: "ListFighterEquipmentAssignment",
    rating_delta: TransactDelta,
) -> None:
    """
    Propagate a rating change from an assignment up to the list.

    Updates:
    - assignment.rating_current
    - fighter.rating_current
    - list.rating_current or list.stash_current (based on routing)

    Clears dirty flags along the path.

    This should be called within a transaction (typically inside transact()).
    """
    if not cost_delta.has_change:
        return

    # Update assignment
    assignment.rating_current = rating_delta.new_rating
    assignment.dirty = False
    assignment.save(update_fields=["rating_current", "dirty"])

    # Walk up to fighter
    fighter = assignment.list_fighter
    fighter.rating_current += rating_delta.delta
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Walk up to list
    is_stash = is_stash_linked(fighter)
    lst = fighter.list
    if is_stash:
        lst.stash_current = max(0, lst.stash_current + rating_delta.delta)
    else:
        lst.rating_current = max(0, lst.rating_current + rating_delta.delta)

    return TransactDelta(
        old_rating=rating_before,
        new_rating=rating_before + rating_delta.delta,
        is_stash=is_stash,
    )



def propagate_from_fighter(
    fighter: "ListFighter",
    rating_delta: TransactDelta,
) -> None:
    """
    Propagate a cost change from a fighter up to the list.

    Use when fighter's own cost changes (e.g., base cost override,
    advancement cost change).
    """
    if not rating_delta.has_change:
        return

    # Update fighter
    fighter.rating_current = rating_delta.new_rating
    fighter.dirty = False
    fighter.save(update_fields=["rating_current", "dirty"])

    # Walk up to list
    is_stash = is_stash_linked(fighter)
    lst = fighter.list
    if is_stash:
        lst.stash_current = max(0, lst.stash_current + rating_delta.delta)
    else:
        lst.rating_current = max(0, lst.rating_current + rating_delta.delta)

    return TransactDelta(
        old_rating=rating_before,
        new_rating=rating_before + rating_delta.delta,
        is_stash=is_stash,
    )


def is_stash_linked(fighter: "ListFighter") -> bool:
    """
    Determine if a fighter's costs route to stash or rating.

    Returns True if costs should go to stash_current.
    Returns False if costs should go to rating_current.
    """
    # TODO: This should reuse existing logic if available

    # Direct stash fighter
    if fighter.content_fighter.is_stash:
        return True

    # Child fighter (vehicle/exotic beast) whose parent is on stash
    if fighter.is_child_fighter:
        parent_assignment = fighter.parent_equipment_assignment
        if parent_assignment:
            parent_fighter = parent_assignment.list_fighter
            return is_stash_linked(parent_fighter)

    return False
```

### 4. Transaction Wrapper

Rename `create_action` to `transact()` and refactor to accept a mutation lambda:

```python
# In List model

def transact(
    self,
    *,
    mutation: Callable[[], TransactDelta],
    user=None,
    action_type: ListActionType,
    description: str,
    is_stash: bool,
    subject_app: str = None,
    subject_type: str = None,
    subject_id: UUID = None,
    list_fighter: "ListFighter" = None,
    list_fighter_equipment_assignment: "ListFighterEquipmentAssignment" = None,
    update_credits: bool = False,
    credits_delta: int = 0,
) -> Optional[ListAction]:
    """
    Execute a cost-mutating operation within a transaction.

    The mutation callable should:
    1. Perform the actual model changes
    2. Call propagate_from_assignment() or propagate_from_fighter()
    3. Return the TransactDelta representing the change

    This method then:
    1. Captures before state
    2. Executes the mutation
    3. Creates a ListAction for audit trail

    Example:
        def do_mutation():
            old_cost = assignment.cost_current
            assignment.cost_override = new_value
            assignment.save()
            new_cost = assignment._calculate_cost()

            delta = TransactDelta(old_cost, new_cost)
            return propagate_from_assignment(assignment, delta)

        lst.transact(
            mutation=do_mutation,
            action_type=ListActionType.UPDATE_EQUIPMENT,
            description="Changed cost override",
            ...
        )
    """
    # Feature flag check (existing)
    if not self.latest_action or not settings.FEATURE_LIST_ACTION_CREATE_INITIAL:
        # Still execute mutation even if actions disabled
        mutation()
        # TODO: This should also preform the credit update as per current create_action
        return None

    # Capture before state
    rating_before = self.rating_current
    stash_before = self.stash_current
    credits_before = self.credits_current

    # Execute the mutation - it handles propagation to fighter/assignment
    delta = mutation()

    if update_credits:
        lst.credits_current += credits_delta
        lst.credits_earned += max(0, credits_delta)

    self.dirty = False  # We just updated, so we're clean
    self.save(update_fields=[
        "rating_current", "stash_current", "credits_current",
        "credits_earned", "dirty"
    ])

    # Create action for audit trail
    la = ListAction.objects.create(
        user=user or self.owner,
        owner=self.owner,
        list=self,
        action_type=action_type,
        description=description,
        subject_app=subject_app,
        subject_type=subject_type,
        subject_id=subject_id,
        list_fighter=list_fighter,
        list_fighter_equipment_assignment=list_fighter_equipment_assignment,
        rating_delta=delta.delta if not delta.is_stash else 0,
        stash_delta=delta.delta if delta.is_stash else 0,
        credits_delta=credits_delta if update_credits else 0,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
        applied=True,
    )

    return la
```

### 5. Handler Pattern

**Before (current pattern):**

```python
@transaction.atomic
def handle_equipment_purchase(*, user, lst, fighter, assignment):
    assignment.refresh_from_db()
    total_cost = assignment.cost_int()

    is_stash = fighter.is_stash

    lst.create_action(
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        rating_delta=total_cost if not is_stash else 0,
        stash_delta=total_cost if is_stash else 0,
        ...
    )
```

**After (new pattern):**

```python
@transaction.atomic
def handle_equipment_purchase(*, user, lst, fighter, assignment):
    assignment.refresh_from_db()

    def mutation() -> TransactDelta:
        # Assignment already saved by form
        new_cost = assignment._calculate_cost()
        delta = TransactDelta(old_rating=0, new_rating=new_cost)
        return propagate_from_assignment(assignment, delta)

    lst.transact(
        mutation=mutation,
        user=user,
        action_type=ListActionType.ADD_EQUIPMENT,
        description=f"Added {assignment.content_equipment.name}",
        list_fighter=fighter,
        list_fighter_equipment_assignment=assignment,
    )
```

### 6. Content Model Changes

When a Content model's cost field changes, mark the affected tree dirty:

```python
# gyrinx/core/signals/content_cost.py

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from gyrinx.content.models import ContentEquipment, ContentWeaponProfile, ...


COST_FIELDS = {
    ContentEquipment: ["cost"],
    ContentWeaponProfile: ["cost"],
    ContentWeaponAccessory: ["cost"],
    ContentEquipmentUpgrade: ["cost"],
    ContentFighter: ["base_cost"],
    ContentFighterEquipmentListItem: ["cost"],
}


@receiver(pre_save)
def capture_old_cost(sender, instance, **kwargs):
    if sender not in COST_FIELDS:
        return

    for field in COST_FIELDS[sender]:
        if instance.pk:
            try:
                old = sender.objects.filter(pk=instance.pk).values_list(field, flat=True).first()
                setattr(instance, f"_old_{field}", old)
            except Exception:
                pass


@receiver(post_save)
def mark_affected_dirty(sender, instance, created, **kwargs):
    if sender not in COST_FIELDS or created:
        return

    for field in COST_FIELDS[sender]:
        old = getattr(instance, f"_old_{field}", None)
        new = getattr(instance, field)
        if old != new:
            _mark_tree_dirty(sender, instance)
            break


def _mark_tree_dirty(model_class, instance):
    """
    Mark all affected assignments, fighters, and lists as dirty.
    """
    from gyrinx.core.models.list import (
        List, ListFighter, ListFighterEquipmentAssignment
    )

    # Find affected assignments based on model type
    if model_class.__name__ == "ContentEquipment":
        assignments = ListFighterEquipmentAssignment.objects.filter(
            content_equipment=instance
        )
    elif model_class.__name__ == "ContentWeaponProfile":
        assignments = ListFighterEquipmentAssignment.objects.filter(
            weapon_profiles_field=instance
        )
    # ... similar for other content types
    else:
        return

    # Mark assignments dirty
    assignment_ids = list(assignments.values_list("id", flat=True))
    ListFighterEquipmentAssignment.objects.filter(
        id__in=assignment_ids
    ).update(dirty=True)

    # Mark fighters dirty
    fighter_ids = list(assignments.values_list("list_fighter_id", flat=True).distinct())
    ListFighter.objects.filter(id__in=fighter_ids).update(dirty=True)

    # Mark lists dirty
    list_ids = list(
        ListFighter.objects.filter(id__in=fighter_ids)
        .values_list("list_id", flat=True)
        .distinct()
    )
    List.objects.filter(id__in=list_ids).update(dirty=True)
```

### 7. Read Path Usage

**In templates/views:**

```python
# Fast path - use cached facts
def list_detail_view(request, list_id):
    lst = get_object_or_404(List, id=list_id)

    facts = lst.facts()
    if facts is None:
        # Dirty - need to recalculate
        facts = lst.facts_from_db()

    return render(request, "list_detail.html", {
        "list": lst,
        "rating": facts.rating,
        "stash": facts.stash,
        "wealth": facts.wealth,
    })


# For multi-list pages (campaigns, home)
def campaign_detail_view(request, campaign_id):
    campaign = get_object_or_404(Campaign, id=campaign_id)
    lists = campaign.campaign_lists.all()

    list_data = []
    for lst in lists:
        facts = lst.facts()
        if facts is None:
            facts = lst.facts_from_db()
        list_data.append({
            "list": lst,
            "facts": facts,
        })

    return render(request, "campaign_detail.html", {"lists": list_data})
```

---

## Implementation Phases

### Phase 0: Transaction Wrapper

1. Refactor `create_action` to `transact()`
2. Update to accept mutation lambda and return `TransactDelta`
3. Test existing handlers still work

### Phase 1: Handler Migration

1. Update each handler to use new `transact()` pattern
2. Test each handler individually (use existing tests where possible)

### Phase 2: Data Model

1. Add `rating_current`, `dirty` to `ListFighterEquipmentAssignment`
2. Add `rating_current`, `dirty` to `ListFighter`
3. Add `dirty` to `List`
4. Create migration (default `dirty=True` for all existing rows)

### Phase 3: Facts Interface

1. Create `gyrinx/core/models/facts.py` with dataclasses
2. Add `facts()` and `facts_from_db()` to all three models
3. Add `_calculate_rating()` methods (reuse existing `cost_int()` if possible)
4. Test facts interface in isolation

### Phase 4: Propagation

1. Create `gyrinx/core/cost/propagation.py`
2. Implement `propagate_from_assignment()` and `propagate_from_fighter()`
3. Implement `is_stash_linked()` or reuse existing logic
4. Test propagation logic in isolation

### Phase 5: Handler Updates

1. Ensure all mutations call `propagate_from_*`
2. Test each handler end-to-end

### Phase 6: Content Signals

1. Create `gyrinx/core/signals/content_cost.py`
2. Implement dirty marking for content changes
3. Register signals in `apps.py`

### Phase 7: Batch Recalculation (Optional/Later)

0. Look into Django's new task scheduling framework
1. Management command to recalculate dirty objects
2. Can be run on-demand or via cron, or debounced on write
3. Not required - facts_from_db fallback handles it
