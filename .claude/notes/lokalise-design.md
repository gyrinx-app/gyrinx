# Lokalise Integration Design Document

## 1. Overview and Goals

Gyrinx is a Django server-rendered application for managing Necromunda tabletop wargame gangs, campaigns, and equipment. All UI is server-rendered HTML (not an SPA). The application currently has `USE_I18N=True` in settings but virtually no i18n infrastructure in place for the main application -- only allauth/MFA template overrides use translation tags.

**Goals:**

- Enable the Gyrinx application to be served in multiple languages
- Use Lokalise as the central translation management platform
- Translate both static UI strings (templates, Python source) and dynamic content (game data in the database), including all game terminology
- Adopt i18n incrementally without a big-bang rewrite
- Keep the build/deploy pipeline simple and reliable

**Target languages (based on existing user base):**

- English (source/default)
- French (`fr`)
- Polish (`pl`)
- Russian (`ru`)
- Japanese (`ja`)

All five languages are configured from day one in a single migration.

**Translation approach:**

- Community volunteers + Lokalise AI translation
- Full Lokalise sync for both static strings and database content (not deferred)
- Manual sync commands initially, automation added later

**Non-goals (for now):**

- Translating the Django admin interface beyond what Django provides out of the box
- Translating email templates (allauth provides its own translations)
- JavaScript i18n (only one user-facing string exists in JS)

---

## 2. Scope: What Gets Translated

### 2.1 Static Strings (Templates and Python Source)

| Category | Estimated Count | Priority |
|----------|----------------|----------|
| Template strings (headings, buttons, explanatory text) | ~800-1200 strings across ~184 templates | HIGH |
| Flash messages in views (`messages.success/error/warning/info`) | ~171 calls | MEDIUM |
| Form labels and help text | ~100+ strings across 8+ form files | MEDIUM |
| ValidationError messages | ~171 calls | MEDIUM |
| TextChoices enum labels | ~40 labels across 7 enums | LOW |
| Model `verbose_name` / `help_text` (admin-facing) | ~500+ occurrences | LOW (defer) |

### 2.2 Dynamic Content (Database -- Content Library)

The content library stores game data from Necromunda rulebooks. Key models with translatable fields:

| Model | Translatable Fields | Approx Records |
|-------|---------------------|----------------|
| `ContentHouse` | `name` | ~20 |
| `ContentFighter` | `type` | ~200+ |
| `ContentEquipment` | `name` | ~400+ |
| `ContentWeaponProfile` | `name` | ~600+ |
| `ContentWeaponTrait` | `name` | ~50 |
| `ContentSkill` | `name` | ~80 |
| `ContentRule` | `name` | ~100 |
| `ContentInjury` | `name`, `description` | ~40 |
| `ContentBook` | `name`, `shortname`, `description` | ~10 |
| `ContentPageRef` | `title`, `description`, `category` | ~500+ |
| `ContentStat` | `short_name`, `full_name` | ~20 |
| `ContentEquipmentCategory` | `name` | ~15 |
| `ContentSkillCategory` | `name` | ~10 |
| `ContentPsykerDiscipline` | `name` | ~10 |
| `ContentPsykerPower` | `name` | ~30 |
| `ContentInjuryGroup` | `name`, `description` | ~10 |
| Other content models | Various `name` fields | ~100+ |

**Total: ~20+ fields across ~20+ models, covering ~2000+ database records.**

### 2.3 Out of Scope (Initially)

- Admin-only fields (`help_text`, `verbose_name` on model Meta classes)
- Email templates (allauth handles its own i18n)
- JavaScript strings (1 tooltip -- negligible)
- `ContentMod` subclass fields (stat modifiers, not user-facing text)

---

## 3. Architecture: How Lokalise Integrates

