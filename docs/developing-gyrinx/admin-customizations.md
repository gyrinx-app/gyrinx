# Admin Customizations

This document describes the most important Django admin customizations in Gyrinx, particularly focusing on the content admin module.

## Overview

The content admin module (`gyrinx/content/admin.py`) contains extensive customizations to provide a better user experience for managing game content. These customizations handle complex relationships between fighters, equipment, and various game mechanics.

## Key Admin Customizations

### 1. Equipment Category Limit Validation

The `ContentFighterEquipmentCategoryLimitForm` ensures that equipment category limits can only be set for categories that have fighter restrictions. This prevents configuration errors where limits would be meaningless.

**Key features:**
- Validates against parent category restrictions
- Groups fighters by house for better organization
- Prevents invalid limit configurations

**Implementation:**
- Custom `clean()` method checks for fighter restrictions
- Dynamic form class creation in `get_formset()` to pass parent instance

### 2. Equipment Cloning

The `clone` action in `ContentEquipmentAdmin` allows duplicating equipment items with all their associated weapon profiles. This is useful for creating variations of existing equipment.

**Key features:**
- Atomic transaction ensures data consistency
- Copies all associated weapon profiles
- Adds "(Clone)" suffix to distinguish copies
- Error handling with user feedback

**Usage:**
Select equipment items in the admin list view and choose "Clone selected Equipment" from the actions dropdown.

### 3. Dynamic Form Field Filtering

Several admin forms dynamically filter their field choices based on context:

#### Equipment Admin Form
- Orders categories by predefined group order
- Filters modifiers to only show fighter-affecting types
- Groups categories for better organization

#### Fighter Equipment List Item Form
- Filters weapon profiles based on selected equipment
- Only shows profiles with cost > 0
- Groups fighters by house and equipment by category

### 4. Statline Auto-Creation

The `ContentStatlineAdmin.save_related()` method ensures all required stats exist for a statline after saving. This prevents incomplete data and maintains consistency.

**Key features:**
- Automatically creates missing stat entries
- Sets default empty values ("-")
- Runs after all related objects are saved
- Maintains statline type requirements

### 5. Inline Form Customizations

#### Statline Inline
- Enforces one-to-one relationship with fighters
- Custom `has_add_permission()` prevents multiple statlines
- Max of one statline per fighter

#### Page Reference Inline
- Custom ordering by numeric page number
- Handles both numeric and empty page values
- Converts string pages to integers for proper sorting

### 6. Query Optimization

Several admins include query optimizations to prevent N+1 queries:

- `ContentFighterEquipmentListUpgradeAdmin`: Uses `select_related("house")` for fighter queries
- `ContentStatlineStatInline`: Filters stats based on parent statline type

## Common Patterns

### Group Select Fields

The `group_select()` utility function is used throughout to organize dropdown fields into logical groups:

```python
group_select(self, "fighter", key=lambda x: x.house.name if x.house else "No House")
group_select(self, "equipment", key=lambda x: x.cat())
```

This improves usability when dealing with large numbers of choices.

### Polymorphic Admin Support

The content module uses `django-polymorphic` for modifier models, with:
- `ContentModAdmin` as the parent admin
- Child admins for specific modifier types
- Polymorphic filter in list view

### Custom Form Validation

Many forms include custom validation in their `clean()` methods to enforce business rules:
- Equipment category restrictions
- Fighter assignment limits
- Statline requirements

## Best Practices

1. **Use Atomic Transactions**: Critical operations like cloning use `transaction.atomic()` to ensure consistency
2. **Provide User Feedback**: Actions include success/error messages via `message_user()`
3. **Optimize Queries**: Use `select_related()` and `prefetch_related()` to prevent N+1 queries
4. **Dynamic Filtering**: Filter choices based on context to prevent invalid selections
5. **Group Related Fields**: Use `group_select()` to organize long dropdown lists

## Adding New Admin Customizations

When adding new admin customizations:

1. Document complex logic with docstrings
2. Use transactions for multi-step operations
3. Include error handling and user feedback
4. Consider query performance with proper prefetching
5. Test with both empty and populated databases
6. Follow existing patterns for consistency
