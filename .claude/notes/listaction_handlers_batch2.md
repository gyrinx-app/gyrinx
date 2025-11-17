# ListAction Handlers - Batch 2 Implementation Plan

## Overview

**Issue**: #1088 - Implement ListAction handlers for next batch of operations
**Parent Issue**: #1054 - List cost cache rethink
**Dependencies**: #1058 - ListAction model implementation (merged)

### Goal

Add ListAction tracking for all remaining cost-affecting operations to enable performant cost calculation via event sourcing pattern instead of full tree traversal.

### Key Investigation Findings 🔍

**All open questions have been answered:**

1. **Advancement Integration** ✅
   - `apply_advancement()` called from 3 view locations around line 4909 in list.py
   - Handler should wrap advancement application in the views

2. **Captured Fighters** ✅
   - **Captured fighters CANNOT be advanced** (validation in place)
   - Simplifies cost tracking - cost won't change while captured

3. **Fighter Cloning** ✅
   - Create ListAction on TARGET list only (where new fighter appears)
   - Source list unaffected (no cost change)

4. **Equipment Sale** ✅
   - Deletion at lines 5669-5686 in sell_list_fighter_equipment
   - Clean integration point before deletion, within existing transaction

5. **Campaign Start** ✅
   - Replace direct credit modification with handler
   - `create_action()` handles both ListAction and credit update atomically

### Already Completed ✅

From #1054, these operations now have ListAction handlers:
- Fighter deletion
- Fighter archival/restoration
- Equipment deletion
- Weapon profile removal
- Weapon accessory removal
- Equipment upgrade removal

## Operations to Implement

### 1. Fighter Cloning

**Location**: `clone_list_fighter` in `gyrinx/core/views/list.py:1040`

**Operation**: Creates a duplicate of an existing fighter with all their equipment

**ListAction Requirements**:
```python
action_type: ADD_FIGHTER
rating_delta: Positive (cost of new fighter + equipment)
stash_delta: Positive if cloning stash fighter
credits_delta: Negative in campaign mode (cost deducted)
```

**Implementation Notes**:
- Clone can target different list (source vs target)
- Uses `fighter.clone()` which preserves equipment, upgrades, profiles, accessories
- Preserves `cost_override` field
- **Question**: Create action on source list, target list, or both?

**Confidence**: MEDIUM-HIGH

---

### 2. Fighter Capture Operations

Multiple related operations affecting fighter captured state.

#### 2a. Mark Fighter Captured

**Location**: `mark_fighter_captured` in `gyrinx/core/views/list.py:3820`

**Operation**: Removes fighter from rating (still in gang but not counted)

**ListAction Requirements**:
```python
action_type: UPDATE_FIGHTER
rating_delta: Negative (remove fighter cost from rating)
stash_delta: 0
credits_delta: 0
```

**Implementation Notes**:
- Creates `CapturedFighter` record
- After capture, `fighter.should_have_zero_cost` returns True
- **CRITICAL**: Must capture cost BEFORE creating CapturedFighter record
- **Question**: Can captured fighters receive advancements while captured?

**Confidence**: LOW-MEDIUM

#### 2b. Fighter Return to Owner (with Ransom)

**Location**: `fighter_return_to_owner` in `gyrinx/core/views/campaign.py:2188`

**Operation**: Returns fighter to original owner with ransom payment

**ListAction Requirements** (TWO actions needed):

Capturing gang:
```python
action_type: UPDATE_FIGHTER
rating_delta: 0
stash_delta: 0
credits_delta: Positive (ransom payment received)
```

Original gang:
```python
action_type: UPDATE_FIGHTER
rating_delta: Positive (fighter cost added back)
stash_delta: 0
credits_delta: Negative (ransom payment made)
```

**Implementation Notes**:
- Deletes `CapturedFighter` record
- Multi-list operation - must create actions on BOTH lists
- Must be atomic (transaction boundary)

**Confidence**: LOW-MEDIUM

#### 2c. Fighter Release (no payment)

**Location**: `fighter_release` in `gyrinx/core/views/campaign.py:2323`

**Operation**: Returns fighter without payment

**ListAction Requirements** (original gang only):
```python
action_type: UPDATE_FIGHTER
rating_delta: Positive (fighter cost added back)
stash_delta: 0
credits_delta: 0
```

**Implementation Notes**:
- Deletes `CapturedFighter` record
- No credit transfer
- Single list operation

**Confidence**: MEDIUM

#### 2d. Sell Fighter to Guilders

**Location**: `fighter_sell_to_guilders` in `gyrinx/core/views/campaign.py:2084`

**Operation**: Permanently removes fighter, adds credits to capturing gang

**ListAction Requirements** (TWO actions needed):

