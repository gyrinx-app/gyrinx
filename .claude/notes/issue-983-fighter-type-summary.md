# Issue #983: Fighter Type Summary

## Goal

Add a table of gang fighter type and count in the list page attributes card.

## Requirements

- Display in the attributes card (`gyrinx/core/templates/core/includes/list_attributes.html`)
- List active fighters only (not stash)
- Visually separate with a table header row labelled "Fighter Types"
- Implement as a method on the List model
- Ensure no additional queries are issued (should use existing `with_related_data` prefetch)

## Implementation Steps

- [x] Add `fighter_type_summary` cached property to List model
- [x] Update `list_attributes.html` template to display fighter types
- [x] Write test to verify no additional queries
- [x] Run tests and format code

## Implementation Notes

- Iterate over `listfighter_set.all()` to access prefetched data without additional queries
- Filter in-memory using `fighter.archived` and `fighter.is_stash` properties
- Use `fighter.get_category()` to respect category overrides
- Group and count in-memory using `defaultdict`
- Convert category values to labels using `FighterCategoryChoices[category].label`
- Return sorted list of dicts with 'type' (category label) and 'count' keys

## Files Modified

- `gyrinx/core/models/list.py` - Added `fighter_type_summary` cached property
- `gyrinx/core/templates/core/includes/list_attributes.html` - Added fighter types section
- `gyrinx/core/tests/test_models_core.py` - Added two tests for the new functionality

## Tests

✓ `test_fighter_type_summary_no_additional_queries` - Verifies no additional queries when prefetched
✓ `test_fighter_type_summary_with_category_override` - Verifies category overrides are respected
