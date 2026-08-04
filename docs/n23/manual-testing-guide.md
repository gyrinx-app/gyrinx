# Manual Testing Guide

This guide provides comprehensive test scenarios for the Gyrinx application, covering basic functionality, expected behaviors, and complex edge cases where multiple features intersect.

## Table of Contents

1. [Authentication & User Management](manual-testing-guide.md#authentication--user-management)
2. [Gang/List Management](manual-testing-guide.md#ganglist-management)
3. [Fighter Management](manual-testing-guide.md#fighter-management)
4. [Equipment & Weapons](manual-testing-guide.md#equipment--weapons)
5. [Fighter Advancement](manual-testing-guide.md#fighter-advancement)
6. [Campaign Management](manual-testing-guide.md#campaign-management)
7. [Campaign Assets & Resources](manual-testing-guide.md#campaign-assets--resources)
8. [Battle Management](manual-testing-guide.md#battle-management)
9. [Captured Fighters](manual-testing-guide.md#captured-fighters)

***

## Authentication & User Management

### Basic Functionality

**User Registration**

- Users can sign up when `ACCOUNT_ALLOW_SIGNUPS=True`
- Registration requires username, email, password with reCAPTCHA verification
- Users are redirected to account home after successful registration and email verification
- When signups are disabled, users cannot sign up

**User Login/Logout**

- Users can log in with username/password
- Session persists across browser sessions
- Logout clears session and redirects to home

**User Profile**

- Public profile page shows user's public lists (later, campaigns)
- Private lists/campaigns are hidden from other users
- Profile URL format: `/user/<username>`

### Test Cases

| Scenario           | Steps                                           | Expected Result          |
| ------------------ | ----------------------------------------------- | ------------------------ |
| Signup disabled    | Set `ACCOUNT_ALLOW_SIGNUPS=False`, visit signup | Signup not available     |
| Duplicate username | Register with existing username                 | Error message displayed  |
| Profile visibility | Create private list, view as another user       | Private list not visible |

***

## Gang/List Management

### Basic Functionality

**List Creation**

- Users create lists with name, house selection, and optional narrative
- Lists can be public or private
- Each list has a unique URL and can be themed with custom colors
- Lists track total cost based on fighters and equipment

**List Management**

- Edit: Change name, narrative, theme color, public status
- Clone: Create a copy with all fighters and equipment
- Archive: Soft delete to hide from active lists
- Delete: Only available in non-campaign mode

**List Building vs Campaign Mode**

- List building mode: Full editing capabilities, can delete fighters
- Campaign mode: Restricted editing, no fighter deletion, credit tracking enabled

### Test Cases

| Scenario             | Steps                                        | Expected Result                            |
| -------------------- | -------------------------------------------- | ------------------------------------------ |
| Clone with equipment | Create list with equipped fighters, clone it | All equipment preserved with correct costs |
| Archive then view    | Archive a list, try to access URL            | Archived message shown, edit disabled      |
| Campaign mode switch | Add list to campaign, check edit options     | Delete fighter option hidden               |
| Public list access   | Create public list, view logged out          | List visible without login                 |

***

## Fighter Management

### Basic Functionality

**Adding Fighters**

- Select from available content fighters based on house
- Fighter cost automatically calculated from template
- Can override cost manually with justification
- Fighters can have custom names and narratives

**Fighter States**

- Active: Normal state, counts toward gang rating
- Recovery: Injured but healing (campaign mode)
- Convalescence: Seriously injured (campaign mode)
- Dead: Killed in campaign, shown struck through
- Captured: Held by another gang, costs 0 credits

**Fighter Management**

- Edit: Name, narrative, stat overrides, cost override
- Clone: Copy within same list or to another list
- Archive: Remove from active roster
- Kill: Mark as dead (campaign only)
- Capture: Mark as captured (campaign only)

**Psyker Powers (Wyrd Powers)**

- Available to psyker-type fighters (e.g., Wyrd, Sanctioned Psyker)
- Powers function like skills but from separate power lists
- Can gain powers through advancement or starting abilities
- Powers organized by discipline (e.g., Biomancy, Telepathy)
- Each power has specific game effects
- Powers shown separately from skills on fighter card
- Some powers are faction-specific

### Test Cases

| Scenario            | Steps                                        | Expected Result                                   |
| ------------------- | -------------------------------------------- | ------------------------------------------------- |
| Cost override       | Override fighter cost to 500, save           | Cost shows as overridden with tooltip             |
| Clone to other list | Clone fighter to different list              | Fighter appears in target list                    |
| State transitions   | Mark fighter recovery → convalescence → dead | States update correctly, cost becomes 0 when dead |
| Captured fighter    | Capture fighter, check original list         | Fighter marked captured, 0 cost                   |
| Add psyker power    | Add Wyrd power to psyker fighter             | Power appears separate from skills                |
| Power advancement   | Advance psyker, select new power             | Power added to fighter's abilities                |

***

## Equipment & Weapons

### Basic Functionality

**Equipment Assignment**

- Weapons and gear assigned separately
- Weapons may have multiple profiles (e.g., close combat vs ranged)
- Fighters may have default assignments
- Equipment can have accessories (scopes, suspensors)
- Equipment can have upgrades (Tiers, Cyberteknika)
- Costs cascade: base → profile → accessories → upgrades

**Equipment Accessories & Modifications**

- Accessories enhance equipment functionality (e.g., telescopic sight, suspensor)
- Each accessory has specific equipment type restrictions
- Multiple accessories can stack on single item
- Accessories add to base equipment cost
- Some accessories modify weapon stats or grant special rules
- Cannot remove accessories individually (must remove whole equipment)
- Common accessories: Las-projector, Infra-sight, Telescopic sight, Suspensor

**Default Equipment**

- Fighters from content templates come with default equipment pre-assigned
- Default equipment shows with a "default" badge and costs 0 credits
- Can disable default equipment to remove it from fighter
- Can convert default equipment to purchasable (fighter must pay cost)
- Converting to purchasable creates a normal equipment assignment

**Equipment-Fighter Links (Pets/Exotic Beasts)**

- Some equipment creates additional fighters when assigned (e.g., Cyber-mastiff creates a fighter)
- Child fighters appear in gang roster with special "child" indicator
- Child fighters cannot be independently edited or removed
- Removing the parent equipment removes the child fighter
- Child fighters count toward gang rating and cost

**Equipment-Equipment Links**

- Some equipment automatically adds other equipment when assigned
- Example: Certain weapons might come with built-in accessories
- Linked equipment cannot be removed independently
- Removing parent equipment removes all linked equipment
- Linked equipment costs are included in parent item cost
- Equipment links cascade (A creates B, B creates C)

**Equipment Lists**

- Fighters may have specific equipment lists affecting costs/availability
- Venator gangs have special access rules for equipment
- House-specific equipment restricted to that house
- Generic equipment available to all

**Equipment Management**

- Reassign: Transfer equipment between fighters
- Sell: Stash fighters can sell equipment (campaign mode)
- Cost override: Manual price adjustment
- Default equipment: Can disable or convert to purchasable

### Test Cases

| Scenario                     | Steps                                             | Expected Result                                   |
| ---------------------------- | ------------------------------------------------- | ------------------------------------------------- |
| Multi-profile weapon         | Add plasma gun, select different profiles         | Each profile shows correct stats                  |
| Accessory stacking           | Add weapon, add multiple accessories              | All accessories shown, costs sum correctly        |
| Equipment list pricing       | Add equipment with fighter-specific price         | Custom price from equipment list used             |
| Venator equipment            | Create Venator gang, check available equipment    | Access to items from all houses                   |
| Default equipment conversion | Fighter with default gear, convert to purchasable | Equipment now costs credits, can be sold          |
| Equipment creates fighter    | Add Cyber-mastiff to fighter                      | New mastiff fighter appears linked to equipment   |
| Equipment creates equipment  | Add weapon with built-in accessory                | Both items appear, linked equipment not removable |
| Remove child fighter parent | Delete equipment that created fighter             | Child fighter also removed from gang             |
| Cascade equipment links      | Add equipment A that creates B that creates C     | All three items present, removing A removes all   |
| Default equipment disable    | Disable default weapon on fighter                 | Weapon removed, fighter cost unchanged            |
| Multiple accessories         | Add telescopic sight + suspensor to weapon        | Both show, costs stack correctly                  |
| Accessory restrictions       | Try adding melee accessory to ranged weapon       | Accessory not available in list                   |

***

## Fighter Advancement

### Basic Functionality

**XP Management**

- Add/spend/reduce XP with transaction logging
- Current XP = available to spend
- Total XP = lifetime earned
- XP only available in campaign mode

**Advancement System**

- Choice: 2D6 roll or manual selection
- Types: Stat improvement, skill gain, specialist promotion, other
- Stats: M, WS, BS, S, T, W, I, A, Ld, Cl, Wil, Int
- Skills: Limited to primary/secondary categories unless promoted
- Cost: Each advancement costs XP and increases fighter cost

**Stat Improvements**

- Numeric stats (S, T, W) increase by 1
- "+" stats (WS 4+, BS 3+) improve by reducing number
- Maximums are left to the player

### Test Cases

| Scenario            | Steps                                                    | Expected Result                           |
| ------------------- | -------------------------------------------------------- | ----------------------------------------- |
| Insufficient XP     | Try advancement with 0 XP                                | Error: insufficient XP                    |
| + stat improvement  | Improve WS from 4+ to 3+                                 | Number decreases (improvement)            |
| Skill categories    | Check available skills before/after specialist promotion | More categories available after promotion |
| Roll integration    | Use 2D6 roll option, check campaign action               | Dice results recorded in action           |
| Already owned skill | Try to select skill fighter already has                  | Skill not available in selection          |

***

## Campaign Management

### Basic Functionality

**Campaign Creation**

- Set name, description, start date, budget
- Public/private visibility
- Pre-campaign → In Progress → Post-campaign lifecycle

**Starting Campaign**

- All participating lists are cloned
- Starting budget distributed based on gang cost
- Lists enter campaign mode (restricted editing)

**Campaign Operations**

- Add new lists mid-campaign (with cloning)
- End campaign (locks all changes)
- Reopen campaign (allows continued play)
- Campaign actions log all significant events

**Campaign Actions**

- Central logging system for all campaign events
- Can be created by any participant or campaign owner
- Actions can reference: battles, specific lists, or general campaign
- Supports rich text descriptions with formatting
- Optional dice rolling integration (D3, D6, 2D6, D66, etc.)
- Dice results stored and displayed with action
- Actions appear in chronological campaign history
- Used for: battle outcomes, territory rolls, injury rolls, advancement rolls
- Linked to fighter advancement when using roll option
- Can track any campaign event (trades, alliances, narrative events)

### Test Cases

| Scenario              | Steps                                          | Expected Result                                       |
| --------------------- | ---------------------------------------------- | ----------------------------------------------------- |
| Budget distribution   | Start campaign with 1000¢ budget, uneven gangs | Each gang gets credits inversely proportional to cost |
| Mid-campaign addition | Add list after campaign started                | List cloned, enters at current campaign state         |
| End then reopen       | End campaign, try edits, then reopen           | Edits blocked when ended, allowed when reopened       |
| Clone tracking        | View campaign clones for a list                | All campaign versions shown chronologically           |
| Action with dice      | Create action, roll 2D6                        | Dice results shown (e.g., "5, 3 = 8")                 |
| Battle-linked action  | Create battle, then action referencing it      | Action shows battle context                           |
| List-specific action  | Create action for specific gang                | Action appears in gang's history                      |
| Advancement dice link | Use dice roll in fighter advancement           | Same roll appears in campaign action                  |

***

## Campaign Assets & Resources

### Basic Functionality

**Asset Management**

- Campaign owner defines asset types (e.g., Territories)
- Assets assigned to specific gangs
- Assets can be transferred between gangs
- Assets shown in gang's campaign view

**Resource Management**

- Campaign owner defines resource types (e.g., Meat, Ammo)
- Resources tracked per gang with quantities
- Can add/subtract resources with validation
- Cannot go below 0 resources

### Test Cases

| Scenario             | Steps                                         | Expected Result                               |
| -------------------- | --------------------------------------------- | --------------------------------------------- |
| Asset transfer       | Transfer territory between gangs              | Asset ownership updates correctly             |
| Resource depletion   | Try to subtract more resources than available | Error: would go negative                      |
| Multiple resources   | Add multiple resource types to gang           | All shown with correct quantities             |
| Archived gang assets | Archive gang with assets                      | Assets still visible but gang marked archived |

***

## Battle Management

### Basic Functionality

**Battle Creation**

- Date, mission type, participating gangs
- Can have single winner, multiple winners, or draw
- Rich text notes for battle report
- Links to campaign for context

**Battle Integration**

- Campaign actions can reference battles
- Fighter injuries/deaths typically happen in battles
- Resource/asset changes often tied to battle outcomes

### Test Cases

| Scenario        | Steps                                     | Expected Result                 |
| --------------- | ----------------------------------------- | ------------------------------- |
| Draw scenario   | Create battle with no winners             | "Draw" shown as outcome         |
| Multi-winner    | Select multiple gangs as winners          | All winners displayed           |
| Battle ordering | Create battles out of chronological order | Sorted by date in campaign view |
| Note formatting | Add formatted text with images            | Rich content preserved          |

***

## Captured Fighters

### Basic Functionality

**Capture System**

- Fighters can be captured by enemy gangs
- Captured fighters cost 0 for original gang
- Cannot participate in battles while captured
- Equipment stays with fighter

**Captured Fighter Options**

- Sell to Guilders: Permanent removal, gang gets credits
- Return to Owner: Fighter goes back to original gang
- Hold: Keep captured (no benefit but denies enemy)

**Campaign Integration**

- Capture creates campaign action
- Sale/return creates campaign action
- Can link to battle where capture occurred

### Test Cases

| Scenario               | Steps                                 | Expected Result                        |
| ---------------------- | ------------------------------------- | -------------------------------------- |
| Capture with equipment | Capture equipped fighter              | Equipment shown but unusable           |
| Sell to guilders       | Sell captured fighter                 | Fighter permanently unavailable        |
| Return with ransom     | Return fighter to owner               | Fighter active again for original gang |
| Multiple captures      | Capture, return, capture again        | Full history in campaign actions       |
| Cost calculation       | Check gang cost with captured fighter | Captured fighter = 0 credits           |