Capturing gang:
```python
action_type: REMOVE_FIGHTER
rating_delta: 0
stash_delta: 0
credits_delta: Positive (sale proceeds)
```

Original gang:
```python
action_type: REMOVE_FIGHTER
rating_delta: Negative (fighter cost removed)
stash_delta: 0
credits_delta: 0
```

**Implementation Notes**:
- Marks `CapturedFighter.sold_to_guilders = True`
- Multi-list operation
- **Question**: Capture cost before or after `sold_to_guilders=True`?

**Confidence**: LOW-MEDIUM

---

### 3. Equipment Operations

#### 3a. Reassign Equipment

**Location**: `reassign_list_fighter_equipment` in `gyrinx/core/views/list.py:5317`

**Operation**: Moves equipment from one fighter to another

**ListAction Requirements**:
```python
action_type: UPDATE_EQUIPMENT
rating_delta: Depends on stash status of source/target
stash_delta: Depends on stash status of source/target
credits_delta: 0
```

**Delta Calculation Logic**:
- Source=stash, Target=regular: Move from stash to rating (+rating, -stash)
- Source=regular, Target=stash: Move from rating to stash (-rating, +stash)
- Both same type: No rating/stash change (0, 0)

**Implementation Notes**:
- Equipment cost via `assignment.cost_int()` includes upgrades/profiles/accessories
- Different houses may have different costs
- View already has `@transaction.atomic`

**Confidence**: HIGH ✅

#### 3b. Sell Equipment

**Location**: `sell_list_fighter_equipment` in `gyrinx/core/views/list.py:5431`

**Operation**: Removes equipment, adds credits

**ListAction Requirements**:
```python
action_type: REMOVE_EQUIPMENT
rating_delta: Negative if not from stash
stash_delta: Negative if from stash
credits_delta: Positive (sale proceeds)
```

**Implementation Notes**:
- Multi-step flow: selection → dice roll → summary
- **NEEDS INVESTIGATION**: Where exactly is equipment deleted?
- Complex existing view logic

**Confidence**: LOW

---

### 4. Fighter Advancements

**Location**: `apply_advancement()` in `gyrinx/core/models/list.py:4195`

**Operation**: Applies advancement to fighter (stat increase, skill, injury, etc.)

**ListAction Requirements**:
```python
action_type: UPDATE_FIGHTER
rating_delta: Positive (cost_increase from advancement)
stash_delta: Positive if fighter is in stash
credits_delta: Negative in campaign mode (advancement cost)
```

**Special Cases**:
- **Promotion**: Changes `category_override`, affects base cost
- All advancement types: stat, skill, injury, equipment, other
- Cost tracked in `advancement.cost_increase` field

**Implementation Notes**:
- Model method, not view
- **NEEDS INVESTIGATION**: Grep for all call sites to `apply_advancement()`
- Determine if handler belongs in view or model method
- Promotion may need special handling

**Confidence**: LOW

---

### 5. Campaign Start

**Location**: `start_campaign()` in `gyrinx/core/models/campaign.py:140`

**Operation**: Distributes initial credits to all lists based on budget

**ListAction Requirements** (for each list):
```python
action_type: UPDATE_FIGHTER (or new CAMPAIGN_START type?)
rating_delta: 0
stash_delta: 0
credits_delta: Positive (initial budget allocation)
```

**Implementation Notes**:
- Called once when campaign starts
- Affects all lists in campaign simultaneously
- Current implementation directly modifies `credits_current` in `_distribute_budget_to_list()`
- Must avoid double-application of credits
- May want dedicated action type

**Confidence**: MEDIUM-HIGH

---

## Existing Infrastructure

### ListAction Model

**Location**: `gyrinx/core/models/action.py:44-212`

**Key Fields**:
- `action_type` - Type from `ListActionType` enum
- `rating_delta`, `stash_delta`, `credits_delta` - Changes applied
- `rating_before`, `stash_before`, `credits_before` - State before action
- `subject_app`, `subject_type`, `subject_id` - What was affected
- `description` - Human-readable description
- `is_applied` - Whether action has been applied (for rollback safety)

### List.create_action() Method

**Location**: `gyrinx/core/models/list.py:521-561`

**Signature**:
```python
def create_action(
    self,
    user,
    action_type: ListActionType,
    subject_app: str,
    subject_type: str,
    subject_id: uuid.UUID,
    description: str,
    rating_delta: int = 0,
    stash_delta: int = 0,
    credits_delta: int = 0,
    rating_before: int | None = None,
    stash_before: int | None = None,
    credits_before: int | None = None,
) -> ListAction:
```

**Behavior**:
- Validates deltas match before/after if provided
- Updates `rating_current`, `stash_current`, `credits_current`
- Marks action as `is_applied=True`
- Creates associated `CampaignAction` if list is in campaign
- All within single database operation (atomic)

