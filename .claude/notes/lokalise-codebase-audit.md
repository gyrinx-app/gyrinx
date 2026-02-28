# Lokalise i18n Codebase Audit

## 1. Current i18n State

### Settings (`gyrinx/settings.py`)

| Setting | Current Value | Status |
|---------|---------------|--------|
| `LANGUAGE_CODE` | `"en-us"` | Set (default) |
| `USE_I18N` | `True` | Enabled |
| `USE_TZ` | `True` | Enabled |
| `LOCALE_PATHS` | **Not configured** | Needs adding |
| `LANGUAGES` | **Not configured** | Needs adding |
| `LocaleMiddleware` | **Not in MIDDLEWARE** | Needs adding |

### Existing i18n Usage

- **No project-level `.po`/`.mo` files** exist. Only third-party packages (allauth, polymorphic) have their own locale files.
- **39 templates** load `{% load i18n %}` - all are allauth/MFA/account template overrides, not app-specific templates.
- **42 templates** use `{% trans %}` tags - same allauth/MFA/account subset.
- **0 core app templates** (lists, campaigns, fighters, etc.) use any i18n template tags.
- **4 Python files** import gettext/gettext_lazy:
  - `gyrinx/core/forms/__init__.py` - `gettext_lazy` for 3 strings in `BsClearableFileInput`
  - `gyrinx/content/actions.py` - `gettext` (admin actions)
  - `gyrinx/content/admin.py` - `gettext` (admin interface)
  - `gyrinx/core/admin/auth.py` - `gettext` (admin interface)
  - `gyrinx/core/models/print_config.py` - `ngettext` for pluralization (3 usages)

**Summary: The app has USE_I18N=True but virtually no i18n infrastructure in place for the main application. Only allauth templates and a handful of Python files use translation functions.**

---

## 2. Template Strings Audit

### Template Count

| Directory | Count |
|-----------|-------|
| `core/templates/core/` (main pages) | 63 |
| `core/templates/core/includes/` (reusable components) | 43 |
| `core/templates/core/campaign/` | 36 |
| `core/templates/account/` (allauth overrides) | 26 |
| `core/templates/allauth/elements/` | 21 |
| `core/templates/core/campaign/includes/` | 7 |
| `core/templates/mfa/` (all MFA dirs) | 18 |
| Other (layouts, admin, widgets, debug, pages, etc.) | 45 |
| **Total** | **259** |

Of these, **~75 are allauth/MFA/account overrides** that already have some i18n. The remaining **~184 are app-specific templates** that need i18n work.

### String Patterns in Templates

Templates contain hardcoded English strings of these types:

1. **Page headings**: `<h1 class="h3">Edit {{ form.instance.name }}</h1>`, `<h1 class="h3">Archive</h1>`
2. **Button labels**: `Save`, `Cancel`, `Archive`, `Unarchive`, `Next`, `Add`, `Remove`
3. **Explanatory text**: "Are you sure you want to archive this gang/list?", "What happens when you archive:"
4. **List items and descriptions**: "The list will be hidden from your main lists page", "You won't be able to edit the list or its fighters"
5. **Warning/info messages**: "Warning: Active Campaign", "Note:"
6. **Form labels embedded in templates** (some forms render labels via Python, some in templates)
7. **Navigation text**: "Back to list", "Cancel"

**Estimated string count in templates: 800-1200 unique translatable strings** (headings, buttons, explanatory text, labels, error messages, list items).

### Sample Template Analysis

`list_archive.html` (typical page) contains ~20 hardcoded English strings:
- "Unarchive", "Archive" (headings, buttons)
- "Are you sure you want to archive this gang/list?"
- "What happens when you archive:", "What happens when you unarchive:"
- 6 list items explaining consequences
- "Warning: Active Campaign", "Note:"
- Dynamic sentences with pluralization

---

## 3. Content Library (Model Fields)

### Content Models - Translatable Name Fields

These `name` fields on content models store game terminology that would need translation:

