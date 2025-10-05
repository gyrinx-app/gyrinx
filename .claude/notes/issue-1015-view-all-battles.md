# Issue #1015: View all X battles implementation

## Overview

Implement the "View all battles" link functionality for campaigns that currently points to "#".

## Tasks

- [x] Create .claude/notes directory and todo file
- [ ] Extract battle summary card into reusable include
- [ ] Create URL pattern for campaign battles list (`campaign/<id>/battles`)
- [ ] Create view for battles list
- [ ] Create template for battles list
- [ ] Update campaign.html link to use new URL
- [ ] Run formatting
- [ ] Run tests
- [ ] Commit and push changes

## Implementation Details

### Battle Summary Card

Extract from `campaign.html` lines 302-323 into `core/includes/battle_summary_card.html`

### URL Pattern

Add to `urls.py` around line 530 (after resources, before individual battle paths):

```python
path(
    "campaign/<id>/battles",
    campaign.campaign_battles,
    name="campaign-battles",
),
```

### View

Add to `views/campaign.py`:

- Function or class to list all battles for a campaign
- Reuse same prefetching as campaign overview (lines 185-188)
- No limit on battles returned

### Template

Create `core/templates/core/campaign/campaign_battles.html`:

- Extend base layout
- Display all battles using the extracted include
- Similar structure to campaign overview

### Link Update

In `campaign.html` line 327:
Change `href="#"` to `href="{% url 'core:campaign-battles' campaign.id %}"`
