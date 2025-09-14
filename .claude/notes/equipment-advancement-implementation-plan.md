# Equipment-Based Advancement Implementation Plan

## Overview

This document provides a comprehensive plan for implementing equipment-based advancements in the Gyrinx advancement system. Based on analysis of the existing codebase, this plan integrates with the current advancement framework while adding support for equipment-based progression.

## Current System Analysis

### Existing Components

#### 1. ListFighterAdvancement Model (`/Users/tom/code/gyrinx/gyrinx/gyrinx/core/models/list.py:3842`)

**Current Structure:**

```python
class ListFighterAdvancement(AppBase):
    fighter = models.ForeignKey(ListFighter, ...)
    advancement_type = models.CharField(...)  # "stat", "skill", "other"
    stat_increased = models.CharField(...)    # For stat advancements
    skill = models.ForeignKey(ContentSkill, ...)  # For skill advancements
    description = models.CharField(...)       # For "other" advancements
    xp_cost = models.PositiveIntegerField(...)
    cost_increase = models.IntegerField(...)
    campaign_action = models.OneToOneField("CampaignAction", ...)
```

**Key Features:**

- Uses `AppBase` (provides UUID primary key, owner tracking, archiving, history)
- Tracks XP cost and credit increase
- Links to campaign actions for dice rolls
- Supports three advancement types: STAT, SKILL, OTHER

#### 2. AdvancementTypeForm (`/Users/tom/code/gyrinx/gyrinx/gyrinx/core/forms/advancement.py:24`)

**Current Dynamic Choice Generation:**

- Stat choices are dynamically generated from `ContentStat` model entries based on fighter's statline
- Uses `ContentStat.objects.all().values()` to build stat choices
- Maps stat field names to full display names via `all_stat_choices()` method

**Current Flow:**

1. Dice rolling choice (optional)
2. Type selection (stat/skill/other with dynamic costs)
3. Specific selection (for skills)
4. Confirmation

#### 3. ContentStat Model (`/Users/tom/code/gyrinx/gyrinx/gyrinx/content/models.py:3057`)

**Structure:**

```python
class ContentStat(Content):
    field_name = models.CharField(...)      # "movement", "weapon_skill"
    short_name = models.CharField(...)      # "M", "WS"
    full_name = models.CharField(...)       # "Movement", "Weapon Skill"
    is_inverted = models.BooleanField(...)  # Lower values are better (WS 3+ vs 4+)
    is_inches = models.BooleanField(...)    # Movement-type stats
```

**Key Integration:**

- Already used by advancement system for dynamic stat choice generation
- Provides consistent stat definitions across the system

#### 4. Equipment Models

**ContentEquipment** (`/Users/tom/code/gyrinx/gyrinx/gyrinx/content/models.py:607`):

- Standard equipment model with cost, rarity, categories
- Supports weapon profiles, upgrades, and accessories

**ListFighterEquipmentAssignment** (`/Users/tom/code/gyrinx/gyrinx/gyrinx/core/models/list.py:2450`):

- Links fighters to equipment
- Tracks cost overrides and total costs
- Uses `VirtualListFighterEquipmentAssignment` wrapper

### Current Advancement Flow

1. **Start** → `list_fighter_advancement_start`
2. **Dice Choice** → `list_fighter_advancement_dice_choice` (optional)
3. **Type Selection** → `list_fighter_advancement_type`
4. **Skill Selection** → `list_fighter_advancement_select` (if skill chosen)
5. **Confirmation** → `list_fighter_advancement_confirm`

## Proposed Implementation

### 1. New Model: ContentAdvancementEquipment

**Purpose:** Define which equipment can be gained through advancements with associated costs.

**Location:** `/Users/tom/code/gyrinx/gyrinx/gyrinx/content/models.py`

