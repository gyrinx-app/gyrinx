# Weapon Display Logic Documentation

## Overview
The weapon display in Gyrinx follows a specific hierarchy to show weapon profiles (statlines) correctly. This document explains how weapons are displayed in list views and how this should be replicated in edit views.

## Key Concepts

### Profile Types
1. **Standard Profiles** (`cost=0`): Free profiles that come with the weapon by default
   - Usually represent the base weapon statline
   - Automatically included when weapon is assigned
   - Not selectable/removable by users

2. **Non-Standard/Paid Profiles** (`cost>0`): Optional profiles that cost extra
   - Represent special ammo types or firing modes
   - Must be explicitly selected by users
   - Can be added/removed individually

### Display Logic (from `list_fighter_weapon_rows.html`)

The template uses the following logic to display weapons:

#### Case 1: Single Profile Weapon
```
if assign.all_profiles_cached|length == 1:
    - Display weapon name + single statline
    - Show traits if present
```

#### Case 2: Multi-Profile Weapon
```
if assign.all_profiles_cached|length > 1:
    # Check if first standard profile is named
    if first_standard_profile.name != "":
        - Show weapon name as header row

    # Display all standard profiles (free ones)
    for profile in assign.standard_profiles_cached:
        if first profile AND unnamed:
            - Show weapon name inline with statline
        else if named:
            - Show "- ProfileName" with statline

    # Display all non-standard profiles (paid ones)
    for profile in assign.weapon_profiles_display:
        - Show "- ProfileName (cost)" with statline
```

## Data Sources

- `assign.all_profiles_cached`: All profiles (standard + selected paid)
- `assign.standard_profiles_cached`: Only standard/free profiles (cost=0)
- `assign.weapon_profiles_display`: Only selected paid profiles (cost>0)

## Implementation for Edit View

The weapon edit view (`list_fighter_weapon_edit.html`) should:

1. **Always show standard profiles** as the base weapon statline(s)
   - These are not editable/removable
   - Display them at the top like the main weapon stats

2. **Show selected paid profiles** below the standard ones
   - These have delete buttons
   - Show their additional cost

3. **Available profiles section** should only show unassigned paid profiles
   - Never show standard profiles here (they're automatic)
   - Only show profiles not already selected

## Key Methods

### VirtualListFighterEquipmentAssignment
- `standard_profiles_cached`: Returns list of VirtualWeaponProfile objects for standard profiles
- `weapon_profiles_display`: Returns list of dicts with paid profiles and their costs
- `all_profiles_cached`: Returns combined list of all profiles

### Profile Cost Calculation
- Standard profiles: Always 0 cost (free)
- Paid profiles: Use `profile_cost_int()` to get actual cost (may have fighter-specific overrides)