```
                          +------------------+
                          |     Lokalise     |
                          |  (2 projects)    |
                          +--------+---------+
                                   |
                    +--------------+--------------+
                    |                             |
           Static Strings                 Dynamic Content
           (.po files)                    (API keys)
                    |                             |
           lokalise2 CLI                  python-lokalise-api
           push/pull .po                  or Django admin
                    |                             |
          +---------+----------+        +---------+----------+
          |  locale/<lang>/    |        | django-model-      |
          |  LC_MESSAGES/      |        | translation        |
          |  django.po/.mo     |        | (field_en, _fr,    |
          +--------------------+        |  _pl, _ru, _ja)    |
                    |                   +--------------------+
                    |                             |
          +---------+-----------------------------+----------+
          |              Django Application                  |
          |  {% trans %} / gettext()  |  model.field (auto)  |
          +--------------------------------------------------+
```

**Two Lokalise projects:**

1. **Static Strings Project** -- manages `.po` files from templates and Python source. Synced via the `lokalise2` CLI.
2. **Dynamic Content Project** -- manages database content keys. Synced via the `python-lokalise-api` SDK or managed directly in Django admin.

**Two Django libraries:**

1. **Django's built-in i18n** (`django.utils.translation`) -- for static strings in templates and Python code.
2. **django-modeltranslation** -- for database content fields. Adds language-specific columns (`name_en`, `name_fr`, etc.) to existing tables.

---

## 4. Static Strings Strategy

### 4.1 Django i18n Setup

Add to `gyrinx/settings.py`:

```python
from django.utils.translation import gettext_lazy as _

# Languages to support -- all configured from day one
LANGUAGES = [
    ("en", _("English")),
    ("fr", _("French")),
    ("pl", _("Polish")),
    ("ru", _("Russian")),
    ("ja", _("Japanese")),
]

LANGUAGE_CODE = "en"  # Default language (change from "en-us")

# Where Django looks for .po files
LOCALE_PATHS = [
    BASE_DIR / "locale",
]
```

Add `LocaleMiddleware` to `MIDDLEWARE` (must be after `SessionMiddleware` and before `CommonMiddleware`):

```python
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",  # NEW
    "django.middleware.common.CommonMiddleware",
    # ... rest of middleware
]
```

### 4.2 URL Routing with i18n_patterns

URLs use language prefixes for non-English languages. English URLs remain unprefixed (no breaking changes for existing users).

Update the root `urls.py`:

```python
from django.conf.urls.i18n import i18n_patterns

urlpatterns = [
    # Non-i18n URLs (API endpoints, webhooks, etc.)
    path("api/", include("gyrinx.api.urls")),
    # ...
]

urlpatterns += i18n_patterns(
    # All user-facing URLs get language prefixes
    path("", include("gyrinx.core.urls")),
    path("admin/", admin.site.urls),
    # ... other app URLs
    prefix_default_language=False,  # English stays at /lists/, not /en/lists/
)
```

Result:
- `/lists/` -- English (unchanged, no prefix)
- `/fr/lists/` -- French
- `/pl/lists/` -- Polish
- `/ru/lists/` -- Russian
- `/ja/lists/` -- Japanese

Django's `LocaleMiddleware` detects language from: URL prefix > cookie > `Accept-Language` header > `LANGUAGE_CODE` setting.

### 4.3 Language Selector

A language selector link in the page footer allows users to switch languages. Django provides a built-in `set_language` view for this:

```python
# In urls.py (non-i18n section)
urlpatterns = [
    path("i18n/", include("django.conf.urls.i18n")),
    # ...
]
```

```html
<!-- In footer template -->
<form action="{% url 'set_language' %}" method="post">
    {% csrf_token %}
    <input name="next" type="hidden" value="{{ redirect_to }}">
    <select name="language" onchange="this.form.submit()">
        {% get_current_language as LANGUAGE_CODE %}
        {% get_available_languages as LANGUAGES %}
        {% for lang_code, lang_name in LANGUAGES %}
            <option value="{{ lang_code }}"{% if lang_code == LANGUAGE_CODE %} selected{% endif %}>
                {{ lang_name }}
            </option>
        {% endfor %}
    </select>
</form>
```