```python
class ContentAdvancementEquipment(Content):
    """
    Defines equipment that can be acquired through fighter advancement.
    Links equipment to advancement costs and restrictions.
    """

    equipment = models.ForeignKey(
        ContentEquipment,
        on_delete=models.CASCADE,
        related_name="advancement_options",
        help_text="Equipment that can be gained through advancement",
    )

    xp_cost = models.PositiveIntegerField(
        help_text="XP cost to acquire this equipment through advancement"
    )

    cost_increase = models.IntegerField(
        default=0,
        help_text="Fighter cost increase when this equipment is gained"
    )

    # Restriction options
    restricted_to_houses = models.ManyToManyField(
        ContentHouse,
        blank=True,
        related_name="advancement_equipment",
        help_text="If set, only these houses can gain this equipment via advancement"
    )

    restricted_to_fighter_categories = models.JSONField(
        default=list,
        blank=True,
        help_text="List of fighter categories that can gain this equipment (e.g., ['GANGER', 'CHAMPION'])"
    )

    history = HistoricalRecords()

    class Meta:
        verbose_name = "Advancement Equipment"
        verbose_name_plural = "Advancement Equipment"
        ordering = ["advancement_category", "position", "equipment__name"]

    def __str__(self):
        return f"{self.equipment.name} ({self.xp_cost} XP)"

    def is_available_to_fighter(self, list_fighter):
        """Check if this advancement equipment is available to a specific fighter."""
        # Check house restrictions
        if self.restricted_to_houses.exists():
            if list_fighter.list.house not in self.restricted_to_houses.all():
                return False

        # Check fighter category restrictions
        if self.restricted_to_fighter_categories:
            if list_fighter.content_fighter.category not in self.restricted_to_fighter_categories:
                return False

        # Check if fighter already has this equipment
        if ListFighterEquipmentAssignment.objects.filter(
            list_fighter=list_fighter,
            content_equipment=self.equipment,
            archived=False
        ).exists():
            return False

        return True
```

### 2. Update ListFighterAdvancement Model

**Add equipment support to existing model:**

```python
# Add new advancement type
ADVANCEMENT_EQUIPMENT = "equipment"

ADVANCEMENT_TYPE_CHOICES = [
    (ADVANCEMENT_STAT, "Characteristic Increase"),
    (ADVANCEMENT_SKILL, "New Skill"),
    (ADVANCEMENT_EQUIPMENT, "New Equipment"),  # NEW
    (ADVANCEMENT_OTHER, "Other"),
]

# Add equipment field
equipment = models.ForeignKey(
    ContentEquipment,
    on_delete=models.CASCADE,
    null=True,
    blank=True,
    help_text="For equipment advancements, which equipment was gained."
)

# Update __str__ method
def __str__(self):
    if self.advancement_type == self.ADVANCEMENT_STAT:
        return f"{self.fighter.name} - {self.get_stat_increased_display()}"
    elif self.advancement_type == self.ADVANCEMENT_SKILL:
        return f"{self.fighter.name} - {self.skill.name}"
    elif self.advancement_type == self.ADVANCEMENT_EQUIPMENT:  # NEW
        return f"{self.fighter.name} - {self.equipment.name}"
    elif self.advancement_type == self.ADVANCEMENT_OTHER and self.description:
        return f"{self.fighter.name} - {self.description}"
    return f"{self.fighter.name} - Advancement"

# Update apply_advancement method
def apply_advancement(self):
    """Apply this advancement to the fighter."""
    if self.advancement_type == self.ADVANCEMENT_STAT and self.stat_increased:
        # ... existing stat logic ...
    elif self.advancement_type == self.ADVANCEMENT_SKILL and self.skill:
        # ... existing skill logic ...
    elif self.advancement_type == self.ADVANCEMENT_EQUIPMENT and self.equipment:  # NEW
        # Create equipment assignment
        ListFighterEquipmentAssignment.objects.create(
            list_fighter=self.fighter,
            content_equipment=self.equipment,
            owner=self.owner  # Inherited from AppBase
        )
    elif self.advancement_type == self.ADVANCEMENT_OTHER:
        # ... existing other logic ...

    # Deduct XP cost from fighter
    self.fighter.xp_current -= self.xp_cost
    self.fighter.save()

# Update clean method
def clean(self):
    """Validate the advancement."""
    if self.advancement_type == self.ADVANCEMENT_STAT and not self.stat_increased:
        raise ValidationError("Stat advancement requires a stat to be selected.")
    if self.advancement_type == self.ADVANCEMENT_SKILL and not self.skill:
        raise ValidationError("Skill advancement requires a skill to be selected.")
    if self.advancement_type == self.ADVANCEMENT_EQUIPMENT and not self.equipment:  # NEW
        raise ValidationError("Equipment advancement requires equipment to be selected.")
    if self.advancement_type == self.ADVANCEMENT_OTHER and not self.description:
        raise ValidationError("Other advancement requires a description.")
    # Additional validation to ensure only appropriate field is set...
```

