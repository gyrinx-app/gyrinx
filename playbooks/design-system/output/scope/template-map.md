# Template Map

## Summary

- **Total templates:** 314 `.html` files
- **SCSS files:** 3 (`styles.scss`, `screen.scss`, `print.scss`)
- **JS files:** 1 (`index.js`)
- **SCSS build command:** `npm run css` (sass + autoprefixer)

## Layout Chain

```
core/layouts/foundation.html          ← HTML shell, meta, CSS/JS
  └─ core/layouts/base.html           ← Navbar, content container, footer
      ├─ core/layouts/page.html       ← Simple titled-page wrapper
      └─ allauth/layouts/base.html    ← Auth pages bridge
  └─ core/layouts/base_print.html     ← Print/embed (no chrome)
```

## URL → View → Template Map

### Home / Account

| URL | Name | Template |
|-----|------|----------|
| `/` | `core:index` | `core/index.html` |
| `/accounts/` | `core:account_home` | `core/account_home.html` |
| `/user/<slug>` | `core:user` | `core/user.html` |
| `/dice/` | `core:dice` | `core/dice.html` |
| `/_debug/design-system/` | `debug_design_system` | `core/debug/design_system.html` |

### Lists

| URL | Name | Template |
|-----|------|----------|
| `/lists/` | `core:lists` | `core/lists.html` |
| `/lists/new` | `core:lists-new` | `core/list_new.html` |
| `/list/<id>` | `core:list` | `core/list.html` |
| `/list/<id>/edit` | `core:list-edit` | `core/list_edit.html` |
| `/list/<id>/about` | `core:list-about` | `core/list_about.html` |
| `/list/<id>/notes` | `core:list-notes` | `core/list_notes.html` |
| `/list/<id>/print` | `core:list-print` | `core/list_print.html` |
| `/list/<id>/clone` | `core:list-clone` | `core/list_clone.html` |
| `/list/<id>/archive` | `core:list-archive` | `core/list_archive.html` |
| `/list/<id>/credits` | `core:list-credits-edit` | `core/list_credits_edit.html` |
| `/list/<id>/packs` | `core:list-packs` | `core/list_packs.html` |
| `/list/<id>/invitations` | `core:list-invitations` | `core/list/list_invitations.html` |
| `/list/<id>/attribute/<attr_id>/edit` | `core:list-attribute-edit` | `core/list_attribute_edit.html` |
| `/list/<id>/attributes` | `core:list-attributes-manage` | `core/list_attributes_manage.html` |

### Fighters

| URL | Name | Template |
|-----|------|----------|
| `/list/<id>/fighters/new` | `core:list-fighter-new` | `core/list_fighter_new.html` |
| `/list/<id>/fighter/<fid>` | `core:list-fighter-edit` | `core/list_fighter_edit.html` |
| `/list/<id>/fighter/<fid>/weapons` | `core:list-fighter-weapons-edit` | `core/list_fighter_weapons_edit.html` |
| `/list/<id>/fighter/<fid>/gear` | `core:list-fighter-gear-edit` | `core/list_fighter_gear_edit.html` |
| `/list/<id>/fighter/<fid>/skills` | `core:list-fighter-skills-edit` | `core/list_fighter_skills_edit.html` |
| `/list/<id>/fighter/<fid>/rules` | `core:list-fighter-rules-edit` | `core/list_fighter_rules_edit.html` |
| `/list/<id>/fighter/<fid>/xp` | `core:list-fighter-xp-edit` | `core/list_fighter_xp_edit.html` |
| `/list/<id>/fighter/<fid>/stats` | `core:list-fighter-stats-edit` | `core/list_fighter_stats_edit.html` |
| `/list/<id>/fighter/<fid>/injuries` | `core:list-fighter-injuries-edit` | `core/list_fighter_injuries_edit.html` |
| `/list/<id>/fighter/<fid>/narrative` | `core:list-fighter-narrative-edit` | `core/list_fighter_narrative_edit.html` |
| `/list/<id>/fighter/<fid>/notes` | `core:list-fighter-notes-edit` | `core/list_fighter_notes_edit.html` |
| `/list/<id>/fighter/<fid>/advancements/` | `core:list-fighter-advancements` | `core/list_fighter_advancements.html` |
| `/list/<id>/fighter/<fid>/embed` | `core:list-fighter-embed` | `core/list_fighter_embed.html` |

### Campaigns

| URL | Name | Template |
|-----|------|----------|
| `/campaigns/` | `core:campaigns` | `core/campaign/campaigns.html` |
| `/campaigns/new/` | `core:campaigns-new` | `core/campaign/campaign_new.html` |
| `/campaign/<id>` | `core:campaign` | `core/campaign/campaign.html` |
| `/campaign/<id>/edit/` | `core:campaign-edit` | `core/campaign/campaign_edit.html` |
| `/campaign/<id>/lists/add` | `core:campaign-add-lists` | `core/campaign/campaign_add_lists.html` |
| `/campaign/<id>/packs` | `core:campaign-packs` | `core/campaign/campaign_packs.html` |
| `/campaign/<id>/assets` | `core:campaign-assets` | `core/campaign/campaign_assets.html` |
| `/campaign/<id>/resources` | `core:campaign-resources` | `core/campaign/campaign_resources.html` |
| `/campaign/<id>/attributes` | `core:campaign-attributes` | `core/campaign/campaign_attributes.html` |
| `/campaign/<id>/battles` | `core:campaign-battles` | `core/campaign/campaign_battles.html` |
| `/campaign/<id>/actions` | `core:campaign-actions` | `core/campaign/campaign_actions.html` |
| `/battle/<id>` | `core:battle` | `core/battle/battle.html` |

### Content Packs

| URL | Name | Template |
|-----|------|----------|
| `/packs/` | `core:packs` | `core/pack/packs.html` |
| `/packs/new/` | `core:packs-new` | `core/pack/pack_new.html` |
| `/pack/<id>` | `core:pack` | `core/pack/pack.html` |
| `/pack/<id>/edit/` | `core:pack-edit` | `core/pack/pack_edit.html` |
| `/pack/<id>/lists/` | `core:pack-lists` | `core/pack/pack_lists.html` |
| `/pack/<id>/activity/` | `core:pack-activity` | `core/pack/pack_activity.html` |

## High-Frequency Include Templates

| Template | Included By (approx) |
|----------|---------------------|
| `core/includes/back.html` | ~50 pages |
| `core/includes/form_field.html` | ~25 pages |
| `core/includes/cancel.html` | ~15 pages |
| `core/includes/pagination.html` | ~10 pages |
| `core/includes/list_common_header.html` | ~10 pages |
| `core/includes/fighter_card.html` | ~8 pages |
| `core/includes/gear_assign_name.html` | ~10 sites |
| `core/includes/weapon_stat_headers.html` | ~7 pages |

## Deepest Include Chain

```
list.html → includes/list.html → includes/fighter_card.html
  → fighter_card_content.html → fighter_card_content_inner.html
  → list_fighter_weapons.html → list_fighter_weapon_rows.html
  → list_fighter_weapon_assign_name.html (7 levels deep)
```
