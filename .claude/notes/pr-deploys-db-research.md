# PR Deploys: Database, Migrations & Content Library Research

## 1. Content Library Schema Overview

The content library is the game data layer. It defines the "rules" and reference data that user-created content depends on. The app is Necromunda (tabletop wargame) and all game data is stored in Django models under `gyrinx/content/models/`.

### Content Models (all inherit from `Content` -> `Base` which provides UUID PK + timestamps)

| Model | Description | Key FKs / M2Ms |
|-------|-------------|-----------------|
| `ContentHouse` | Factions (e.g., Goliath, Escher) | M2M: skill_categories |
| `ContentFighter` | Fighter archetypes per house | FK: house; M2M: skills, primary/secondary skill_categories, rules |
| `ContentFighterCategoryTerms` | Custom terminology per fighter type | - |
| `ContentFighterHouseOverride` | Per-house cost overrides for fighters | FK: fighter, house |
| `ContentEquipmentCategory` | Equipment categories | M2M: restricted_to (houses) |
| `ContentEquipmentCategoryFighterRestriction` | Category restrictions by fighter type | FK: equipment_category |
| `ContentEquipment` | Weapons, gear | FK: category; M2M: modifiers |
| `ContentEquipmentUpgrade` | Equipment upgrades (cyberteknika etc.) | FK: equipment; M2M: modifiers |
| `ContentEquipmentFighterProfile` | Links equipment to fighter types | FK: equipment, content_fighter |
| `ContentEquipmentEquipmentProfile` | Links equipment to other equipment | FK: equipment, linked_equipment |
| `ContentWeaponTrait` | Weapon traits (Rapid Fire, etc.) | - |
| `ContentWeaponProfile` | Weapon stat profiles | FK: equipment; M2M: traits |
| `ContentWeaponAccessory` | Weapon accessories | M2M: modifiers |
| `ContentFighterDefaultAssignment` | Default equipment on fighters | FK: fighter, equipment; M2M: weapon_profiles, weapon_accessories |
| `ContentFighterEquipmentListItem` | Equipment list items per fighter | FK: fighter, equipment, weapon_profile |
| `ContentFighterEquipmentListUpgrade` | Equipment list upgrades per fighter | FK: fighter, upgrade |
| `ContentFighterEquipmentListWeaponAccessory` | Equipment list accessories per fighter | FK: fighter, weapon_accessory |
| `ContentSkillCategory` | Skill trees | - |
| `ContentSkill` | Skills | FK: category |
| `ContentAttribute` | Gang attributes (Alignment etc.) | M2M: restricted_to (houses) |
| `ContentAttributeValue` | Attribute values | FK: attribute |
| `ContentRule` | Game rules | - |
| `ContentBook` | Rulebooks | - |
| `ContentPolicy` | Equipment policies | - |
| `ContentPageRef` | Page references to books | FK: book |
| `ContentPsykerDiscipline` | Psyker disciplines | - |
| `ContentPsykerPower` | Psyker powers | FK: discipline |
| `ContentFighterPsykerDisciplineAssignment` | Fighter-discipline links | FK: fighter, discipline |
| `ContentFighterPsykerPowerDefaultAssignment` | Default power assignments | FK: fighter, power |
| `ContentMod` (polymorphic base) | Modifiers base class | - |
| `ContentModStat` | Weapon stat mods | FK: ContentMod |
| `ContentModFighterStat` | Fighter stat mods | FK: ContentMod |
| `ContentModTrait` | Weapon trait mods | FK: ContentMod |
| `ContentModFighterRule` | Fighter rule mods | FK: ContentMod |
| `ContentModFighterSkill` | Fighter skill mods | FK: ContentMod |
| `ContentModSkillTreeAccess` | Skill tree access mods | FK: ContentMod |
| `ContentModPsykerDisciplineAccess` | Psyker discipline access mods | FK: ContentMod |
| `ContentInjuryGroup` | Injury groups | M2M: restricted_to_houses |
| `ContentInjury` | Individual injuries | FK: group |
| `ContentInjuryDefaultOutcome` | Enum for injury outcomes | - |
| `ContentEquipmentListExpansion` | Equipment list expansions | M2M: rules |
| `ContentEquipmentListExpansionItem` | Expansion items | FK: expansion, equipment, weapon_profile |
| `ContentEquipmentListExpansionRule` (polymorphic) | Base rule class | - |
| `ContentEquipmentListExpansionRuleByAttribute` | Attribute-based rules | FK: attribute; M2M: attribute_values |
| `ContentEquipmentListExpansionRuleByHouse` | House-based rules | FK: house |
| `ContentEquipmentListExpansionRuleByFighterCategory` | Category-based rules | - |
| `ContentStat` | Stat definitions | - |
| `ContentStatlineType` | Statline types (Fighter, Vehicle) | - |
| `ContentStatlineTypeStat` | Links stats to statline types | FK: statline_type, stat |
| `ContentStatline` | Actual stat values for a fighter | FK: fighter, statline_type |
| `ContentStatlineStat` | Individual stat values | FK: statline, statline_type_stat |
| `ContentAdvancementAssignment` | Equipment for advancements | FK: advancement, equipment; M2M: upgrades |
| `ContentAdvancementEquipment` | Equipment-based advancements | M2M: restricted_to_houses |
| `ContentAvailabilityPreset` | Availability defaults | FK: fighter, house |
| `ContentFighterEquipmentCategoryLimit` | Per-fighter category limits | FK: fighter, equipment_category |