### 3. Update AdvancementTypeForm

**Add equipment choices to form:**

```python
ADVANCEMENT_CHOICES = [
    # Stat improvements (dynamically generated)
    # Skill options
    ("skill_primary_random", "Random Primary Skill"),
    ("skill_primary_chosen", "Chosen Primary Skill"),
    ("skill_secondary_random", "Random Secondary Skill"),
    ("skill_secondary_chosen", "Chosen Secondary Skill"),
    ("skill_promote_specialist", "Promote to Specialist (Random Primary Skill)"),
    ("skill_any_random", "Random Skill (Any Set)"),
    # Equipment options (dynamically generated)
    # Other
    ("other", "Other"),
]

def __init__(self, *args, fighter=None, **kwargs):
    super().__init__(*args, **kwargs)
    self.fighter = fighter

    # Generate stat choices (existing logic)
    all_stat_choices = AdvancementTypeForm.all_stat_choices()
    # ... existing stat logic ...

    # Generate equipment choices (NEW)
    equipment_choices = []
    if fighter:
        available_equipment = ContentAdvancementEquipment.objects.filter(
            # Could add filtering here based on dice roll results
        ).select_related('equipment')

        for adv_equipment in available_equipment:
            if adv_equipment.is_available_to_fighter(fighter):
                choice_key = f"equipment_{adv_equipment.id}"
                choice_label = f"{adv_equipment.equipment.name} ({adv_equipment.xp_cost} XP)"
                equipment_choices.append((choice_key, choice_label))

    # Combine all choices
    all_choices = (
        additional_advancement_choices +  # stats
        equipment_choices +               # equipment (NEW)
        initial_advancement_choices       # skills + other
    )

    self.fields["advancement_choice"].choices = all_choices

@classmethod
def all_equipment_choices(cls) -> dict[str, str]:
    """Get a dictionary mapping equipment choice keys to their full names."""
    return dict(
        (f"equipment_{ae.id}", f"{ae.equipment.name} ({ae.xp_cost} XP)")
        for ae in ContentAdvancementEquipment.objects.select_related('equipment').all()
    )

@classmethod
def all_advancement_choices(cls) -> dict[str, str]:
    """Get a dictionary mapping advancement choice keys to their full names."""
    return (
        cls.all_stat_choices() |
        cls.all_equipment_choices() |  # NEW
        dict(cls.ADVANCEMENT_CHOICES)
    )
```

### 4. New Form: EquipmentSelectionForm

**Create form for equipment advancement selection:**

```python
class EquipmentSelectionForm(forms.Form):
    """Form for selecting specific equipment advancement."""

    equipment = forms.ModelChoiceField(
        queryset=ContentAdvancementEquipment.objects.none(),
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Select equipment to gain through advancement.",
    )

    def __init__(self, *args, fighter=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fighter = fighter

        if fighter:
            # Get available equipment for this fighter
            available_equipment = ContentAdvancementEquipment.objects.filter(
                # Add any global filters here
            ).select_related('equipment')

            # Filter to only equipment available to this fighter
            filtered_equipment = [
                ae for ae in available_equipment
                if ae.is_available_to_fighter(fighter)
            ]

            self.fields["equipment"].queryset = ContentAdvancementEquipment.objects.filter(
                id__in=[ae.id for ae in filtered_equipment]
            ).select_related('equipment')

        # Group by advancement category
        group_select(self, "equipment", lambda x: x.advancement_category or "General")
```

### 5. Update Views

**Modify existing advancement views to handle equipment:**

#### Update `list_fighter_advancement_type`

