# View Inventory

## Test Data

- **User:** test1 (id=4)
- **List:** Example Orlock Gang (id=83b0a055-4b01-45ef-a9c2-7fa548924681)
- **Fighter:** id=4d3af0b2-4c3e-4bac-9b21-ca9854ce3fea
- **Campaign:** Force Jets (id=000cb156-e4b5-4157-8904-b0a5cee0148d, pre_campaign)
- **Pack:** Debug Pack (id=1478041d-878e-4e53-a9ad-54114716f0f0)
- **Base URL:** http://localhost:8080

## Auth

Login as `test1` before visiting authenticated views.

## Views to Screenshot

### Public Pages (no auth required)

| # | View Name | URL | States | Notes |
|---|-----------|-----|--------|-------|
| 1 | Home (logged out) | `/` | 1 | Landing page |
| 2 | Lists index | `/lists/` | 1 | Public list browser |
| 3 | Campaigns index | `/campaigns/` | 1 | Public campaigns |
| 4 | List detail | `/list/83b0a055-4b01-45ef-a9c2-7fa548924681` | 1 | Gang view |
| 5 | List about | `/list/83b0a055-4b01-45ef-a9c2-7fa548924681/about` | 1 | Lore tab |
| 6 | List notes | `/list/83b0a055-4b01-45ef-a9c2-7fa548924681/notes` | 1 | Notes tab |
| 7 | List print | `/list/83b0a055-4b01-45ef-a9c2-7fa548924681/print` | 1 | Print view |
| 8 | Campaign detail | `/campaign/000cb156-e4b5-4157-8904-b0a5cee0148d` | 1 | Campaign view |
| 9 | Fighter embed | `/list/83b0a055-4b01-45ef-a9c2-7fa548924681/fighter/4d3af0b2-4c3e-4bac-9b21-ca9854ce3fea/embed` | 1 | Embed card |

### Authenticated Pages (login as test1)

| # | View Name | URL | States | Notes |
|---|-----------|-----|--------|-------|
| 10 | Home (logged in) | `/` | 1 | Dashboard with lists |
| 11 | Account home | `/accounts/` | 1 | Account settings |
| 12 | List new | `/lists/new` | 1 | Create list form |
| 13 | List edit | `/list/83b0a055.../edit` | 1 | Edit form |
| 14 | List clone | `/list/83b0a055.../clone` | 1 | Clone confirm |
| 15 | List archive | `/list/83b0a055.../archive` | 1 | Archive confirm |
| 16 | List credits | `/list/83b0a055.../credits` | 1 | Credits edit |
| 17 | List packs | `/list/83b0a055.../packs` | 1 | Pack management |
| 18 | List invitations | `/list/83b0a055.../invitations` | 1 | Invitation list |
| 19 | List attributes manage | `/list/83b0a055.../attributes` | 1 | Attribute management |
| 20 | Fighter new | `/list/83b0a055.../fighters/new` | 1 | Add fighter form |
| 21 | Fighter edit | `/list/83b0a055.../fighter/4d3af0b2.../` | 1 | Edit fighter |
| 22 | Fighter weapons | `/list/83b0a055.../fighter/4d3af0b2.../weapons` | 1 | Weapons shop |
| 23 | Fighter gear | `/list/83b0a055.../fighter/4d3af0b2.../gear` | 1 | Gear shop |
| 24 | Fighter skills | `/list/83b0a055.../fighter/4d3af0b2.../skills` | 3 | Primary/Secondary, All, All+Restricted tabs |
| 25 | Fighter rules | `/list/83b0a055.../fighter/4d3af0b2.../rules` | 1 | Rules edit |
| 26 | Fighter XP | `/list/83b0a055.../fighter/4d3af0b2.../xp` | 1 | XP edit |
| 27 | Fighter stats | `/list/83b0a055.../fighter/4d3af0b2.../stats` | 1 | Stats override |
| 28 | Fighter injuries | `/list/83b0a055.../fighter/4d3af0b2.../injuries` | 1 | Injuries edit |
| 29 | Fighter narrative | `/list/83b0a055.../fighter/4d3af0b2.../narrative` | 1 | Lore edit |
| 30 | Fighter notes | `/list/83b0a055.../fighter/4d3af0b2.../notes` | 1 | Notes edit |
| 31 | Fighter advancements | `/list/83b0a055.../fighter/4d3af0b2.../advancements/` | 1 | Advancement list |
| 32 | Campaign new | `/campaigns/new/` | 1 | Create campaign |
| 33 | Campaign edit | `/campaign/000cb156.../edit/` | 1 | Edit campaign |
| 34 | Campaign add lists | `/campaign/000cb156.../lists/add` | 1 | Add gangs |
| 35 | Campaign packs | `/campaign/000cb156.../packs` | 1 | Pack management |
| 36 | Campaign assets | `/campaign/000cb156.../assets` | 1 | Asset management |
| 37 | Campaign resources | `/campaign/000cb156.../resources` | 1 | Resource management |
| 38 | Campaign attributes | `/campaign/000cb156.../attributes` | 1 | Attribute management |
| 39 | Campaign battles | `/campaign/000cb156.../battles` | 1 | Battle list |
| 40 | Campaign actions | `/campaign/000cb156.../actions` | 1 | Action log |
| 41 | Packs index | `/packs/` | 1 | Pack browser |
| 42 | Pack detail | `/pack/1478041d...` | 1 | Pack view |
| 43 | Pack edit | `/pack/1478041d.../edit/` | 1 | Edit pack |
| 44 | Pack lists | `/pack/1478041d.../lists/` | 1 | Subscribed lists |
| 45 | Pack activity | `/pack/1478041d.../activity/` | 1 | Activity log |
| 46 | Dice roller | `/dice/` | 1 | Dice tool |
| 47 | Design system | `/_debug/design-system/` | 1 | Existing design ref |
| 48 | Login page | `/accounts/login/` | 1 | Auth page |
| 49 | Signup page | `/accounts/signup/` | 1 | Auth page |

**Total views:** ~49 (with ~52 screenshot targets including skill tab states)