### 4.4 Marking Strings for Translation

**Templates** -- add `{% load i18n %}` and wrap strings:

```html
{% load i18n %}

{# Simple strings #}
<h1 class="h3">{% trans "Archive" %}</h1>
<button class="btn btn-primary btn-sm">{% trans "Save" %}</button>

{# Strings with variables #}
{% blocktrans with name=fighter.name %}
  Are you sure you want to archive {{ name }}?
{% endblocktrans %}

{# Pluralization #}
{% blocktrans count num=fighters|length %}
  {{ num }} fighter will be affected.
{% plural %}
  {{ num }} fighters will be affected.
{% endblocktrans %}
```

**Python code** -- wrap with `gettext()` or `gettext_lazy()`:

```python
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _lazy

# In views (runtime strings):
messages.success(request, _("Fighter archived successfully."))

# In models/forms (lazy evaluation):
class MyForm(forms.Form):
    name = forms.CharField(label=_lazy("Name"), help_text=_lazy("Enter the gang name"))

# With variables (use named placeholders, not f-strings):
messages.success(request, _("%(name)s has been archived.") % {"name": fighter.name})

# Pluralization:
from django.utils.translation import ngettext
msg = ngettext(
    "%(count)d fighter was updated.",
    "%(count)d fighters were updated.",
    count,
) % {"count": count}
```

**TextChoices enums:**

```python
from django.utils.translation import gettext_lazy as _

class FighterCategoryChoices(models.TextChoices):
    LEADER = "leader", _("Leader")
    CHAMPION = "champion", _("Champion")
    GANGER = "ganger", _("Ganger")
    # ...
```

### 4.5 Extracting and Managing .po Files

```bash
# Create locale directory
mkdir -p locale/en/LC_MESSAGES

# Extract all translatable strings
manage makemessages -l en --no-obsolete

# After translations are added, compile to .mo
manage compilemessages
```

The resulting file structure:

```
locale/
  en/
    LC_MESSAGES/
      django.po    # Committed to git
      django.mo    # NOT committed (build artifact)
  fr/
    LC_MESSAGES/
      django.po    # Committed to git
      django.mo    # NOT committed
```

Add to `.gitignore`:

```
*.mo
```

### 4.6 Syncing with Lokalise

**Upload source strings (after `makemessages`):**

```bash
lokalise2 --token $LOKALISE_API_TOKEN \
  --project-id $LOKALISE_STATIC_PROJECT_ID \
  file upload \
  --file "locale/en/LC_MESSAGES/django.po" \
  --lang-iso en \
  --replace-modified \
  --distinguish-by-file
```

**Download translations (after translators finish):**

```bash
lokalise2 --token $LOKALISE_API_TOKEN \
  --project-id $LOKALISE_STATIC_PROJECT_ID \
  file download \
  --format po \
  --original-filenames=true \
  --directory-prefix "" \
  --unzip-to "./locale/"
```

### 4.7 The `template_form_with_terms` Challenge

The codebase uses a custom string interpolation system for fighter-specific terminology (e.g., `{term_singular}`, `{term_injury_singular}`). This system replaces placeholders in form labels and help text with terms that vary by fighter category.

**Strategy:** Wrap the template strings with `gettext_lazy()` first, then apply the term substitution. The `.po` file will contain strings like `"Add a new {term_singular}"` -- translators translate around the placeholders. This is a standard pattern in Django i18n (named format strings in translations).

```python
# Current:
label = "Add a new {term_singular}"

# After i18n:
label = _lazy("Add a new {term_singular}")
# Translators see: "Add a new {term_singular}" and translate to e.g.
# "Ajouter un nouveau {term_singular}" (French)
```

---

## 5. Dynamic Content Strategy (Content Library)

### 5.1 django-modeltranslation Setup

Install the package:

```bash
pip install django-modeltranslation
```

Add to `INSTALLED_APPS` in `settings.py` (**must be before `django.contrib.admin`**):