```python
# In AdvancementFlowParams class
def is_equipment_advancement(self) -> bool:
    """Check if this is an equipment advancement choice."""
    return self.advancement_choice.startswith("equipment_")

def get_equipment_id(self) -> int:
    """Extract the equipment ID from the advancement choice."""
    if self.is_equipment_advancement():
        return int(self.advancement_choice.split("_", 1)[1])
    raise ValueError("Not an equipment advancement choice.")

def description_from_choice(self) -> str:
    """Get the description for the advancement based on the choice."""
    if self.is_stat_advancement():
        return AdvancementTypeForm.all_stat_choices().get(
            self.advancement_choice, "Unknown"
        )
    elif self.is_equipment_advancement():  # NEW
        try:
            equipment_id = self.get_equipment_id()
            adv_equipment = ContentAdvancementEquipment.objects.select_related('equipment').get(id=equipment_id)
            return adv_equipment.equipment.name
        except ContentAdvancementEquipment.DoesNotExist:
            return "Unknown Equipment"

    raise ValueError("Invalid advancement type for description.")
```

#### Update `list_fighter_advancement_select`

```python
# Add equipment selection logic alongside skill selection
if params.is_equipment_advancement():
    # Handle direct equipment assignment (no further selection needed)
    equipment_id = params.get_equipment_id()
    try:
        adv_equipment = ContentAdvancementEquipment.objects.select_related('equipment').get(id=equipment_id)
        if not adv_equipment.is_available_to_fighter(fighter):
            messages.error(request, "Selected equipment is not available to this fighter.")
            return redirect('core:list-fighter-advancement-type', lst.id, fighter.id)

        # Store equipment selection in session
        request.session['advancement_equipment_id'] = adv_equipment.id
        return redirect('core:list-fighter-advancement-confirm', lst.id, fighter.id)
    except ContentAdvancementEquipment.DoesNotExist:
        messages.error(request, "Invalid equipment selection.")
        return redirect('core:list-fighter-advancement-type', lst.id, fighter.id)
```

#### Update `list_fighter_advancement_confirm`

```python
# Add equipment confirmation logic
elif advancement_choice.startswith("equipment_"):
    equipment_id = request.session.get('advancement_equipment_id')
    if not equipment_id:
        messages.error(request, "Equipment selection not found.")
        return redirect('core:list-fighter-advancement-start', lst.id, fighter.id)

    try:
        adv_equipment = ContentAdvancementEquipment.objects.select_related('equipment').get(id=equipment_id)

        # Create advancement record
        advancement = ListFighterAdvancement.objects.create(
            fighter=fighter,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
            equipment=adv_equipment.equipment,
            xp_cost=adv_equipment.xp_cost,
            cost_increase=adv_equipment.cost_increase,
            owner=request.user,
            campaign_action_id=campaign_action_id,
        )

        # Apply the advancement (creates equipment assignment)
        advancement.apply_advancement()

        # Update fighter cost
        fighter.cost_increase += adv_equipment.cost_increase
        fighter.save()

        context['advancement_type'] = "Equipment"
        context['advancement_name'] = adv_equipment.equipment.name
        context['xp_cost'] = adv_equipment.xp_cost
        context['cost_increase'] = adv_equipment.cost_increase

    except ContentAdvancementEquipment.DoesNotExist:
        messages.error(request, "Invalid equipment selection.")
        return redirect('core:list-fighter-advancement-start', lst.id, fighter.id)
```

### 6. Update Templates

#### Update `list_fighter_advancement_type.html`

Add equipment advancement options to the advancement selection template, grouping them appropriately.

#### Update `list_fighter_advancement_confirm.html`

Add equipment-specific confirmation display showing the equipment being gained.

#### Update `list_fighter_advancements.html`

The template already handles equipment advancements via the updated `__str__` method.

### 7. Admin Integration

**Add admin for ContentAdvancementEquipment:**

