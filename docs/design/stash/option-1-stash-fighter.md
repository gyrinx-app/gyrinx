# Gang Stash - Stash Fighter Implementation (Option 1)

## Overview

This document provides detailed implementation specifications for the gang stash feature using the "stash fighter" approach. This design maximizes reuse of existing infrastructure by treating the stash as a special fighter that holds unassigned equipment.

## Architecture

### Core Concept
- Create a special `ListFighter` with `is_stash=True` flag
- This fighter acts as a container for unassigned equipment
- Reuses the existing `ListFighterEquipmentAssignment` system
- Credits tracked separately on the `List` model

### Key Benefits
- All equipment assignment logic works unchanged
- Cost calculation automatic
- History tracking via existing systems
- UI components largely reusable

## Model Changes

### 1. ListFighter Model
```python
# core/models/fighter.py
class ListFighter(AppBase):
    # New field
    is_stash = models.BooleanField(
        default=False,
        help_text="Is this a special stash fighter for equipment storage?"
    )

    class Meta:
        # Existing meta...
        constraints = [
            models.CheckConstraint(
                check=~Q(is_stash=True, injury_state__in=['recovery', 'convalescence', 'dead']),
                name="stash_fighter_always_active"
            )
        ]

# Custom manager to exclude stash fighters by default
class ActiveListFighterManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_stash=False)

# Update ListFighter to use both managers
class ListFighter(AppBase):
    objects = models.Manager()  # Default manager includes stash
    active = ActiveListFighterManager()  # Excludes stash fighters
```

### 2. List Model Updates
```python
# core/models/list.py
class List(AppBase):
    # New field for credits
    campaign_credits = models.IntegerField(
        default=0,
        help_text="Credits available in campaign stash"
    )

    @cached_property
    def fighters_cached(self):
        """Return non-stash fighters only."""
        return list(self.fighters.filter(is_stash=False).order_by("created"))

    @cached_property
    def stash_fighter(self):
        """Return the stash fighter if in campaign mode."""
        if self.status == self.CAMPAIGN_MODE:
            return self.fighters.filter(is_stash=True).first()
        return None

    @property
    def total_wealth(self):
        """Calculate total gang wealth including stash."""
        base_value = self.cost_int  # Active fighters + their equipment

        if self.status == self.CAMPAIGN_MODE:
            # Add stash equipment value
            stash = self.stash_fighter
            if stash:
                base_value += stash.cost_int
            # Add campaign credits
            base_value += self.campaign_credits

        return base_value

    def clone(self, name=None, owner=None, for_campaign=None):
        """Clone the list, creating stash fighter if for campaign."""
        # ... existing clone logic ...

        if for_campaign:
            cloned_list.status = self.CAMPAIGN_MODE
            cloned_list.save()

            # Calculate initial credits
            initial_credits = for_campaign.budget - cloned_list.cost_int
            cloned_list.campaign_credits = max(0, initial_credits)
            cloned_list.save()

            # Create stash fighter
            self._create_stash_fighter(cloned_list, owner or self.owner)

        return cloned_list

    def _create_stash_fighter(self, for_list, user):
        """Create the stash fighter for a campaign list."""
        stash_content = ContentFighter.objects.get(
            type="Equipment Stash",
            house__generic=True
        )

        return ListFighter.objects.create_with_user(
            list=for_list,
            content_fighter=stash_content,
            name=f"{for_list.name} Stash",
            is_stash=True,
            user=user
        )
```

## Data Setup

### ContentFighter for Stash
```python
# Data migration: create_stash_content_fighter
def create_stash_content_fighter(apps, schema_editor):
    ContentFighter = apps.get_model('content', 'ContentFighter')
    ContentHouse = apps.get_model('content', 'ContentHouse')

    # Find or create generic house
    generic_house, _ = ContentHouse.objects.get_or_create(
        name="Universal",
        defaults={'generic': True, 'description': 'Generic game elements'}
    )

    # Create stash fighter type
    ContentFighter.objects.get_or_create(
        type="Equipment Stash",
        house=generic_house,
        defaults={
            'name': "Equipment Stash",
            'category': "HANGER_ON",
            'base_cost': 0,
            'can_be_purchased': False,
            'can_be_leader': False,
            # All stats at 99 (displays as "-" in templates)
            'movement': 99,
            'weapon_skill': 99,
            'ballistic_skill': 99,
            'strength': 99,
            'toughness': 99,
            'wounds': 99,
            'initiative': 99,
            'attacks': 99,
            'leadership': 99,
            'cool': 99,
            'willpower': 99,
            'intelligence': 99,
        }
    )
```

## User Interface

