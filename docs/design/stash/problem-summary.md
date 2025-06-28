# Gang Stash - Problem Summary & Options

## Overview

In Necromunda campaigns, gangs need to manage unassigned equipment and credits between battles. Currently, all equipment must be assigned to specific fighters, which doesn't match the game's rules for campaign resource management. This document outlines the requirements and evaluates implementation options for a gang stash system.

## Original Requirements

Based on game rules and user needs:

### Core Functionality
- **Equipment Storage**: Store unassigned equipment in a gang-wide stash
- **Credits Management**: Track gang credits (starting amount = campaign budget - gang cost)
- **Equipment Distribution**: Move equipment between stash and fighters during post-battle
- **Equipment Sources**:
  - Trading Post purchases
  - Territory boons
  - Dead/retired fighter equipment
  - Battle rewards
- **Equipment Sales**: Sell items for value - D6×10 credits (minimum 5 credits)

### Game Rule Constraints
- **Wargear Replacement**: Can only discard wargear when replacing with similar item
- **Weapon Persistence**: Weapons cannot be discarded (must go to stash)
- **Equipment Limits**: Fighters limited to 3 weapons (with * weapons counting as 2)
- **Fighter Restrictions**: Equipment must be valid for fighter type when assigning
- **Cost Updates**: Fighter costs update when equipment is added/removed

### Financial Mechanics
- **Initial Credits**: Campaign budget - total gang cost = starting credits
- **Wealth Calculation**: Gang wealth = fighter value + stash equipment value + credits
- **Trading Post**: Purchase Common equipment at listed prices
- **Dice Mechanics**: Various operations require dice rolls (e.g., "pay 2D6×10 credits")

### Technical Requirements
- **Preserve Equipment Details**: Maintain weapon profiles, accessories, upgrades, and cost overrides
- **Audit Trail**: Log all stash operations as campaign actions
- **Equipment Sets**: Support linked equipment (vehicles with crew, exotic beasts)
- **Campaign Mode Only**: Stash only exists for lists in campaign mode

## Implementation Options

### Option 1: Dedicated Stash Model
Create a new `CampaignStashItem` model specifically for stash equipment.

**Pros:**
- Clean separation of concerns
- Purpose-built for stash functionality
- Flexible for future enhancements
- Clear, understandable data model

**Cons:**
- Requires new models, views, and admin
- Duplicates equipment assignment logic
- More code to maintain
- Longer implementation time

### Option 2: Stash Fighter (Recommended)
Use a special fighter with `is_stash=True` flag as equipment container.

**Pros:**
- Reuses ALL existing equipment infrastructure
- Automatic cost tracking (stash value = fighter cost)
- No new models required
- Fast implementation
- Equipment transfer is just reassignment between fighters

**Cons:**
- Conceptually odd (stash isn't really a fighter)
- Requires filtering stash fighters from many queries
- Needs special UI handling

### Option 3: Null Fighter Assignments
Allow `ListFighterEquipmentAssignment` to exist without a fighter.

**Pros:**
- Minimal model changes
- Equipment stays in same table
- Simple transfer mechanism

**Cons:**
- Breaks existing assumptions throughout codebase
- Complex foreign key constraints
- Risk of breaking existing functionality

### Option 4: Shadow Equipment Pool
Create parallel `ListEquipmentPool` model for unassigned equipment.

**Pros:**
- Clean separation without conceptual issues
- Similar to Option 1 but simpler
- Clear migration path

**Cons:**
- Still requires new model
- Some duplication of logic
- Medium implementation time

### Option 5: State Machine
Add state field to track equipment location (assigned/stashed/sold).

**Pros:**
- Single source of truth
- Clear state transitions
- Good audit trail

**Cons:**
- Complex state management
- Similar issues to Option 3
- Requires careful validation

## Recommendation

**Implement Option 2 (Stash Fighter)** for the following reasons:

1. **Fastest Time to Value**: Can be implemented with minimal changes
2. **Maximum Code Reuse**: Leverages existing equipment assignment system
3. **Proven Pattern**: Similar approaches used successfully in other systems
4. **Easy Migration Path**: Can refactor to cleaner approach later if needed
5. **Automatic Features**: Cost calculation, history tracking, and UI mostly work out of the box

### Implementation Strategy

1. **Phase 1**: Implement stash fighter with basic functionality
2. **Phase 2**: Add Trading Post integration and sales mechanics
3. **Phase 3**: Polish UI and add bulk operations
4. **Phase 4**: Consider migration to Option 4 if limitations become problematic

### Credits Handling

After evaluating options for credits storage:
- **Chosen Approach**: Add `campaign_credits` field directly to List model
- **Rationale**: Simple, reliable, can't be accidentally deleted
- **Alternative Considered**: Use campaign resources system (too flexible, deletion risk)

## Future Considerations

- **Reputation System**: May need integration with stash value
- **Hangers-on/Brutes**: Purchase through stash system
- **Captured Fighters**: Could extend stash to handle
- **Equipment Condition**: Damaged/broken equipment states
- **Loan System**: Borrowing credits with interest