### Handler Pattern

**Example**: `handle_fighter_hire` in `gyrinx/core/handlers/fighter_operations.py`

```python
@transaction.atomic
def handle_fighter_hire(lst: List, fighter: ListFighter, user) -> ListAction:
    # 1. Capture BEFORE values
    rating_before = lst.rating_current
    stash_before = lst.stash_current
    credits_before = lst.credits_current

    # 2. Calculate deltas
    fighter_cost = fighter.cost_int()
    if fighter.stash:
        rating_delta = 0
        stash_delta = fighter_cost
    else:
        rating_delta = fighter_cost
        stash_delta = 0

    # 3. Calculate credits (if campaign)
    credits_delta = 0
    if lst.campaign:
        credits_delta = -fighter_cost

    # 4. Perform the operation (if needed - hiring already saved fighter)

    # 5. Create the ListAction
    return lst.create_action(
        user=user,
        action_type=ListActionType.ADD_FIGHTER,
        subject_app="core",
        subject_type="ListFighter",
        subject_id=fighter.id,
        description=f"Hired {fighter.name}",
        rating_delta=rating_delta,
        stash_delta=stash_delta,
        credits_delta=credits_delta,
        rating_before=rating_before,
        stash_before=stash_before,
        credits_before=credits_before,
    )
```

### Test Pattern

**Location**: `gyrinx/core/tests/test_handlers_fighter_operations.py`

**Coverage**:
- Correct deltas calculated
- ListAction created with correct action_type
- Before/after values tracked accurately
- Action marked as applied
- Campaign vs non-campaign mode
- Stash vs regular fighters

---

## Cost Calculation Logic

### ListFighter.cost_int()

**Location**: `gyrinx/core/models/list.py:1414-1430`

**Formula**:
```python
if cost_override:
    return cost_override

return (
    base_cost +           # From ContentFighter
    advancement_cost +    # Sum of all advancement.cost_increase
    equipment_cost        # Sum of all assignments via cost_for_list()
)
```

**Special Cases**:
- `should_have_zero_cost` returns True for captured/sold fighters → cost_int() returns 0
- Stash fighters same cost calculation, just affects different totals

### ListFighter.should_have_zero_cost

**Location**: `gyrinx/core/models/list.py:2273-2275`

Returns True if:
- Fighter has `CapturedFighter` record, OR
- Fighter's `CapturedFighter` has `sold_to_guilders=True`

### ListFighterAdvancement.cost_increase

**Location**: `gyrinx/core/models/list.py` (in ListFighterAdvancement model)

- Field tracks rating impact of advancement
- Used in `ListFighter.advancement_cost` calculation
- Set when advancement is applied

## Testing Strategy

### Test Structure

All handler tests follow pattern from `test_handlers_fighter_operations.py`:

```python
@pytest.mark.django_db
def test_handler_name_basic(client, user):
    """Test basic functionality."""
    # Setup
    lst = List.objects.create(owner=user, ...)

    # Execute
    action = handle_operation(lst, ..., user)

    # Assert
    assert action.action_type == ListActionType.XXX
    assert action.rating_delta == expected
    assert action.is_applied is True
    lst.refresh_from_db()
    assert lst.rating_current == expected
```

### Test Categories

For each handler:

1. **Basic Functionality**
   - Correct deltas calculated
   - ListAction created with correct type
   - Before/after values accurate
   - Action marked as applied

2. **Mode-Specific**
   - Campaign mode vs list building
   - CampaignAction creation
   - Credit validation

3. **Stash Handling**
   - Stash vs regular fighter behavior
   - Equipment on stash fighters
   - Correct delta target (rating vs stash)

4. **Credit Management**
   - Sufficient credits validation
   - Credit transfers (multi-list ops)
   - Negative credit prevention

5. **Edge Cases**
   - Equipment with upgrades/profiles/accessories
   - Fighter with cost_override
   - Cross-list operations
   - State transitions (captured → free)

6. **Transaction Safety**
   - Rollback on error (no partial state)
   - Atomic multi-list updates
   - Database integrity maintained

---

## Files to Modify/Create

### Handlers (Implementation)

- ✅ `gyrinx/core/handlers/equipment_purchases.py` - Add equipment reassignment
- ✅ `gyrinx/core/handlers/fighter_operations.py` - Add 5 fighter handlers
- 🆕 `gyrinx/core/handlers/campaign_operations.py` - New file for campaign start

### Views (Integration)

- `gyrinx/core/views/list.py`:
  - Line 1040: `clone_list_fighter`
  - Line 3820: `mark_fighter_captured`
  - Line 5317: `reassign_list_fighter_equipment`
  - Line 5431: `sell_list_fighter_equipment`