```python
@admin.register(ContentAdvancementEquipment)
class ContentAdvancementEquipmentAdmin(admin.ModelAdmin):
    list_display = ('equipment', 'xp_cost', 'cost_increase', 'advancement_category')
    list_filter = ('advancement_category', 'restricted_to_houses')
    search_fields = ('equipment__name', 'description')
    filter_horizontal = ('restricted_to_houses', 'requires_skills')

    fieldsets = (
        (None, {
            'fields': ('equipment', 'xp_cost', 'cost_increase')
        }),
        ('Restrictions', {
            'fields': ('restricted_to_houses', 'restricted_to_fighter_categories', 'requires_skills'),
            'classes': ('collapse',)
        }),
        ('Display', {
            'fields': ('advancement_category', 'position', 'description')
        })
    )
```

## Implementation Strategy

### Phase 1: Database Schema (Migration Required)

1. **Create ContentAdvancementEquipment model**
    - Add to `/Users/tom/code/gyrinx/gyrinx/gyrinx/content/models.py`
    - Run `manage makemigrations content -n "add_advancement_equipment"`

2. **Update ListFighterAdvancement model**
    - Add `ADVANCEMENT_EQUIPMENT` choice
    - Add `equipment` ForeignKey field
    - Update methods: `__str__`, `apply_advancement`, `clean`
    - Run `manage makemigrations core -n "add_equipment_advancement_support"`

### Phase 2: Forms and Logic

3. **Update AdvancementTypeForm**
    - Add equipment choice generation in `__init__`
    - Add `all_equipment_choices()` class method
    - Update `all_advancement_choices()` to include equipment

4. **Create EquipmentSelectionForm**
    - New form in `/Users/tom/code/gyrinx/gyrinx/gyrinx/core/forms/advancement.py`
    - Handle equipment filtering and grouping

5. **Update AdvancementFlowParams**
    - Add `is_equipment_advancement()` method
    - Add `get_equipment_id()` method
    - Update `description_from_choice()` for equipment

### Phase 3: Views and Templates

6. **Update advancement views**
    - Modify `list_fighter_advancement_select` for equipment handling
    - Update `list_fighter_advancement_confirm` for equipment confirmation
    - Add equipment selection logic to flow

7. **Update templates**
    - Update advancement type selection template
    - Update confirmation template for equipment display
    - Templates already handle equipment via updated `__str__` method

### Phase 4: Admin and Testing

8. **Add admin interface**
    - Create `ContentAdvancementEquipmentAdmin`
    - Add to admin registration

9. **Create comprehensive tests**
    - Test equipment advancement flow
    - Test restrictions and prerequisites
    - Test integration with existing advancement system

## Integration Points

### 1. Form Integration

**AdvancementTypeForm Dynamic Choices:**

- Equipment choices are generated based on `ContentAdvancementEquipment` entries
- Filtered by fighter availability using `is_available_to_fighter()`
- Grouped by `advancement_category` for better UX

**Equipment Selection Flow:**

- Direct selection for equipment (no separate selection step needed)
- Equipment ID stored in session for confirmation step
- Validation ensures equipment availability at confirmation

### 2. Model Integration

**ContentStat Integration:**

- Equipment advancements follow same pattern as stat advancements
- Both use dynamic choice generation in forms
- Both integrate with dice roll cost system

**Equipment Assignment Integration:**

- Equipment advancement creates `ListFighterEquipmentAssignment` records
- Uses existing equipment assignment infrastructure
- Maintains cost tracking and history

### 3. View Flow Integration

**Existing Flow:**

```
Start → Dice Choice → Type Selection → [Skill Selection] → Confirmation
```

**With Equipment:**

```
Start → Dice Choice → Type Selection → [Equipment/Skill Selection] → Confirmation
```

Equipment selection is immediate (no separate selection step), similar to stat advancements.

### 4. Session State Management

**Current Session Keys:**

- `advancement_choice`
- `xp_cost`
- `cost_increase`
- `campaign_action_id`

**Additional Keys for Equipment:**

- `advancement_equipment_id` (stores selected equipment ID)

### 5. Cost System Integration

**Dice Roll to Cost Mapping:**
Equipment advancements can integrate with existing dice roll cost system:

- Base equipment XP cost from `ContentAdvancementEquipment.xp_cost`
- Additional cost modifier from dice roll (same as current system)
- Cost increase affects fighter value (same as current system)