| Model | Field | Description | Approx Record Count |
|-------|-------|-------------|---------------------|
| `ContentHouse` | `name` | Faction names (e.g., "Escher", "Goliath") | ~20 |
| `ContentFighter` | `type` | Fighter type names | ~200+ |
| `ContentEquipmentCategory` | `name` | Category names (e.g., "Pistols", "Basic Weapons") | ~15 |
| `ContentEquipment` | `name` | Equipment names | ~400+ |
| `ContentWeaponProfile` | `name` | Profile names (e.g., "Standard", "Concentrated") | ~600+ |
| `ContentWeaponTrait` | `name` | Trait names (e.g., "Rapid Fire", "Knockback") | ~50 |
| `ContentWeaponAccessory` | `name` | Accessory names | ~20 |
| `ContentEquipmentUpgrade` | `name` | Upgrade names | ~50 |
| `ContentSkillCategory` | `name` | Skill tree names | ~10 |
| `ContentSkill` | `name` | Skill names | ~80 |
| `ContentRule` | `name` | Rule names | ~100 |
| `ContentBook` | `name`, `shortname`, `description` | Rulebook metadata | ~10 |
| `ContentPageRef` | `title`, `description`, `category` | Page references | ~500+ |
| `ContentPsykerDiscipline` | `name` | Discipline names | ~10 |
| `ContentPsykerPower` | `name` | Power names | ~30 |
| `ContentInjuryGroup` | `name`, `description` | Injury group names | ~10 |
| `ContentInjury` | `name`, `description` | Injury names | ~40 |
| `ContentStat` | `short_name`, `full_name` | Stat names (e.g., "M"/"Movement") | ~20 |
| `ContentStatlineType` | `name` | Statline type names | ~3 |
| `ContentAttribute` | `name`, `description` | Attribute names | ~10 |
| `ContentAttributeValue` | `name`, `description` | Attribute value names | ~30 |
| `ContentEquipmentListExpansion` | `name` | Expansion names | ~10 |
| `ContentFighterCategoryTerms` | `singular`, `proximal_demonstrative`, `injury_singular`, `injury_plural`, `recovery_singular` | Custom terminology per fighter type | ~5 records, 5 fields each |

**Important note on content translation approach:** These are game content from Necromunda rulebooks. There are two distinct approaches:

1. **django-modeltranslation**: Add translated columns to DB tables (e.g., `name_en`, `name_fr`). Best for database-driven content that changes frequently.
2. **Extract to .po files**: Treat content names as static strings. Best if content rarely changes.

Given that content is managed via Django admin and changes periodically, **django-modeltranslation is likely the better fit** for content model fields.

**Estimated translatable content model fields: ~20 name fields across 20+ models, covering ~2000+ database records.**

### Content Models - Admin-Only Fields (Lower Priority)

These fields appear only in the Django admin and may not need translation initially:

- `help_text` on all model fields (~122 occurrences across content models)
- `verbose_name` / `verbose_name_plural` on Meta classes (~148 occurrences across content models)

---

## 4. Python Source Strings

### Flash Messages (views)

**171 total `messages.success/error/warning/info()` calls** across views. These are user-facing and all contain hardcoded English strings.

Key view files with flash messages:
- `gyrinx/core/views/fighter/equipment.py` - equipment operations
- `gyrinx/core/views/fighter/state.py` - fighter state changes
- `gyrinx/core/views/fighter/advancements.py` - advancement system
- `gyrinx/core/views/campaign/lists.py` - campaign list management
- `gyrinx/core/views/campaign/resources.py` - campaign resources
- `gyrinx/core/views/campaign/assets.py` - campaign assets
- `gyrinx/core/views/campaign/lifecycle.py` - campaign lifecycle
- `gyrinx/core/views/campaign/copy.py` - campaign copy operations
- `gyrinx/core/views/vehicle.py` - vehicle flow
- `gyrinx/core/views/fighter/crud.py` - fighter CRUD

### ValidationError Messages

**171 `raise ValidationError()` calls** across the codebase with hardcoded English error messages.

### Form Labels and Help Text