### 1. Stash Display Card
```django
<!-- templates/core/includes/stash_card.html -->
<div class="card g-col-12 border-info">
    <div class="card-header bg-info bg-opacity-10 p-2">
        <div class="hstack">
            <h3 class="h5 mb-0">
                <i class="bi-box-seam"></i> Equipment Stash
            </h3>
            <div class="ms-auto hstack gap-2">
                <span class="badge bg-success">
                    <i class="bi-currency-dollar"></i> {{ list.campaign_credits }} Credits
                </span>
                <span class="badge text-bg-primary">
                    <i class="bi-box"></i> {{ stash.cost_int_cached }} Equipment
                </span>
            </div>
        </div>
    </div>
    <div class="card-body p-2">
        {% if stash.equipment_assignments.exists %}
            <div class="table-responsive">
                <table class="table table-sm mb-2">
                    <thead>
                        <tr>
                            <th>Equipment</th>
                            <th>Enhancements</th>
                            <th class="text-end">Value</th>
                            <th width="150">Actions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for assignment in stash.equipment_assignments.select_related.all %}
                            <tr>
                                <td>
                                    {{ assignment.content_equipment.name }}
                                    {% if assignment.content_equipment.is_weapon %}
                                        <i class="bi-shield-fill-exclamation text-warning"
                                           title="Weapons cannot be discarded"></i>
                                    {% endif %}
                                </td>
                                <td>
                                    {% if assignment.weapon_profiles_field.exists %}
                                        {% for profile in assignment.weapon_profiles_field.all %}
                                            <span class="badge bg-secondary">{{ profile.name }}</span>
                                        {% endfor %}
                                    {% endif %}
                                    {% if assignment.weapon_accessories_field.exists %}
                                        {% for acc in assignment.weapon_accessories_field.all %}
                                            <span class="badge bg-info">{{ acc.name }}</span>
                                        {% endfor %}
                                    {% endif %}
                                </td>
                                <td class="text-end">{{ assignment.cost_display }}</td>
                                <td>
                                    <div class="btn-group btn-group-sm" role="group">
                                        <a href="{% url 'core:stash-assign' list.id assignment.id %}"
                                           class="btn btn-outline-primary">
                                            <i class="bi-person-plus"></i> Assign
                                        </a>
                                        <a href="{% url 'core:stash-sell' list.id assignment.id %}"
                                           class="btn btn-outline-danger">
                                            <i class="bi-currency-dollar"></i> Sell
                                        </a>
                                    </div>
                                </td>
                            </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        {% else %}
            <p class="text-muted mb-2">No equipment in stash. Equipment from dead or retired fighters will appear here.</p>
        {% endif %}

        <div class="d-flex gap-2 flex-wrap">
            <a href="{% url 'core:trading-post' list.id %}"
               class="btn btn-sm btn-primary">
                <i class="bi-shop"></i> Trading Post ({{ list.campaign_credits }} credits)
            </a>
            {% if stash %}
                <a href="{% url 'core:list-fighter-weapons-edit' list.id stash.id %}"
                   class="btn btn-sm btn-secondary">
                    <i class="bi-plus"></i> Add Equipment to Stash
                </a>
            {% endif %}
        </div>
    </div>
    <div class="card-footer bg-transparent p-2 text-muted small">
        <i class="bi-info-circle"></i>
        <strong>Total Wealth:</strong> {{ list.total_wealth }}
        (Fighters: {{ list.cost_int }}, Stash: {{ stash.cost_int_cached|default:0 }}, Credits: {{ list.campaign_credits }})
    </div>
</div>
```

### 2. Integration into List View
```django
<!-- Update templates/core/includes/list.html -->
<div class="grid {% if print %}gap-2{% endif %}">
    {% if not print %}
        {% include "core/includes/list_campaign_actions.html" with list=list %}
        {% include "core/includes/list_campaign_resources_assets.html" %}

        <!-- Add stash card for campaign mode -->
        {% if list.status == 'campaign_mode' and list.stash_fighter %}
            {% include "core/includes/stash_card.html" with stash=list.stash_fighter %}
        {% endif %}
    {% endif %}

    <!-- Regular fighters (stash excluded via fighters_cached) -->
    {% for fighter in list.fighters_cached %}
        {% include "core/includes/fighter_card.html" with fighter=fighter list=list %}
    {% empty %}
        <div class="g-col-12 py-2">This List is empty.</div>
    {% endfor %}
</div>
```

## Core Operations

