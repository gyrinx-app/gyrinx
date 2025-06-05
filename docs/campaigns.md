# Campaigns

Campaigns are a core feature of Gyrinx that allow users to organize and track multi-game narratives with multiple participating gangs (lists). The campaign system provides tools for tracking progress, managing shared resources, and creating collaborative storytelling experiences.

## Overview

A campaign in Gyrinx represents a series of connected games with:
- Multiple participating gangs (lists)
- Shared narrative and tracking
- Asset management (territories, relics, etc.)
- Resource tracking (credits, supplies, etc.)
- Action logging with optional dice rolls

## Campaign Lifecycle

Campaigns progress through three distinct phases:

### Pre-Campaign
- Initial setup phase
- Add participating lists
- Define asset types and resource types
- Set up campaign narrative

### In Progress
- Active gaming phase
- Lists are cloned for campaign-specific tracking
- Resources are allocated
- Players can log actions and outcomes
- Assets can be transferred between gangs
- Resources can be modified

### Post-Campaign
- Archived state
- No further modifications allowed
- Historical record preserved

## Campaign Features

### Action Logging

Players can log actions during the campaign with:
- Descriptive text of what happened
- Optional dice rolls (D6)
- Outcome recording
- Automatic timestamp and user tracking

Example actions:
- "Ambushed rival gang in Sector 7"
- "Explored abandoned manufactorum" (with 2D6 roll)
- "Negotiated trade agreement"

### Asset Management

Campaign owners can define custom asset types:
- **Name**: Singular and plural forms (e.g., "Territory" / "Territories")
- **Description**: Rich text description of the asset type
- **Individual Assets**: Named items that can be held by gangs

Assets can be:
- Created by campaign owner
- Assigned to specific gangs
- Transferred between gangs
- Tracked with full history

Common asset types:
- Territories (specific locations)
- Relics (unique items)
- Alliances (political connections)
- Contracts (ongoing agreements)

### Resource Tracking

Resources represent countable items shared across the campaign:
- **Name**: Resource identifier (e.g., "Credits", "Ammunition")
- **Description**: What the resource represents
- **Default Amount**: Starting quantity for each gang
- **Modifications**: Add or subtract amounts

Resource features:
- Automatically allocated when campaign starts
- Cannot go below zero
- Modifications create action log entries
- Both campaign and list owners can modify

## Managing Campaigns

### Creating a Campaign

1. Navigate to Campaigns (if you have access)
2. Click "Create Campaign"
3. Enter name, summary, and narrative
4. Choose visibility (public/private)
5. Save campaign

### Adding Lists

In pre-campaign phase:
1. Click "Add Lists" from campaign page
2. Search for lists by name or owner
3. Add your own lists or public lists
4. Lists must be in "List Building" status

### Starting the Campaign

When ready to begin:
1. Ensure all lists are added
2. Click "Start Campaign"
3. Lists are cloned for campaign tracking
4. Resources are allocated
5. Campaign enters "In Progress" phase

### During the Campaign

Players can:
- Log actions with narrative descriptions
- Roll dice for random outcomes
- Transfer assets between gangs
- Modify resource amounts
- Update gang progress

Campaign owners can:
- Create new asset types and assets
- Create new resource types
- Manage all transfers and modifications
- End the campaign when complete

## Permissions

- **Campaign Owner**: Full control over campaign, assets, and resources
- **List Owners**: Can modify their own resources and log actions
- **Other Users**: Can view public campaigns

## Best Practices

1. **Plan Asset Types**: Define meaningful asset types that drive narrative
2. **Resource Balance**: Set appropriate default amounts for resources
3. **Regular Updates**: Encourage players to log actions after each game
4. **Rich Narratives**: Use the description fields to add flavor
5. **Asset Stories**: Give assets interesting names and descriptions

## Technical Notes

- Lists are cloned when campaign starts to preserve state
- All modifications are tracked with full history
- Action logs are immutable once created
- Resources use atomic operations to prevent conflicts
