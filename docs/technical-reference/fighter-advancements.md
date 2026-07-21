# Fighter Advancement System

The fighter advancement system allows players to spend experience points (XP) to improve their fighters in campaign mode. This document describes the implementation and usage of the advancement system.

## Overview

Advancements are improvements that fighters can purchase using XP earned during campaigns. The system uses a multi-step wizard interface that guides players through:

1. **Dice Rolling Choice** - Choose between random rolling (cheaper) or manual selection (more expensive)
2. **Advancement Selection** - Pick a specific advancement based on dice roll or manual choice
3. **Confirmation** - Review and confirm the advancement purchase

There are four main types of advancements:

- **Characteristic Increases** - Improve fighter stats like Movement, Weapon Skill, etc.
- **New Skills** - Learn skills from Primary, Secondary, or other skill categories
- **Equipment** - Gain equipment configured through `ContentAdvancementEquipment`
- **Promotions** - Rise in rank (Ganger → Specialist, Prospect → Champion), driven by `ContentPromotionPath` content rows

## Model Structure

### ListFighterAdvancement

The `ListFighterAdvancement` model tracks all advancements purchased by a fighter:

```python
class ListFighterAdvancement(AppBase):
    fighter = models.ForeignKey(ListFighter, ...)
    advancement_type = models.CharField(...)  # "stat", "skill", "equipment", "promotion", "other"
    stat_increased = models.CharField(...)    # For stat advancements
    skill = models.ForeignKey(ContentSkill, ...)  # For skill advancements (and skill-bundling promotions)
    equipment_assignment = models.ForeignKey("content.ContentAdvancementAssignment", ...)
    promotion_path = models.ForeignKey("content.ContentPromotionPath", ...)  # For promotions
    promotion_target = models.ForeignKey("content.ContentFighter", ...)  # Chosen type for multi-target promotions
    xp_cost = models.PositiveIntegerField(...)
    cost_increase = models.IntegerField(...)
    campaign_action = models.OneToOneField("CampaignAction", ...)
```

Key features:

- Tracks which fighter purchased the advancement
- Records the type of advancement (stat, skill, equipment, promotion, or other)
- For stat advances: which characteristic was improved
- For skill advances: which skill was gained
- For promotions: which `ContentPromotionPath` was taken and, where the path offers a choice of target types, which was chosen
- Tracks XP cost and any increase to the fighter's credit value
- Links to campaign action if dice were rolled

### Promotions

Promotions are data-driven from `ContentPromotionPath` rows (see the
[content library guide](../content-library/promotions.md) for authoring). The moving parts:

- **Choice keys**: promotion options use the dynamic key `promotion_{path.id}` in the
  wizard. The two pre-content-driven keys (`skill_promote_specialist`,
  `skill_promote_champion`) remain valid forever — stored advancement rows are never
  rewritten. `resolve_promotion_choice()` in `core/models/list/advancement.py` resolves
  both eras; the legacy strings map through a static table so they keep applying and
  reversing even with no content rows present.
- **Applying** (`apply_advancement`): sets the fighter's `category_override` and, for
  type changes, `ListFighter.promoted_content_fighter` — the "counts as" pointer. Per
  the rules, statline and base cost never change; the only cost effect is the flat
  `cost_increase`, summed with all other advancements.
- **The counts-as pointer** (`ListFighter.promoted_content_fighter`, PROTECT): access-only.
  Equipment-list pricing resolves `legacy > promoted > base` (one shared tie-break helper,
  `preferred_equipment_list_override` in `core/models/list/_common.py`); skill-set access
  and special rules resolve `promoted > base` (replaced, not merged); statline and base
  cost always read `content_fighter`. The pointer is written only by the advancement flow —
  it is never a user-editable form field, and stash/vehicle targets are rejected.
- **Roll-driven prefill**: a Ganger's 2d6 total is matched against each path's `rolls`
  list (`get_initial_for_action`), so both 2 and 12 offer the Specialist promotion.
- **Reversal**: deleting a promotion recomputes both `category_override` and the pointer
  from the highest-`rank` promotion the fighter still holds (either era).
