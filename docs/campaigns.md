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

## Data Model

### Core Models

- **Campaign** - Main campaign entity with lifecycle state
- **CampaignList** - Join table linking campaigns to lists
- **CampaignAction** - Action log entries with optional dice rolls
- **CampaignAssetType** - Custom asset type definitions
- **CampaignAsset** - Individual assets assignable to gangs
- **CampaignResourceType** - Resource type definitions
- **CampaignResource** - Per-gang resource quantities

### Key Methods

- `Campaign.start()` - Transitions to In Progress, clones lists, allocates resources
- `Campaign.end()` - Transitions to Post-Campaign, locks modifications
- `List.clone()` - Creates campaign-specific copy of a list

## Permissions

Permission checks are implemented in views and enforced at the model level:

- **Campaign Owner** (`campaign.owner == request.user`): Full control
- **List Owners** (`list.owner == request.user`): Can modify own resources and log actions
- **Other Users**: Read-only access to public campaigns

## Technical Implementation

- Lists are cloned via `List.clone()` when campaign starts to preserve state
- All modifications tracked with django-simple-history
- Action logs are immutable once created
- Resources use `F()` expressions for atomic operations

## Related Documentation

- [Lists](lists.md) - List system and campaign integration
- [Models and Database](developing-gyrinx/models-and-database.md) - Data model documentation
- [History Tracking](developing-gyrinx/history-tracking.md) - How modifications are tracked