**Total: ~45+ content model tables (not counting Historical* tables from simple-history)**

Every content model with `history = HistoricalRecords()` also generates a `Historical*` table. This roughly doubles the content table count to ~90 tables.

### Content Data Volume

The YAML data files in `content/necromunda-2018/data/` total ~7,285 lines across:
- ~21 houses
- ~25 fighter files (per-house)
- Equipment, skills, injuries, categories

This is **reference data only** -- the actual production database will have more content managed via the Django admin. The YAML is the "source of truth" for initial data population, but content is actively managed and extended through the admin interface.

### M2M Tables

Many M2M relationships exist (skills, rules, traits, modifiers, weapon_profiles, etc.). These create additional junction tables that must be included in any content export.

## 2. Core (User Data) Models

The core app stores user-created data. Key models:

| Model | Description | Content FKs |
|-------|-------------|-------------|
| `List` | User's gang/list | FK: content_house |
| `ListFighter` | Fighter in a list | FK: content_fighter, legacy_content_fighter |
| `ListFighterEquipmentAssignment` | Equipment on fighters | FK: content_equipment; M2M: weapon_profiles, weapon_accessories, upgrades |
| `ListFighterPsykerPowerAssignment` | Psyker powers | FK: content power |
| `ListFighterInjury` | Injuries on fighters | FK: content injury |
| `ListFighterAdvancement` | Advancements | FK: advancement equipment |
| `ListFighterStatOverride` | Stat overrides | - |
| `ListAttributeAssignment` | Gang attributes | FK: attribute_value |
| `Campaign` | Campaign tracking | - |
| `ListAction` | Action log | - |
| `Event` | Analytics events | - |

**Critical: Core models have ForeignKey references to Content models.** This means the content data MUST exist before user data can reference it. For PR deploys, the content tables need to be populated.

## 3. Migration Structure

### Content Migrations
- **Start:** `0001_squashed_0116_add_visible_only_if_in_equipment_list.py` (squashed from 116 migrations)
- **Latest:** `0153_add_availability_preset.py`
- **Post-squash migrations:** 0117 through 0153 (37 individual migrations)

### Core Migrations
- **Start:** `0001_squashed_0080_alter_historicallistfighter_private_notes_and_more.py`
- **Latest:** `0125_allow_negative_rating_for_equipment.py`
- **Post-squash migrations:** 0081 through 0125 (45 individual migrations)

### Other Apps
- `pages`: 6 migrations (simple, no cross-app deps)
- `api`: 4 migrations (simple)
- `analytics`: No migrations (uses admin views only)