### 1. Equipment Transfer to Stash
```python
# core/views/stash.py
@login_required
def transfer_to_stash(request, list_id, assignment_id):
    """Move equipment from fighter to stash."""
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        id=assignment_id,
        list_fighter__list_id=list_id,
        list_fighter__list__owner=request.user,
        list_fighter__is_stash=False  # Can't transfer from stash to stash
    )

    list_obj = assignment.list_fighter.list
    if list_obj.status != List.CAMPAIGN_MODE:
        messages.error(request, "Stash only available in campaign mode")
        return redirect('core:list', list_id)

    stash = list_obj.stash_fighter
    if not stash:
        messages.error(request, "No stash available")
        return redirect('core:list', list_id)

    # Clone to stash (preserves all enhancements and overrides)
    fighter_name = assignment.list_fighter.name
    equipment_name = assignment.content_equipment.name

    new_assignment = assignment.clone()
    new_assignment.list_fighter = stash
    new_assignment.save_with_user(user=request.user)

    # Delete original
    assignment.delete()

    # Update fighter cost
    assignment.list_fighter.calculate_cost()

    # Log the transfer
    log_campaign_action(
        list_obj,
        f"Moved {equipment_name} from {fighter_name} to stash",
        user=request.user
    )

    messages.success(request, f"Moved {equipment_name} to stash")
    return redirect(request.META.get('HTTP_REFERER', f'/list/{list_id}'))
```

### 2. Assign from Stash
```python
@login_required
def assign_from_stash(request, list_id, assignment_id):
    """Assign equipment from stash to a fighter."""
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        id=assignment_id,
        list_fighter__is_stash=True,
        list_fighter__list_id=list_id,
        list_fighter__list__owner=request.user
    )

    if request.method == 'POST':
        fighter_id = request.POST.get('fighter_id')
        fighter = get_object_or_404(
            ListFighter,
            id=fighter_id,
            list_id=list_id,
            is_stash=False
        )

        # Validate assignment
        equipment = assignment.content_equipment
        if not fighter.can_take_equipment(equipment):
            messages.error(request, f"{fighter.name} cannot use {equipment.name}")
            return redirect('core:stash-assign', list_id, assignment_id)

        # Check weapon limits
        if equipment.is_weapon:
            current_weapons = fighter.get_weapon_count()
            weapon_spaces = 2 if equipment.has_trait('Unwieldy') else 1
            if current_weapons + weapon_spaces > 3:
                messages.error(request, f"{fighter.name} cannot carry more weapons")
                return redirect('core:stash-assign', list_id, assignment_id)

        # Transfer equipment
        new_assignment = assignment.clone()
        new_assignment.list_fighter = fighter
        new_assignment.save_with_user(user=request.user)

        # Delete from stash
        assignment.delete()

        # Update costs
        fighter.calculate_cost()

        # Log
        log_campaign_action(
            fighter.list,
            f"Assigned {equipment.name} from stash to {fighter.name}",
            user=request.user
        )

        messages.success(request, f"Assigned {equipment.name} to {fighter.name}")
        return redirect('core:list', list_id)

    # Show fighter selection form
    eligible_fighters = assignment.list_fighter.list.fighters.filter(
        is_stash=False,
        injury_state='active'
    )

    return render(request, 'core/stash_assign.html', {
        'assignment': assignment,
        'eligible_fighters': eligible_fighters,
        'list': assignment.list_fighter.list,
    })
```

### 3. Sell Equipment
```python
@login_required
def sell_equipment(request, list_id, assignment_id):
    """Sell equipment from stash for credits."""
    assignment = get_object_or_404(
        ListFighterEquipmentAssignment,
        id=assignment_id,
        list_fighter__is_stash=True,
        list_fighter__list_id=list_id,
        list_fighter__list__owner=request.user
    )

    if request.method == 'POST':
        # Calculate sale value
        base_value = assignment.cost_int
        dice_roll = random.randint(1, 6)
        reduction = dice_roll * 10
        sale_value = max(5, base_value - reduction)

        # Update credits
        list_obj = assignment.list_fighter.list
        list_obj.campaign_credits += sale_value
        list_obj.save_with_user(user=request.user)

        # Delete equipment
        equipment_name = assignment.content_equipment.name
        assignment.delete()

        # Log sale
        log_campaign_action(
            list_obj,
            f"Sold {equipment_name} for {sale_value} credits "
            f"(base {base_value}, rolled {dice_roll}, -{reduction})",
            user=request.user,
            dice_rolls={'d6': dice_roll}
        )

        messages.success(
            request,
            f"Sold {equipment_name} for {sale_value} credits! (Rolled {dice_roll})"
        )
        return redirect('core:list', list_id)

    # Show confirmation
    return render(request, 'core/stash_sell_confirm.html', {
        'assignment': assignment,
        'min_value': max(5, assignment.cost_int - 60),
        'max_value': max(5, assignment.cost_int - 10),
        'list': assignment.list_fighter.list,
    })
```