## Database Schema Changes

### New Table: content_contentadvancementequipment

```sql
CREATE TABLE content_contentadvancementequipment (
    id UUID PRIMARY KEY,
    created TIMESTAMP WITH TIME ZONE NOT NULL,
    updated TIMESTAMP WITH TIME ZONE NOT NULL,
    equipment_id UUID NOT NULL REFERENCES content_contentequipment(id),
    xp_cost INTEGER NOT NULL CHECK (xp_cost >= 0),
    cost_increase INTEGER NOT NULL DEFAULT 0,
    advancement_category VARCHAR(50) NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    description TEXT NOT NULL DEFAULT '',
    restricted_to_fighter_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- History tracking
    history_id UUID
);

-- Many-to-many tables
CREATE TABLE content_contentadvancementequipment_restricted_to_houses (
    id BIGINT PRIMARY KEY,
    contentadvancementequipment_id UUID NOT NULL,
    contenthouse_id UUID NOT NULL,
    UNIQUE(contentadvancementequipment_id, contenthouse_id)
);

CREATE TABLE content_contentadvancementequipment_requires_skills (
    id BIGINT PRIMARY KEY,
    contentadvancementequipment_id UUID NOT NULL,
    contentskill_id UUID NOT NULL,
    UNIQUE(contentadvancementequipment_id, contentskill_id)
);
```

### Updated Table: core_listfighteradvancement

```sql
ALTER TABLE core_listfighteradvancement
ADD COLUMN equipment_id UUID REFERENCES content_contentequipment(id);

-- Update choices constraint
ALTER TABLE core_listfighteradvancement
DROP CONSTRAINT IF EXISTS core_listfighteradvancement_advancement_type_check;

ALTER TABLE core_listfighteradvancement
ADD CONSTRAINT core_listfighteradvancement_advancement_type_check
CHECK (advancement_type IN ('stat', 'skill', 'equipment', 'other'));
```

## UI/UX Design

### Equipment Advancement Selection

**Type Selection Screen:**

- Equipment options grouped by category (e.g., "Exotic Weapons", "Cybernetics")
- Show XP cost and prerequisites in option description
- Clear indication when equipment is unavailable (with reason)

**Category Grouping Examples:**

- **Exotic Weapons:** Plasma Pistol, Melta Gun, Power Sword
- **Cybernetics:** Cyber-mastiff, Photo-goggles, Respirator
- **Rare Gear:** Jump Booster, Grapnel Launcher, Web Solvent

**Confirmation Screen:**

- Show equipment details (name, cost, rules)
- Display any special properties or weapon profiles
- Confirm XP cost and fighter cost increase

### Responsive Design

**Mobile-First Approach:**

- Equipment options stack vertically on mobile
- Category headers clearly separate groups
- Touch-friendly selection buttons

**Desktop Enhancement:**

- Multi-column layout for equipment options
- Hover states show equipment details
- Keyboard navigation support

## Testing Strategy

### Unit Tests

1. **Model Tests:**
    - `ContentAdvancementEquipment.is_available_to_fighter()` logic
    - `ListFighterAdvancement.apply_advancement()` for equipment
    - Model validation and constraints

2. **Form Tests:**
    - Equipment choice generation in `AdvancementTypeForm`
    - Equipment filtering in `EquipmentSelectionForm`
    - Dynamic choice updates based on fighter

3. **View Tests:**
    - Equipment advancement flow end-to-end
    - Session state management
    - Error handling for invalid selections

### Integration Tests

1. **Full Advancement Flow:**
    - Complete equipment advancement from start to finish
    - Equipment assignment creation and cost tracking
    - Integration with campaign actions and dice rolls

2. **Restriction Testing:**
    - House restrictions work correctly
    - Fighter category restrictions enforced
    - Skill prerequisites validated

3. **Edge Cases:**
    - Equipment already owned by fighter
    - Invalid equipment selections
    - Session state corruption handling

## Data Migration Plan

### Content Data Seeding

**Initial Equipment Advancement Options:**