Form files contain extensive hardcoded labels and help text:
- `gyrinx/core/forms/list.py` - ~50 label/help_text strings
- `gyrinx/core/forms/campaign.py` - ~20+ strings
- `gyrinx/core/forms/battle.py` - ~10+ strings
- `gyrinx/core/forms/vehicle.py` - ~10+ strings
- `gyrinx/core/forms/advancement.py` - ~10+ strings
- `gyrinx/core/forms/__init__.py` - ~15+ strings (signup, login, username)

The forms use a **template_form_with_terms** system that dynamically replaces `{term_singular}`, `{term_injury_singular}`, etc. with fighter-specific terminology. This will need to interact with the i18n system.

### Model verbose_name and help_text

- **~230 occurrences** of `verbose_name` / `help_text` across core models (`gyrinx/core/models/`)
- **~148 occurrences** of `verbose_name` across content models
- **~122 occurrences** of `help_text` across content models
- These are used in admin and forms; wrapping them in `gettext_lazy()` is standard Django practice

### TextChoices Enums

7 TextChoices classes with English labels:
- `FighterCategoryChoices` - 18 choices (Leader, Champion, Ganger, etc.)
- `ListActionType` - action type labels
- `EventNoun`, `EventVerb`, `EventField` - event system labels
- `ContentInjuryDefaultOutcome` - 6 outcome labels
- `ContentEquipment.UpgradeMode` - 2 mode labels

### Email Templates

- **26 email `.txt` templates** in `account/email/` and `mfa/email/` (subjects and bodies)
- **13 message `.txt` templates** in `account/messages/` and `mfa/messages/`
- These are allauth overrides and would need translation

---

## 5. Frontend Strings

### JavaScript (`gyrinx/core/static/core/js/index.js`)

- **1 JavaScript file** (536 lines)
- **Minimal user-facing strings**:
  - One tooltip message: "Availability filters are disabled when Equipment List is toggled on..."
  - Console log/error messages (don't need translation)
- JavaScript i18n is a negligible concern for this codebase

### SCSS/CSS

- No translatable strings in stylesheets (as expected)

---

## 6. Scope Summary

### By Priority

| Category | Count | Effort |
|----------|-------|--------|
| **Template strings** (headings, buttons, text) | ~800-1200 strings across 184 templates | HIGH - biggest effort |
| **Flash messages** (views) | ~171 calls | MEDIUM |
| **Form labels/help text** | ~100+ strings across 8+ form files | MEDIUM |
| **ValidationError messages** | ~171 calls | MEDIUM |
| **Content model fields** (name, description) | ~20 fields across 20+ models, ~2000+ records | HIGH - needs django-modeltranslation or similar |
| **Model verbose_name/help_text** (admin-facing) | ~500+ occurrences | LOW - admin-only, can defer |
| **TextChoices labels** | ~40+ labels across 7 enums | LOW |
| **Email templates** | ~39 files | LOW - allauth provides translations |
| **JavaScript strings** | ~1 string | NEGLIGIBLE |

### Required Infrastructure Changes

1. Add `LOCALE_PATHS`, `LANGUAGES` settings
2. Add `django.middleware.locale.LocaleMiddleware` to MIDDLEWARE
3. Add `{% load i18n %}` to all 184+ app templates
4. Wrap all template strings with `{% trans %}` / `{% blocktrans %}`
5. Wrap all Python strings with `gettext()` / `gettext_lazy()`
6. Set up `.po` file generation and management
7. Decide on content model translation approach (django-modeltranslation vs .po files)
8. The `template_form_with_terms` system needs to be made i18n-aware

### Key Challenges

1. **Content data is game terminology** - fighter names, equipment names, etc. are from Necromunda rulebooks. Translation needs domain expertise.
2. **Dynamic string composition** - many flash messages use f-strings with dynamic content (fighter names, campaign names). These need `gettext()` with format placeholders.
3. **template_form_with_terms system** - forms use a custom string interpolation system for fighter-specific terminology that needs to work alongside i18n.
4. **Pluralization** - Django's `{% blocktrans %}` with `count` and Python's `ngettext` will be needed in several places.
5. **Content model translation** - a separate concern from UI translation, requiring either django-modeltranslation or a custom approach to translate ~2000+ database records.