### Cross-App Migration Dependencies

**Core depends on Content (7 migrations):**
- `0001_squashed` (references content models)
- `0083_add_listfighterstatoverride`
- `0088_add_rule_overrides_to_listfighter`
- `0100_add_disabled_skills_to_listfighter`
- `0102_listfighter_idx_listfighter_list_active`
- `0104_historicallistfighteradvancement_equipment_assignment_and_more`
- `0121_add_dirty_propagation_indexes`

**Content depends on Core (3 migrations - data-only):**
- `0118_merge_armoured_undersuit`
- `0137_remove_deprecated_house_additional_rules`
- `0144_fix_smart_quotes_in_stats`

These are data migrations that reference core models. The schema dependencies flow primarily **content -> core** (content is the foundation).

## 4. How Migrations Run in Production

The `docker/entrypoint.sh` runs on every container start:

```bash
manage collectstatic --noinput
manage migrate
manage ensuresuperuser --no-input
daphne -b 0.0.0.0 -p $PORT "gyrinx.asgi:application"
```

**Key insight:** Migrations run automatically on each deploy. This is standard Cloud Run behavior where the container starts fresh each time.

## 5. Database Configuration

**Production:**
- PostgreSQL on Cloud SQL (GCP europe-west2)
- Configured via `DB_CONFIG` env var (JSON with user/password)
- `DB_NAME`, `DB_HOST`, `DB_PORT` env vars
- Cloud SQL connection likely via Cloud SQL Auth Proxy or direct private IP

**Development:**
- PostgreSQL 16.4 via Docker Compose on localhost:5432
- Default credentials: postgres/postgres

## 6. Content Data Import/Export Approaches

### Existing Mechanisms

1. **`loaddata_overwrite` management command** (`gyrinx/core/management/commands/loaddata_overwrite.py`):
   - Loads JSON fixture files
   - Truncates existing tables before loading (with FK checks disabled)
   - Skips historical model records
   - Uses Django's `loaddata` under the hood
   - Disables FK checks via `SET session_replication_role = 'replica'`

2. **YAML data files** (`content/necromunda-2018/data/`):
   - Source of truth for initial content data
   - Has a utilities module (`gyrinx/content/management/utils.py`) for loading YAML with schema validation
   - Uses `stable_uuid()` (MD5-based deterministic UUIDs) for content IDs

3. **Django `dumpdata` / `loaddata`**:
   - Standard Django fixture tooling
   - Could export content tables to JSON

4. **Test fixtures** (`gyrinx/content/tests/fixtures/`):
   - YAML test data files (minimal content for testing)
   - Used by test suite

### PR Environment Strategy Options

**Option A: pg_dump/pg_restore of content tables**
- Pros: Fast, exact copy, handles all FK relationships correctly
- Cons: Need to identify all content tables (including M2M junction tables and Historical tables)
- Implementation: `pg_dump --table=content_* --table=django_content_type` from production DB

**Option B: Django `dumpdata` for content app**
- Command: `manage dumpdata content --natural-foreign --natural-primary -o content.json`
- Pros: Portable, handles natural keys
- Cons: Slower than pg_dump, may have issues with UUID PKs and M2M tables

**Option C: Clone entire production database**
- Pros: Simplest, guaranteed consistency
- Cons: Includes user data (privacy concern), large database size, slow

**Option D: Create empty DB + migrate + load content from fixtures**
- Pros: Clean, no user data
- Cons: Content in fixtures may be stale vs production

**Recommended approach for PR deploys: Option A (pg_dump of content schema + tables)**
- Export content tables from production (or a regularly-refreshed snapshot)
- Create PR database, run migrations, import content tables
- This gives a functional app with all game data but no user data

## 7. PR Database Lifecycle Strategy

### Creation Flow
1. **PR opened/updated** -> Cloud Build trigger
2. **Create Cloud SQL database** (or use a database per PR pattern)
   - `CREATE DATABASE pr_<pr_number>` on the existing Cloud SQL instance
   - Or use a separate, smaller Cloud SQL instance for PR databases