```python
INSTALLED_APPS = [
    "modeltranslation",  # NEW - must be before admin
    "django.contrib.admin",
    # ... rest of apps
]
```

### 5.2 Register Models for Translation

Create `gyrinx/content/translation.py`:

```python
from modeltranslation.translator import register, TranslationOptions
from .models import (
    ContentBook,
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentHouse,
    ContentInjury,
    ContentInjuryGroup,
    ContentPageRef,
    ContentPsykerDiscipline,
    ContentPsykerPower,
    ContentRule,
    ContentSkill,
    ContentSkillCategory,
    ContentStat,
    ContentWeaponProfile,
    ContentWeaponTrait,
)


@register(ContentHouse)
class ContentHouseTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentFighter)
class ContentFighterTranslationOptions(TranslationOptions):
    fields = ("type",)


@register(ContentEquipment)
class ContentEquipmentTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentEquipmentCategory)
class ContentEquipmentCategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentWeaponProfile)
class ContentWeaponProfileTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentWeaponTrait)
class ContentWeaponTraitTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentSkillCategory)
class ContentSkillCategoryTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentSkill)
class ContentSkillTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentRule)
class ContentRuleTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentBook)
class ContentBookTranslationOptions(TranslationOptions):
    fields = ("name", "shortname", "description")


@register(ContentPageRef)
class ContentPageRefTranslationOptions(TranslationOptions):
    fields = ("title", "description", "category")


@register(ContentStat)
class ContentStatTranslationOptions(TranslationOptions):
    fields = ("short_name", "full_name")


@register(ContentPsykerDiscipline)
class ContentPsykerDisciplineTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentPsykerPower)
class ContentPsykerPowerTranslationOptions(TranslationOptions):
    fields = ("name",)


@register(ContentInjuryGroup)
class ContentInjuryGroupTranslationOptions(TranslationOptions):
    fields = ("name", "description")


@register(ContentInjury)
class ContentInjuryTranslationOptions(TranslationOptions):
    fields = ("name", "description")
```

### 5.3 Generate and Apply Migrations

```bash
manage makemigrations content -n "add_translation_fields"
manage migrate
manage update_translation_fields  # Copies existing values to _en columns
```

This adds columns like `name_en`, `name_fr`, `type_en`, `type_fr`, etc. to the content tables. The original `name` field becomes a proxy that returns the value for the active language.

### 5.4 How It Works at Runtime

django-modeltranslation is transparent. Existing code continues to work:

```python
# This already works -- returns name in the active language
fighter = ContentFighter.objects.get(pk=some_id)
print(fighter.type)  # Returns type_en, type_fr, etc. based on active language

# Templates work unchanged:
{{ fighter.type }}  # Renders the translated value automatically
```

No template changes are needed for content library fields. The translation is handled at the model layer.

### 5.5 Admin Integration

Update `gyrinx/content/admin.py` to use translation-aware admin classes:

```python
from modeltranslation.admin import TranslationAdmin, TabbedTranslationAdmin

# Change base classes from admin.ModelAdmin to TabbedTranslationAdmin
# for models registered in translation.py

class ContentFighterAdmin(TabbedTranslationAdmin):
    # existing configuration stays the same
    list_display = [...]
    # ...

class ContentEquipmentAdmin(TabbedTranslationAdmin):
    list_display = [...]
    # ...
```

`TabbedTranslationAdmin` adds language tabs to the admin form, so content managers can enter translations per language in a clean tabbed interface.

### 5.6 Syncing Database Content with Lokalise

Both Django admin and Lokalise API sync are available from Phase 1. Content managers can enter translations directly via the tabbed admin interface, while community volunteers translate via Lokalise's web UI.

Key naming convention for Lokalise: `<model>.<uuid>.<field>`

```
contentfighter.a1b2c3d4.type
contentequipment.e5f6g7h8.name
contentweaponprofile.i9j0k1l2.name
```

Example management command:

```python
# gyrinx/content/management/commands/sync_translations_to_lokalise.py
import lokalise
from django.conf import settings
from django.core.management.base import BaseCommand

from gyrinx.content.models import ContentFighter, ContentEquipment


class Command(BaseCommand):
    help = "Push content library strings to Lokalise for translation"

    def handle(self, *args, **options):
        client = lokalise.Client(settings.LOKALISE_API_TOKEN)
        project_id = settings.LOKALISE_CONTENT_PROJECT_ID

        keys = []
        for fighter in ContentFighter.objects.all():
            keys.append({
                "key_name": f"contentfighter.{fighter.pk}.type",
                "platforms": ["web"],
                "tags": ["content-library", "fighter"],
                "translations": [
                    {"language_iso": "en", "translation": fighter.type_en or ""}
                ],
            })

        for equipment in ContentEquipment.objects.all():
            keys.append({
                "key_name": f"contentequipment.{equipment.pk}.name",
                "platforms": ["web"],
                "tags": ["content-library", "equipment"],
                "translations": [
                    {"language_iso": "en", "translation": equipment.name_en or ""}
                ],
            })

        # Batch create/update (API accepts up to 500 keys per request)
        batch_size = 500
        for i in range(0, len(keys), batch_size):
            batch = keys[i : i + batch_size]
            client.create_keys(project_id, batch)
            self.stdout.write(f"Pushed {len(batch)} keys")
```

---

## 6. Lokalise Project Setup

### 6.1 Project Structure

Create two Lokalise projects:

| Project | Purpose | Format | Sync Method |
|---------|---------|--------|-------------|
| **Gyrinx Static Strings** | Template/Python UI strings | Gettext PO | `lokalise2` CLI (push/pull .po files) |
| **Gyrinx Content Library** | Database content (fighters, equipment, etc.) | Keys (API) | `python-lokalise-api` SDK or Django admin only |

### 6.2 Key Naming Conventions

**Static strings project:** Uses Django's default `msgid` as the key (the English source string). This is standard for `.po` file imports.

**Dynamic content project:** Uses structured keys:

```
contentfighter.<uuid>.type
contentequipment.<uuid>.name
contentweaponprofile.<uuid>.name
contentskill.<uuid>.name
contentbook.<uuid>.name
contentbook.<uuid>.description
```

### 6.3 Tags

Organize keys with tags for translator context:

- `ui` -- buttons, labels, headings
- `content-library` -- database content
- `fighter` -- fighter-related content
- `equipment` -- equipment-related content
- `campaign` -- campaign UI strings
- `list` -- list/gang UI strings

### 6.4 Languages

All five languages are configured from day one:

| Code | Language | Notes |
|------|----------|-------|
| `en` | English | Source language |
| `fr` | French | |
| `pl` | Polish | |
| `ru` | Russian | |
| `ja` | Japanese | No pluralization in Japanese; Django handles this gracefully |

Adding a new language later requires:
1. Adding to `settings.LANGUAGES`
2. Running `makemigrations` (for django-modeltranslation columns)
3. Running `makemessages -l <code>` (for .po files)
4. Adding the language in both Lokalise projects

### 6.5 Key Quotas

Lokalise key quotas are at the team level across all projects. Estimated key counts:
- Static strings: ~1,500-2,000 keys
- Dynamic content: ~2,000-3,000 keys
- Total: ~3,500-5,000 keys

**Confirmed:** Current Lokalise plan has sufficient quota for this.

---

## 7. Build/Deploy Changes

### 7.1 Dockerfile Changes

Add `gettext` package and `compilemessages` step:

```dockerfile
# In the apt-get install section, add gettext:
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    gettext \
    && rm -rf /var/lib/apt/lists/*

# After pip install and npm build, compile message files:
RUN python -m django compilemessages
```

### 7.2 Dependencies

Add to `pyproject.toml` (or equivalent):

```toml
[project]
dependencies = [
    # ... existing deps ...
    "django-modeltranslation>=0.19",
    "python-lokalise-api>=3.0",  # Required for content library sync
]
```

### 7.3 Cloud Build Pipeline