```python
# Example data for initial equipment advancements
INITIAL_EQUIPMENT_ADVANCEMENTS = [
    {
        'equipment': 'Plasma Pistol',
        'xp_cost': 30,
        'cost_increase': 50,
        'category': 'Exotic Weapons',
        'restricted_to_categories': ['CHAMPION', 'LEADER'],
    },
    {
        'equipment': 'Photo-goggles',
        'xp_cost': 15,
        'cost_increase': 15,
        'category': 'Cybernetics',
        'restricted_to_categories': ['GANGER', 'CHAMPION', 'LEADER'],
    },
    # ... more examples
]
```

**Migration Script:**

- Populate `ContentAdvancementEquipment` with initial data
- Map existing equipment to advancement categories
- Set reasonable XP costs based on equipment rarity/cost

### Backward Compatibility

- Existing `ListFighterAdvancement` records remain unchanged
- New `equipment` field is nullable for backward compatibility
- All existing advancement flows continue to work

## Performance Considerations

### Query Optimization

1. **Equipment Choice Generation:**
    - Use `select_related('equipment')` when loading advancement options
    - Consider caching available equipment choices per fighter type

2. **Availability Filtering:**
    - Database-level filtering where possible
    - Index on `advancement_category` for grouping queries

3. **Form Performance:**
    - Lazy load equipment choices only when needed
    - Prefetch related data for availability checks

### Caching Strategy

- Cache equipment availability by fighter category/house combination
- Cache advancement categories for consistent grouping
- Use Django's query result caching for repeated availability checks

## Security Considerations

### Validation

1. **Server-Side Validation:**
    - Always re-validate equipment availability on form submission
    - Check XP costs match database values
    - Verify fighter can afford advancement

2. **Permission Checks:**
    - Ensure user owns the fighter being advanced
    - Validate campaign mode requirements
    - Check list ownership throughout flow

3. **Input Sanitization:**
    - Validate equipment IDs are valid UUIDs
    - Sanitize any user input in advancement descriptions
    - Prevent injection attacks in dynamic queries

## Future Enhancements

### Conditional Equipment

- Equipment that becomes available based on other advancements
- Prerequisite chains (e.g., Basic → Advanced → Master tier equipment)

### Dynamic Costs

- Equipment costs that vary based on fighter type or house
- Bulk advancement discounts
- Campaign-specific equipment availability

### Equipment Upgrades

- Advancement paths for existing equipment (e.g., upgrade weapon profiles)
- Equipment modification through advancement system
- Integration with existing equipment upgrade system

## Success Criteria

1. **Functional Requirements:**
    - ✅ Equipment can be gained through advancement system
    - ✅ XP costs and fighter cost increases work correctly
    - ✅ Equipment restrictions (house, category, skills) enforced
    - ✅ Integration with existing advancement flow seamless

2. **Technical Requirements:**
    - ✅ Database schema properly normalized and indexed
    - ✅ Form validation prevents invalid selections
    - ✅ Session state management robust and secure
    - ✅ Admin interface allows easy equipment advancement management

3. **User Experience:**
    - ✅ Equipment selection UI intuitive and responsive
    - ✅ Clear feedback on prerequisites and restrictions
    - ✅ Confirmation screen shows all relevant details
    - ✅ Mobile experience equivalent to desktop

4. **Performance:**
    - ✅ Equipment choice generation under 200ms
    - ✅ Advancement confirmation under 500ms
    - ✅ No N+1 query issues in advancement flows

This comprehensive plan provides a roadmap for implementing equipment-based advancements while maintaining compatibility with the existing system and following established patterns in the Gyrinx codebase.

<function_calls>
<invoke name="TodoWrite">
<parameter name="todos">[{"id": "1", "status": "completed", "content": "Analyze existing advancement system components and data models"}, {"id": "2", "status": "completed", "content": "Create comprehensive implementation plan for ContentAdvancementEquipment model"}, {"id": "3", "status": "in_progress", "content": "Document integration points with existing advancement forms and views"}, {"id": "4", "status": "pending", "content": "Plan database schema and migration strategy"}, {"id": "5", "status": "pending", "content": "Design UI/UX flow for equipment-based advancement selection"}]
