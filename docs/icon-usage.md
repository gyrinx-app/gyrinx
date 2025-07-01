# Icon Usage Documentation

This document describes the Bootstrap Icons (v1.x) used throughout the application. Icons are consistently used across the UI to provide visual context and improve usability.

## Nouns (Objects/Concepts)

| Concept | Icon | Usage Context |
|---------|------|---------------|
| **User/Owner/Fighter** | `bi-person` | User profiles, owner attribution, individual fighters |
| **List/Gang** | `bi-list-ul` | Lists of gangs, gang counts |
| **Campaign** | `bi-award` | Campaign associations, active campaigns |
| **Credits/Cost** | `bi-coin` | Currency values, costs, budgets |
| **Public Visibility** | `bi-eye` | Public/visible content |
| **Private Visibility** | `bi-eye-slash` | Private/hidden content |
| **Information** | `bi-info-circle` | Info messages, help text |
| **Warning** | `bi-exclamation-triangle` | Warnings, alerts |
| **Error** | `bi-x-circle` | Error states |
| **Document/Notes** | `bi-file-text` | Documents, narrative, notes |
| **Battle/Combat** | `bi-crosshair` | Combat, targeting |
| **Victory** | `bi-trophy-fill` | Winners, victories |
| **Death** | `bi-heartbreak` | Dead fighters |
| **Captured** | `bi-person-lock` | Captured fighters |
| **Time/History** | `bi-clock` | Time-based info |
| **Calendar** | `bi-calendar` | Date information |
| **Assets** | `bi-box-seam` | Campaign assets |
| **Dice/Random** | `bi-dice-6` | Dice rolls, randomization |
| **More Options** | `bi-three-dots-vertical` | Dropdown menus |

## Actions (Verbs)

| Action | Icon | Usage Context |
|--------|------|---------------|
| **Add/Create** | `bi-plus-circle` | Primary add actions (buttons) |
| **Edit/Modify** | `bi-pencil` | Edit buttons and actions |
| **Save** | `bi-check-circle` | Save confirmations |
| **Delete/Remove** | `bi-trash` | Delete actions |
| **Archive** | `bi-archive` | Archive/unarchive actions |
| **Transfer** | `bi-arrow-left-right` | Transfer between entities |
| **Back** | `bi-chevron-left` | Back navigation |
| **Forward** | `bi-chevron-right` | Forward navigation, detail links |
| **Refresh/Reload** | `bi-arrow-clockwise` | Refresh, reopen actions |
| **Search** | `bi-search` | Search functionality |
| **Filter** | `bi-funnel` | Filter options |
| **Print** | `bi-printer` | Print functionality |
| **Clone/Copy** | `bi-copy` | Clone/duplicate actions |
| **Start** | `bi-play-circle` | Start campaign |
| **Stop/End** | `bi-stop-circle` | End campaign |
| **Increment** | `bi-plus` | Increase values (inline) |
| **Decrement** | `bi-dash` | Decrease values (inline) |
| **Return** | `bi-arrow-return-left` | Return to previous state |
| **Flag/Mark** | `bi-flag` | Mark or flag items |
| **Embed** | `bi-person-bounding-box` | Embed functionality |
| **Add Fighter** | `bi-person-add` | Add fighter specifically |
| **Approve** | `bi-person-check` | User approval |

## Usage Guidelines

1. **Consistency**: Always use the same icon for the same concept throughout the application
2. **Context**: Icons often appear with text labels for clarity
3. **Size**: Most icons use default size, with `btn-sm` buttons using appropriately sized icons
4. **Color**: Icons inherit text color from their parent element
5. **Tooltips**: Icons without text labels should have tooltips explaining their function
6. **Accessibility**: Icons are decorative; functionality should not depend solely on icon recognition

## Common Patterns

### Action Buttons
- Primary actions: Icon + text label (e.g., `<i class="bi-plus-circle"></i> Add Fighter`)
- Secondary actions: Icon only with tooltip (e.g., `<i class="bi-pencil"></i>`)
- Danger actions: Red colored with appropriate icon (e.g., `<i class="bi-trash"></i>`)

### Status Indicators
- Visibility: `bi-eye` (public) vs `bi-eye-slash` (private)
- State: Badges with icons for captured, dead, archived states

### Navigation
- Back links: `bi-chevron-left` or `bi-arrow-left`
- Detail/forward: `bi-chevron-right`
- Dropdowns: `bi-three-dots-vertical`

### Data Display
- Counts: Icon + number (e.g., `<i class="bi-person"></i> 5 fighters`)
- Currency: `<i class="bi-coin"></i> 100¢`
- Ownership: `<i class="bi-person"></i> username`