**No changes to `cloudbuild.yaml` are needed** if .po files are committed to the repository (recommended approach). The Docker build handles compilation.

### 7.4 Entrypoint Changes

The existing `docker/entrypoint.sh` already runs `manage migrate`, which handles django-modeltranslation schema changes. No changes needed.

For the initial deployment after adding django-modeltranslation, a one-time command is needed:

```bash
manage update_translation_fields
```

This can be run manually after the first deploy, or added as a conditional step in the entrypoint (check if translation fields are populated).

### 7.5 Static File Compilation

No changes to static file handling. Translations are in `.mo` files (runtime), not static assets.

### 7.6 What Stays the Same

- `cloudbuild.yaml` -- no changes needed
- `docker/entrypoint.sh` -- `manage migrate` already handles new columns
- Content model source files -- django-modeltranslation patches models externally
- Template files -- can be updated incrementally

---

## 8. Developer Workflow

### 8.1 Day-to-Day: Adding/Changing Translatable Strings

1. Mark strings in templates with `{% trans %}` or `{% blocktrans %}`
2. Mark strings in Python with `gettext()` or `gettext_lazy()`
3. Run `manage makemessages -l en --no-obsolete`
4. Commit the updated `.po` file
5. Upload to Lokalise: `lokalise2 file upload --file locale/en/LC_MESSAGES/django.po --lang-iso en`
6. Translators work in Lokalise
7. Download translations: `lokalise2 file download --format po --original-filenames=true --unzip-to ./locale/`
8. Commit translated `.po` files
9. The Docker build compiles them to `.mo`

### 8.2 Adding a New Translatable Database Field

1. Add the field to `TranslationOptions` in `gyrinx/content/translation.py`
2. Run `manage makemigrations content -n "translate_<field>"`
3. Run `manage migrate`
4. Run `manage update_translation_fields` (copies existing English to `field_en`)
5. Commit migration and `translation.py` changes

### 8.3 Adding a New Language

Example: adding Spanish (`es`) to the existing five languages.

1. Add language to `settings.LANGUAGES`:
   ```python
   LANGUAGES = [
       ("en", _("English")),
       ("fr", _("French")),
       ("pl", _("Polish")),
       ("ru", _("Russian")),
       ("ja", _("Japanese")),
       ("es", _("Spanish")),  # NEW
   ]
   ```
2. Run `manage makemigrations content -n "add_spanish_translations"` (adds `_es` columns)
3. Run `manage makemessages -l es` (creates `locale/es/LC_MESSAGES/django.po`)
4. Commit migrations and new `.po` file
5. Deploy -- migration adds empty columns, `.po` file is compiled
6. Add language in both Lokalise projects
7. Translate via Lokalise (static strings + content library)

### 8.4 Branch/PR Workflow

- `.po` files are text-based and merge reasonably well
- `.mo` files are in `.gitignore` (compiled at build time)
- PRs should include updated `.po` files when translatable strings change
- Conflicts in `.po` files are usually auto-resolvable by git

### 8.5 Helper Script

Create `scripts/i18n.sh` for common operations:

```bash
#!/bin/bash
set -e

case "$1" in
  extract)
    echo "Extracting translatable strings..."
    manage makemessages -l en --no-obsolete
    echo "Done. Updated locale/en/LC_MESSAGES/django.po"
    ;;
  compile)
    echo "Compiling message files..."
    manage compilemessages
    echo "Done."
    ;;
  push)
    echo "Uploading to Lokalise..."
    lokalise2 --token "$LOKALISE_API_TOKEN" \
      --project-id "$LOKALISE_STATIC_PROJECT_ID" \
      file upload \
      --file "locale/en/LC_MESSAGES/django.po" \
      --lang-iso en \
      --replace-modified \
      --distinguish-by-file
    echo "Done."
    ;;
  pull)
    echo "Downloading from Lokalise..."
    lokalise2 --token "$LOKALISE_API_TOKEN" \
      --project-id "$LOKALISE_STATIC_PROJECT_ID" \
      file download \
      --format po \
      --original-filenames=true \
      --directory-prefix "" \
      --unzip-to "./locale/"
    echo "Done."
    ;;
  *)
    echo "Usage: $0 {extract|compile|push|pull}"
    exit 1
    ;;
esac
```