- **Copies**: `clone()`, `copy_attributes_to()`, and `FighterCloneParams` all carry
  `category_override` + `promoted_content_fighter`, so promotions survive campaign entry
  and fighter duplication (the duplicate form's checkbox governs both together).

### XP Tracking

Fighters track their XP using two fields:

- `xp_total` - Total XP earned throughout the campaign
- `xp_current` - Available XP that can be spent

When an advancement is purchased, the XP cost is deducted from `xp_current`.

## Form Flow

The advancement system uses a wizard-style interface with these steps:

### Step 1: Start (`list_fighter_advancement_start`)

Initiates the advancement process and redirects to dice choice.

### Step 2: Dice Choice (`list_fighter_advancement_dice_choice`)

`AdvancementDiceChoiceForm` - Player chooses:

- **Roll 2D6** - Cheaper option, limits choices based on dice result
- **Manual Selection** - More expensive, allows any advancement

### Step 3: Type Selection (`list_fighter_advancement_type`)

`AdvancementTypeForm` - Based on dice roll (or manual choice), shows available advancements:

- Stat improvements (Movement, Weapon Skill, etc.)
- Skill options (Primary/Secondary, Random/Chosen)
- Special options (Promote to Specialist, Any Random Skill)

Each option shows its XP cost based on the roll-to-cost mapping.

### Step 4: Skill Selection (`list_fighter_advancement_select`)

If a skill advancement was chosen:

- `SkillSelectionForm` - Pick specific skill from available categories
- `RandomSkillForm` - Accept randomly rolled skill

### Step 5: Confirmation (`list_fighter_advancement_confirm`)

Reviews the selected advancement showing:

- What was selected
- XP cost
- Credit increase
- Option to confirm or cancel

## Views

The advancement system uses these views:

- `list_fighter_advancements` - Lists all advancements for a fighter
- `list_fighter_advancement_start` - Initiates the advancement wizard
- `list_fighter_advancement_dice_choice` - Handles dice vs manual selection
- `list_fighter_advancement_type` - Shows available advancement options
- `list_fighter_advancement_select` - Skill selection for skill advancements
- `list_fighter_advancement_confirm` - Final confirmation and purchase
- `list_fighter_xp_edit` - Modify fighter's XP directly

## Business Rules

### XP Costs

The system uses a dice roll to XP cost mapping:

- Rolling 2-4, 12: 20 XP (includes special advancements)
- Rolling 5-6: 30 XP (high-value stat increases)
- Rolling 7, 10-11: 10 XP (moderate improvements)
- Rolling 8-9: 5 XP (cheapest options)
- Manual selection: Additional cost on top of base costs

Default advancement for each roll:

- 2, 12: Promote to Specialist
- 3: Weapon Skill, 4: Ballistic Skill, 5: Strength
- 6: Toughness, 7: Movement, 8: Willpower
- 9: Intelligence, 10: Leadership, 11: Cool

### Stat Improvements

- Stats with "+" values (like WS 4+) improve by reducing the number
- Other stats increase numerically
- Applied via fighter stat overrides

### Skill Restrictions

- Can only learn skills from Primary or Secondary categories
- Cannot learn the same skill twice
- Some skills may have prerequisites

### Campaign Mode Only

- Advancements can only be purchased in campaign mode
- Requires active campaign participation

## Templates

Key templates:

- `list_fighter_advancements.html` - Shows all advancements for a fighter
- `list_fighter_advancement_dice_choice.html` - Dice vs manual selection
- `list_fighter_advancement_type.html` - Advancement options based on roll
- `list_fighter_advancement_select.html` - Skill selection interface
- `list_fighter_advancement_confirm.html` - Final confirmation screen

## Integration Points

### Campaign Actions

When dice are rolled for an advancement, it creates a `CampaignAction` record to track:

- Who rolled
- What was rolled (2d6, 2d6+2)
- Results
- Links back to the advancement

### Fighter Cost

Each advancement increases the fighter's cost:

- Stat increases: typically +5 credits per stat point
- Skills: varies by skill value

### History Tracking

All advancement records use django-simple-history for audit trails.

## Example Usage

```python
# Check if fighter can purchase advancements
if fighter.list.status == List.CAMPAIGN_MODE and fighter.xp_current > 0:
    # Fighter can buy advancements

# Apply an advancement
advancement = ListFighterAdvancement.objects.create(
    fighter=fighter,
    advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
    stat_increased="weapon_skill",
    xp_cost=6,
    cost_increase=5
)
advancement.apply_advancement()  # Applies the stat increase
```

## Frontend Behavior

- Uses a multi-page wizard flow (not modals)
- Session storage tracks advancement state between steps
- Shows dice rolls and available options dynamically
- Validates selections at each step
- Allows going back to previous steps

## Error Handling

Common validation errors:

- Insufficient XP
- Invalid stat/skill selection
- Attempting advancement outside campaign mode
- Duplicate skill selection

All errors display user-friendly messages guiding correct usage.