- `gyrinx/core/views/campaign.py`:
  - Line 2084: `fighter_sell_to_guilders`
  - Line 2188: `fighter_return_to_owner`
  - Line 2323: `fighter_release`

### Models (Integration)

- `gyrinx/core/models/campaign.py`:
  - Line 103: `_distribute_budget_to_list()` OR
  - Line 140: `start_campaign()`

- `gyrinx/core/models/list.py`:
  - Line 4195: `apply_advancement()` (TBD based on investigation)

### Tests (Verification)

- ✅ `gyrinx/core/tests/test_handlers_equipment_purchases.py` - Equipment tests
- ✅ `gyrinx/core/tests/test_handlers_fighter_operations.py` - Fighter tests
- 🆕 `gyrinx/core/tests/test_handlers_campaign_operations.py` - Campaign tests

---

## Critical Open Questions - ANSWERED ✅

### 1. Fighter Advancements ✅
- **Q**: Where is `apply_advancement()` called from?
- **A**: Called from 3 locations in `gyrinx/core/views/list.py`:
  1. Line ~4909: In the advancement confirmation flow (main path)
  2. Two other similar paths for different advancement types
  3. All called after creating the advancement object and campaign action
- **Impact**: Handler should go in the view(s), BEFORE calling `apply_advancement()`
- **Handler Placement**: Create handler that wraps the entire advancement application flow

### 2. Captured Fighter Advancements ✅
- **Q**: Can captured fighters receive advancements while captured?
- **A**: **NO** - Captured fighters CANNOT receive advancements
  - Validation exists in views (line 3858 in list.py checks `fighter.is_captured or fighter.is_sold_to_guilders`)
  - This simplifies cost tracking significantly!
- **Impact**: When capturing, we can safely record the fighter's current cost. When returning, the cost will be the same (no advancements possible while captured).

### 3. Fighter Cloning Actions ✅
- **Q**: Should source list also get a ListAction?
- **A**: **YES** - Create action on TARGET list only (where new fighter is created)
  - Cloning can target a different list (via form: `form.cleaned_data["list"]`)
  - The new fighter belongs to the target list, so that's where the cost impact occurs
  - Source list is unaffected (no cost change)
  - Only target list gets the ADD_FIGHTER action
- **Impact**: Handler creates ONE action on the target list

### 4. Equipment Sale Flow ✅
- **Q**: Where exactly is equipment deleted in sale flow?
- **A**: Deletion happens in the "confirm" step at lines 5669-5686:
  - If selling entire assignment: `assignment.delete()` at line 5671
  - If selling components: Profiles/accessories removed from assignment at lines 5674-5686
  - All within existing `@transaction.atomic` block starting at line 5659
- **Integration Point**: Insert handler BEFORE deletion (lines 5668-5669), within the transaction
- **Impact**: Handler can be cleanly inserted after storing assignment_id, before deletion

### 5. Campaign Start Credits ✅
- **Q**: Should handler replace existing credit modification?
- **A**: **NO** - Handler should CREATE ListAction to track the credit distribution
  - Current code in `_distribute_budget_to_list()` (lines 115-117) directly modifies credits
  - HOWEVER, `List.create_action()` ALSO modifies credits via `credits_delta`
  - **SOLUTION**: Replace direct credit modification with handler that creates ListAction
  - `create_action()` will handle both the ListAction creation AND credit modification atomically
- **Impact**: Refactor `_distribute_budget_to_list()` to use handler instead of direct modification

---

## Risk Assessment

1. **Multi-List Operations** (Capture/Return/Sell)
   - Must ensure atomic updates to both lists
   - Rollback testing critical
   - Credit transfers must be exact

2. **Captured Fighter Cost Tracking**
   - Cost becomes 0 after capture
   - Must capture BEFORE state change
   - Return must restore correct cost (what if advanced while captured?)

3. **Transaction Boundaries**
   - Some views already have `@transaction.atomic`
   - Must not create nested transaction issues
   - Handlers use `@transaction.atomic` too

4. **Equipment Sale Multi-Step Flow**
   - Complex existing flow
   - May require refactoring
   - Integration point unclear

5. **Django ModelForm & ORM**
   - Ensure no side effects from form saves or `is_valid()`
   - Specifically watch out for get_object_or_404 -> Form(instance=...) -> is_valid() as this will modify the instance

## Notes

- All handlers use `@transaction.atomic` decorator
- Follow pattern from `handle_fighter_hire`
- Test files use pytest with `@pytest.mark.django_db`
- Static files must be collected before template-rendering tests
- Format code with `./scripts/fmt.sh` before commit
- Run full test suite with `pytest`