---

## 9. Content Library Workflow

### 9.1 Django Admin Translation

Content managers use the Django admin with `TabbedTranslationAdmin`:

1. Navigate to a content model in admin (e.g., Content Fighters)
2. Click on a record
3. See language tabs (English, French, Polish, Russian, Japanese)
4. Enter translations in each tab
5. Save

This gives content managers direct control for quick edits and review.

### 9.2 Lokalise API Sync

For community volunteer translation at scale:

**Push to Lokalise:**

```bash
manage sync_translations_to_lokalise
```

This reads all translatable content fields and creates/updates keys in the Lokalise dynamic content project.

**Pull from Lokalise:**

```bash
manage sync_translations_from_lokalise
```

This reads translated keys from Lokalise and updates the `field_<lang>` columns in the database.

### 9.3 Content Fixture Compatibility

The `loaddata_overwrite` command and content JSON fixtures need consideration:

- **Approach:** Include translation fields (`_en`, `_fr`, `_pl`, `_ru`, `_ja` columns) directly in fixture JSON files. Fixtures are the source of truth for content + translations.
- Fixture exports should include all translation fields. This makes fixtures larger but self-contained.
- django-modeltranslation's extended `loaddata` command can auto-populate the default language field if translation columns are missing from the fixture.
- The `loaddata_overwrite` command may need updates to handle the wider schema.

### 9.4 Content Updates Without Redeploy

Database content translations are live -- no redeploy is needed. Updating a translation in the Django admin or via a management command takes effect immediately.

Static string translations require a new Docker image (since `.mo` files are baked in at build time).

---

## 10. Migration Plan (Incremental Adoption)

### Phase 0: Infrastructure (1-2 days)

Set up the foundation without changing any user-facing behavior.

1. Install `django-modeltranslation` and `python-lokalise-api`, add to dependencies
2. Add `modeltranslation` to `INSTALLED_APPS` (before `django.contrib.admin`)
3. Add `LANGUAGES` (en, fr, pl, ru, ja), `LOCALE_PATHS`, `LocaleMiddleware` to settings
4. Configure `i18n_patterns` in `urls.py` with `prefix_default_language=False`
5. Create `gyrinx/content/translation.py` with registrations for key content models
6. Generate and apply migrations (adds `_en`, `_fr`, `_pl`, `_ru`, `_ja` columns -- ~100 new columns across content tables)
7. Run `manage update_translation_fields` to populate `_en` columns
8. Update `Dockerfile` to install `gettext` and add `compilemessages` step
9. Add `*.mo` to `.gitignore`
10. Create `locale/` directory structure for all 5 languages
11. Set up both Lokalise projects (static strings + dynamic content)
12. Verify: app works identically in English (regression test with `pytest -n auto`)

**Deliverables:** Infrastructure in place, no visible changes, all tests pass.

### Phase 1: Admin Translation UI + Content Sync (2-3 days)

Enable content managers to enter translations via admin, and build Lokalise content sync.

1. Update content admin classes to inherit from `TabbedTranslationAdmin`
2. Verify admin interface shows language tabs for all 5 languages
3. Build `sync_translations_to_lokalise` management command -- push content strings to Lokalise
4. Build `sync_translations_from_lokalise` management command -- pull translations back to database
5. Set up Lokalise dynamic content project with key naming convention
6. Test round-trip sync: push English content to Lokalise, add sample translations, pull back
7. Update fixture export to include translation columns

**Deliverables:** Content managers can enter translations via admin. Community volunteers can translate content library strings in Lokalise. Both sync commands work end-to-end.

### Phase 2: Pilot Template Translation (2-3 days)

Pick a small, self-contained section of the app and fully translate its templates.