3. **Run migrations** against the PR database
4. **Import content data** from a pre-built snapshot
5. **Create superuser** (`ensuresuperuser`)
6. **Deploy Cloud Run service** pointing to PR database

### Content Sync Options
- **Snapshot approach**: Maintain a regularly-updated content dump (e.g., nightly from prod)
- **On-demand**: Export content from prod when PR environment is created
- **Embedded in image**: Include content fixture in Docker image for fast setup

### Database Naming Convention
- `gyrinx_pr_<pr_number>` (e.g., `gyrinx_pr_42`)

### Cleanup Flow
1. **PR closed/merged** -> Trigger cleanup
2. **Drop database**: `DROP DATABASE gyrinx_pr_<pr_number>`
3. **Delete Cloud Run service** for the PR

## 8. Risks and Considerations

### Migration Conflicts Between PRs
- Two PRs might create conflicting migrations (e.g., both add `0154_*.py` to content)
- **Mitigation**: PR environments only need their own branch migrations; conflicts are resolved on merge
- Each PR database runs its own branch's migrations independently

### Content Data Freshness
- If content is actively managed through admin, PR environments may have stale content
- **Mitigation**: Use a recent snapshot or on-demand export from production

### Database Cost
- Cloud SQL instances are expensive; using a single shared instance with multiple databases is more cost-effective
- Consider using AlloyDB or a lighter-weight option for PR databases

### Schema Divergence
- A long-running PR with schema changes may diverge significantly from main
- **Mitigation**: PR databases are ephemeral; recreate if needed

### Historical Tables (django-simple-history)
- Every content model has a corresponding Historical* table
- These are NOT needed for PR environments (they track admin change history)
- Can skip Historical tables in the content export to reduce data size

### Polymorphic Models
- `ContentMod` and `ContentEquipmentListExpansionRule` use django-polymorphic
- These have a base table + child tables with content_type FKs
- The `django_content_type` table must be consistent between environments
- **Critical**: When importing content data, ensure `django_content_type` IDs match

### UUID Primary Keys
- All content models use UUID PKs (from `Base`)
- UUIDs are deterministic for YAML-sourced content (via `stable_uuid()`)
- Admin-created content gets random UUIDs
- **Important**: When cloning content, UUIDs must be preserved exactly

## 9. Database Tables Inventory

### Content App Tables (approximate, from models)
- ~45 content model tables
- ~40 Historical* tables (from simple_history)
- ~15-20 M2M junction tables
- Total: ~100 tables in the content app

### Core App Tables
- ~15 core model tables
- ~15 Historical* tables
- ~10 M2M junction tables
- Total: ~40 tables in the core app

### System Tables
- `django_content_type` (critical for polymorphic models)
- `django_migrations`
- `django_site`
- `auth_*` tables
- `account_*` tables (allauth)
- `django_session`

### For PR Deploys, We Need
1. All content tables (including M2M junctions)
2. `django_content_type` (must match)
3. `django_site` (for allauth)
4. `auth_user` (at least one superuser)
5. We do NOT need: core tables (user data), Historical* tables, session tables

## 10. Summary of Key Findings

1. **Content is foundational**: The app cannot function without content data. All core models FK to content models.
2. **Migrations run automatically** in the entrypoint.sh on container start.
3. **Cross-app dependencies exist** between content and core migrations (content is the foundation).
4. **`loaddata_overwrite`** command exists and handles content import with FK constraint disabling.
5. **Content data is ~7K lines of YAML** but production likely has more data managed via admin.
6. **Historical tables can be skipped** for PR environments (they're change audit logs).
7. **Polymorphic models** (ContentMod, expansion rules) need `django_content_type` consistency.
8. **UUIDs as PKs** mean content can be deterministically imported without conflicts.
9. **Database cost** is the main concern -- use shared Cloud SQL instance with separate databases per PR.
10. **The recommended approach** is: create DB -> migrate -> import content snapshot -> deploy.