### 4. Trading Post Integration
```python
@login_required
def trading_post_purchase(request, list_id, equipment_id):
    """Purchase equipment from trading post."""
    list_obj = get_object_or_404(
        List,
        id=list_id,
        owner=request.user,
        status=List.CAMPAIGN_MODE
    )
    equipment = get_object_or_404(
        ContentEquipment,
        id=equipment_id,
        trading_post_available=True
    )

    # Check credits
    if list_obj.campaign_credits < equipment.cost:
        messages.error(request, f"Need {equipment.cost} credits, have {list_obj.campaign_credits}")
        return redirect('core:trading-post', list_id)

    # Get stash
    stash = list_obj.stash_fighter
    if not stash:
        stash = list_obj._create_stash_fighter(list_obj, request.user)

    # Create assignment
    assignment = ListFighterEquipmentAssignment.objects.create_with_user(
        list_fighter=stash,
        content_equipment=equipment,
        user=request.user
    )

    # Handle weapon profiles if needed
    if equipment.weapon_profiles.exists():
        # ... profile selection logic ...
        pass

    # Deduct credits
    list_obj.campaign_credits -= equipment.cost
    list_obj.save_with_user(user=request.user)

    # Log purchase
    log_campaign_action(
        list_obj,
        f"Purchased {equipment.name} from Trading Post for {equipment.cost} credits",
        user=request.user
    )

    messages.success(request, f"Purchased {equipment.name} for {equipment.cost} credits")
    return redirect('core:list', list_id)
```

### 5. Handle Fighter Death
```python
def handle_fighter_death(fighter, user=None):
    """Transfer all equipment from dead fighter to stash."""
    if fighter.list.status != List.CAMPAIGN_MODE:
        return

    stash = fighter.list.stash_fighter
    if not stash:
        stash = fighter.list._create_stash_fighter(fighter.list, user or fighter.owner)

    # Transfer all equipment
    transferred = []
    for assignment in fighter.equipment_assignments.all():
        equipment_name = assignment.content_equipment.name
        cloned = assignment.clone()
        cloned.list_fighter = stash
        cloned.save_with_user(user=user or fighter.owner)
        transferred.append(equipment_name)

    # Clear fighter's equipment
    fighter.equipment_assignments.all().delete()
    fighter.calculate_cost()

    # Log transfer
    if transferred:
        log_campaign_action(
            fighter.list,
            f"{fighter.name} died. Equipment transferred to stash: {', '.join(transferred)}",
            user=user or fighter.owner
        )
```

## Migration Strategy

### 1. Schema Migration
```python
# core/migrations/00XX_add_stash_support.py
class Migration(migrations.Migration):
    dependencies = [
        ('core', '00XX_previous'),
    ]

    operations = [
        migrations.AddField(
            model_name='listfighter',
            name='is_stash',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='historicallistfighter',
            name='is_stash',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='list',
            name='campaign_credits',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='historicallist',
            name='campaign_credits',
            field=models.IntegerField(default=0),
        ),
    ]
```

### 2. Management Command for Existing Campaigns
```python
# core/management/commands/create_stash_fighters.py
class Command(BaseCommand):
    help = 'Create stash fighters for existing campaign lists'

    def handle(self, *args, **options):
        stash_content = ContentFighter.objects.get(
            type="Equipment Stash",
            house__generic=True
        )

        campaign_lists = List.objects.filter(
            status=List.CAMPAIGN_MODE
        ).exclude(
            fighters__is_stash=True
        )

        created = 0
        for list_obj in campaign_lists:
            ListFighter.objects.create(
                list=list_obj,
                content_fighter=stash_content,
                name=f"{list_obj.name} Stash",
                is_stash=True
            )
            created += 1

        self.stdout.write(
            self.style.SUCCESS(f'Created {created} stash fighters')
        )
```

## Testing Considerations

### Key Test Cases
1. Stash fighter creation during campaign entry
2. Equipment transfer preserves all enhancements
3. Fighter validation when assigning from stash
4. Credit calculations for sales
5. Stash fighter excluded from normal fighter lists
6. Dead fighter equipment transfer
7. Trading post purchase with insufficient credits
8. Weapon limit enforcement

### Performance Considerations
- Add `select_related` for stash equipment queries
- Cache stash fighter reference on List
- Ensure stash fighters excluded from fighter counts
- Index on `is_stash` field if performance issues

## Future Enhancements

1. **Bulk Operations**: Transfer multiple items at once
2. **Equipment Sets**: Handle vehicle equipment as a group
3. **Quick Actions**: Drag-and-drop interface for transfers
4. **Stash Categories**: Organize by equipment type
5. **Loan System**: Borrow credits with interest mechanics