Pilot: the **list archive/unarchive flow** (2-3 templates, ~40 strings).

1. Add `{% load i18n %}` to pilot templates
2. Wrap all strings with `{% trans %}` / `{% blocktrans %}`
3. Run `manage makemessages -l en`
4. Upload `.po` file to Lokalise static strings project
5. Add sample translations (via Lokalise AI or manual)
6. Download translations, compile, verify end-to-end in browser
7. Add language selector to footer template

**Deliverables:** One user flow fully translated end-to-end. Language selector in footer. Proves the full workflow.

### Phase 3: Expand Template Translation (1-2 weeks)

Systematically translate remaining templates, prioritizing by user traffic:

1. **High traffic pages:** List detail, fighter detail, campaign dashboard
2. **CRUD flows:** Create/edit list, add/edit fighter, equipment assignment
3. **Campaign flows:** Campaign management, battle tracking
4. **Remaining pages:** Settings, about, static pages

Work through Python source strings in parallel:
- Flash messages in views (convert f-strings to `gettext()` with `%()` placeholders)
- Form labels and help text (use `gettext_lazy()`)
- ValidationError messages
- TextChoices labels

### Phase 4: Automation (1-2 days)

1. Create GitHub Actions workflow for periodic translation sync (static strings)
2. Optionally set up Lokalise webhooks to trigger pulls
3. Add translation extraction to CI checks (ensure new strings are marked for translation)

---

## 11. Decisions Made

All open questions have been resolved:

| Question | Decision |
|----------|----------|
| **Languages** | French, Polish, Russian, Japanese (based on existing user base). All configured from day one. |
| **Language selection UI** | Footer link with language dropdown. URL prefixes for non-English (`/fr/`, `/pl/`, `/ru/`, `/ja/`). English URLs stay unprefixed. |
| **Translation approach** | Community volunteers + Lokalise AI. Full Lokalise sync for both static and dynamic content. |
| **Game terminology** | Translate everything, including faction names and game terms. |
| **Lokalise quota** | Confirmed sufficient for ~3,500-5,000 keys. |
| **URL scheme** | `i18n_patterns` with `prefix_default_language=False`. No breaking changes for English URLs. |
| **Content fixtures** | Include translation columns in fixture JSON. Fixtures are the source of truth for content + translations. |
| **Sync trigger** | Manual commands first (`sync_to_lokalise` / `sync_from_lokalise`). Automation added in Phase 4. |
| **Phase order** | Content sync moved earlier (Phase 1) so volunteers can start translating content immediately. |

## 12. Technical Considerations

- **`template_form_with_terms` system:** This custom string interpolation for fighter-specific terminology needs testing with i18n. The approach of wrapping template strings with `gettext_lazy()` and keeping `{term_singular}` placeholders should work, but needs validation during the pilot phase.

- **Dynamic string composition:** Many flash messages use f-strings with dynamic content. These all need to be converted to `gettext()` with `%()` format placeholders. This is a systematic but tedious change.

- **Japanese pluralization:** Japanese does not use plural forms. Django's gettext handles this gracefully -- the `nplurals=1` setting in Japanese `.po` files means only one form is needed. `{% blocktrans count %}` works correctly.

- **Lokalise API rate limits:** 6 requests/second, 1 concurrent per token. For ~2,000+ content keys, batch operations are needed. The API accepts up to 500 keys per request, so a full sync of 3,000 keys takes ~6 API calls.

- **Lokalise download limit:** The file download endpoint is limited to projects with under 10,000 key-language pairs (as of June 2025). With ~2,000 static string keys and 5 languages, this is ~10,000 key-language pairs -- at the limit. Monitor this and consider splitting static strings into multiple files if needed.

- **Migration size:** Registering ~20 fields across ~20 models with 4 target languages generates ~80 new columns. The migration will be large but PostgreSQL handles `ALTER TABLE ADD COLUMN` efficiently (especially for nullable columns, which is what django-modeltranslation creates).
