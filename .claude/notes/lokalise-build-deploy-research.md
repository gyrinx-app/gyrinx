# Lokalise Integration: Build/Deploy Implications & Database Content Translation

## 1. Django Database Content Translation Libraries

### 1.1 django-modeltranslation (Recommended)

**How it works:**
- Uses a "registration" approach (similar to Django admin) to declare which model fields are translatable
- You create a `translation.py` file in each app, defining `TranslationOptions` classes
- For each registered field and each language in `settings.LANGUAGES`, it adds a new column to the **same table** (e.g., `name_en`, `name_de`, `name_fr`)
- The original field becomes a proxy that returns the value for the currently active language
- All translation fields are added as real Django model fields with `blank=True, null=True`

**Example registration (for Gyrinx content models):**
```python
# gyrinx/content/translation.py
from modeltranslation.translator import register, TranslationOptions
from .models import ContentFighter, ContentEquipment, ContentHouse, ContentSkill

@register(ContentFighter)
class ContentFighterTranslationOptions(TranslationOptions):
    fields = ('type',)  # Only translatable text fields

@register(ContentEquipment)
class ContentEquipmentTranslationOptions(TranslationOptions):
    fields = ('name',)

@register(ContentHouse)
class ContentHouseTranslationOptions(TranslationOptions):
    fields = ('name',)

@register(ContentSkill)
class ContentSkillTranslationOptions(TranslationOptions):
    fields = ('name',)
```

**Migration implications:**
- Running `makemigrations` after registration generates migrations that ADD new columns
- For example, registering `ContentEquipment.name` with languages `en`, `de`, `fr` creates: `name_en`, `name_de`, `name_fr` columns
- Existing data needs to be copied to the default language field using `manage update_translation_fields`
- Each new language added to `settings.LANGUAGES` requires a new migration
- **Impact on Gyrinx**: The content app has ~30+ models. Registering even a few fields across key models would generate significant migration files and widen the database tables

**Admin integration:**
- Provides `TranslationAdmin`, `TranslationStackedInline`, `TranslationTabularInline`
- `TabbedTranslationAdmin` adds jQuery UI tabs to separate languages visually
- Gyrinx uses custom admin classes that inherit from `admin.ModelAdmin` - these would need to also inherit from `TranslationAdmin`
- Inline admin classes would need similar treatment

**Performance considerations:**
- No extra JOINs (all data in same table) - this is a significant advantage
- Wider tables, but PostgreSQL handles this well
- Existing `select_related` and `prefetch_related` continue to work without modification
- The original field accessor automatically returns the correct language based on `get_language()`
- No additional N+1 query risk compared to current codebase

**Management commands provided:**
1. `update_translation_fields` - copies existing field values to default language translation fields (run once after initial setup)
2. `sync_translation_fields` - detects new translation fields and generates ALTER TABLE SQL (prefer migrations instead)
3. Extended `loaddata` - auto-populates translation fields when loading fixtures

### 1.2 django-parler (Alternative)

**How it works:**
- Stores translations in **separate tables** (one translation table per model)
- Each translation row contains: `master_id`, `language_code`, and the translated fields
- Requires explicit `.translated()` or `.active_translations()` in querysets

**Key differences from django-modeltranslation:**
- Separate table storage = extra JOINs on every query
- Plays well with django-polymorphic (which Gyrinx uses for ContentMod) - this is a potential advantage
- Less mature admin integration
- Last release was older (less actively maintained)

**Concern for Gyrinx:**
- Gyrinx uses `django-polymorphic` for the `ContentMod` hierarchy. django-parler has better documented compatibility with polymorphic models
- However, ContentMod fields are unlikely to need translation (they are stat modifiers, not user-facing text)
- The JOIN overhead would impact the already performance-sensitive fighter card rendering

### 1.3 Recommendation

**django-modeltranslation is the better fit** because:
1. Same-table storage avoids JOIN overhead on the query-heavy content models
2. Transparent field access means minimal template changes
3. Better maintained and more widely used
4. Migration-based approach fits Gyrinx's existing workflow
5. The polymorphic compatibility concern is minor since ContentMod subclasses don't need translatable fields

## 2. Build Process Changes

### 2.1 Current Build Pipeline (from `cloudbuild.yaml`)

```
Cancel Previous Builds → Notify Start → Docker Build → Push → Tag Latest → Push Latest → Deploy → Notify Deploy
```

The Docker build (`Dockerfile`) currently:
1. Installs Python dependencies (`pip install --editable .`)
2. Installs Node.js and npm dependencies
3. Runs `npm run build` (frontend assets)

The entrypoint (`docker/entrypoint.sh`) runs at deploy time:
1. `manage collectstatic --noinput`
2. `manage migrate`
3. `manage ensuresuperuser --no-input`
4. `daphne` (ASGI server)

### 2.2 Changes Required for Static String Translation (.po files)

**Dockerfile additions:**
```dockerfile
# Install gettext for compilemessages
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    gettext \   # NEW: required for compilemessages
    && rm -rf /var/lib/apt/lists/*

# After pip install, compile message files
RUN python -m django compilemessages  # NEW: compile .po -> .mo
```

**Two approaches for translation file management:**

**Option A: Commit .po files to repo, compile at build time**
- Developers run `manage makemessages` locally to extract strings
- .po files are committed to the repository under `locale/`
- Translations are done in Lokalise, then downloaded and committed
- `compilemessages` runs during Docker build
- .mo files are NOT committed (they're build artifacts)

**Option B: Pull translations from Lokalise at build time**
- Source .po files are committed (English source strings)
- Cloud Build pipeline has a pre-build step that runs `lokalise2 file download`
- This requires the Lokalise API token as a Cloud Build secret
- More automated but adds build dependency on Lokalise API availability

**Recommended: Option A** (commit .po files) for simplicity and reliability. The build should not depend on external API availability.

### 2.3 Changes Required for Database Content Translation (django-modeltranslation)

**No build changes needed** - django-modeltranslation operates at the database level via Django migrations. The `manage migrate` step in `entrypoint.sh` handles schema changes automatically.

### 2.4 Cloud Build Pipeline Additions (if using Option B)

Would need a new step before Docker build:
```yaml
- name: "gcr.io/google.com/cloudsdktool/cloud-sdk:slim"
  id: Pull Translations
  entrypoint: bash
  secretEnv:
    - _LOKALISE_API_TOKEN
  args:
    - -c
    - |
      # Install lokalise2 CLI
      curl -sfL https://raw.githubusercontent.com/lokalise/lokalise-cli-2-go/master/install.sh | sh
      # Pull translations
      ./bin/lokalise2 --token $$_LOKALISE_API_TOKEN \
        --project-id $PROJECT_LOKALISE_ID \
        file download --format po \
        --original-filenames=true \
        --directory-prefix "" \
        --unzip-to "./locale/"
```

This is **not recommended** for the initial implementation.

## 3. Deploy Process Changes

### 3.1 Static String Translations

No deploy changes needed beyond what's in the Docker image. The compiled .mo files are baked into the image at build time.

### 3.2 Database Content Translations (django-modeltranslation)

**The `entrypoint.sh` already runs `manage migrate`**, which will apply any new translation field migrations. No changes needed to the entrypoint.

However, **initial data population** is a concern:

1. **First-time setup**: After the migration adds translation columns, the new columns are empty. Need to run `manage update_translation_fields` once to copy existing English values to `field_en` columns.

2. **Ongoing translation sync**: Translations for database content need a mechanism to get from Lokalise into the database. Options:
   - **Manual**: Admin users enter translations via Django admin (simplest, doesn't leverage Lokalise for DB content)
   - **Management command**: Custom command that imports a Lokalise download into the database
   - **API sync**: Background task that pulls from Lokalise API and updates DB

**Recommended approach for DB content:**
- Phase 1: Use Django admin for database content translations (with TabbedTranslationAdmin)
- Phase 2: Build a custom management command to sync DB translations from Lokalise exports

### 3.3 Impact on Content Export/Import (dumpdata/loaddata)

The `loaddata_overwrite` command in the codebase truncates and reloads content data. With django-modeltranslation:
- Fixture files would need to include translation fields (`name_en`, `name_de`, etc.)
- The extended `loaddata` command from modeltranslation can auto-populate the default language
- The `loaddata_overwrite` command may need adjustments to handle translation fields
- JSON fixture format would grow (each translatable field multiplied by number of languages)

### 3.4 Translation File Updates Without Full Redeploy

For static strings:
- A full redeploy IS required (new .mo files need to be in the Docker image)
- This is the standard approach for Django i18n

For database content:
- No redeploy needed - database translations are live
- Can be updated via admin, management command, or API at any time

## 4. Developer Workflow

### 4.1 Adding New Translatable Strings (Templates/Views)

1. Mark strings in templates with `{% trans "string" %}` or `{% blocktrans %}...{% endblocktrans %}`
2. Mark strings in Python code with `gettext("string")` or `gettext_lazy("string")`
3. Run `manage makemessages -l en` to extract strings to `locale/en/LC_MESSAGES/django.po`
4. Commit the updated .po file
5. Upload to Lokalise: `lokalise2 file upload --file locale/en/LC_MESSAGES/django.po --lang-iso en`
6. Translators work in Lokalise
7. Download translations: `lokalise2 file download --format po --original-filenames=true --unzip-to ./locale/`
8. Commit translated .po files
9. The build compiles them to .mo

### 4.2 Adding New Translatable Database Fields

1. Add the field to `TranslationOptions` in `translation.py`
2. Run `manage makemigrations` - generates migration adding `field_lang` columns
3. Run `manage migrate` locally
4. Run `manage update_translation_fields` to populate default language
5. Commit migration and translation.py changes
6. On deploy, `manage migrate` in entrypoint adds columns to production DB

### 4.3 Adding a New Language

1. Add language to `settings.LANGUAGES` tuple
2. Run `manage makemigrations` - generates migration adding new columns for all registered fields
3. Run `manage makemessages -l <new_lang_code>` - creates .po file for the new language
4. Deploy - migration runs, adding empty columns
5. Translate via admin (DB content) or Lokalise (.po files)

### 4.4 Branch/PR Workflow with Translation Files

- `.po` files are text-based and diff/merge reasonably well
- `.mo` files should be in `.gitignore` (compiled at build time)
- Conflicts in .po files can happen but are usually auto-resolvable
- The `locale/` directory should be at the project root
- PRs should include updated .po files when strings change
- Lokalise key management: use branch tags in Lokalise to track which strings belong to which feature branch

### 4.5 String Change Management

- Modifying an English source string creates a new key in Lokalise (old translation is lost)
- Renaming should be done carefully - consider using string IDs rather than source text as keys
- Lokalise supports "key" based projects where keys are stable identifiers

## 5. Lokalise CLI (lokalise2) Integration

### 5.1 Installation

```bash
# macOS
brew tap lokalise/cli-2 && brew install lokalise2

# Linux (in CI)
curl -sfL https://raw.githubusercontent.com/lokalise/lokalise-cli-2-go/master/install.sh | sh

# Docker
docker pull lokalise/lokalise-cli-2-go
```

### 5.2 Configuration

Create `lokalise.yml` (or use `--config` flag):
```yaml
token: ""  # Set via env var LOKALISE_TOKEN instead
project-id: "your-project-id"
```

Required environment variables:
- `LOKALISE_API_TOKEN` - Read/write API token
- `LOKALISE_PROJECT_ID` - Project identifier (found in Lokalise project settings)

### 5.3 Key Commands

**Upload source strings:**
```bash
lokalise2 --token $LOKALISE_API_TOKEN \
  --project-id $LOKALISE_PROJECT_ID \
  file upload \
  --file "locale/en/LC_MESSAGES/django.po" \
  --lang-iso en \
  --replace-modified \
  --distinguish-by-file
```

**Download all translations:**
```bash
lokalise2 --token $LOKALISE_API_TOKEN \
  --project-id $LOKALISE_PROJECT_ID \
  file download \
  --format po \
  --original-filenames=true \
  --directory-prefix "" \
  --unzip-to "./locale/"
```

**Rate limits:** 6 requests/second per token, 1 concurrent request per token.

### 5.4 CI/CD Integration Patterns

**GitHub Actions (recommended for Gyrinx):**
```yaml
# .github/workflows/sync-translations.yml
name: Sync Translations from Lokalise
on:
  workflow_dispatch:  # Manual trigger
  schedule:
    - cron: '0 6 * * 1'  # Weekly Monday 6am

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install Lokalise CLI
        run: curl -sfL https://raw.githubusercontent.com/lokalise/lokalise-cli-2-go/master/install.sh | sh
      - name: Download translations
        run: |
          ./bin/lokalise2 --token ${{ secrets.LOKALISE_API_TOKEN }} \
            --project-id ${{ secrets.LOKALISE_PROJECT_ID }} \
            file download --format po \
            --original-filenames=true \
            --directory-prefix "" \
            --unzip-to "./locale/"
      - name: Compile messages
        run: python -m django compilemessages
      - name: Create PR
        uses: peter-evans/create-pull-request@v6
        with:
          title: "Update translations from Lokalise"
          branch: translations/update
```

**Alternative: Lokalise webhook → GitHub Actions:**
- Lokalise can trigger a webhook when translations are completed
- The webhook can trigger a GitHub Actions workflow
- This provides real-time updates instead of scheduled polling

## 6. Impact Summary on Current Infrastructure

### 6.1 Files That Need Modification

| File | Change | Reason |
|------|--------|--------|
| `Dockerfile` | Add `gettext` package, add `compilemessages` step | Compile .po to .mo at build time |
| `settings.py` | Add `LANGUAGES`, `LOCALE_PATHS`, `USE_I18N`, i18n middleware, modeltranslation to INSTALLED_APPS | Enable Django i18n framework |
| `gyrinx/content/translation.py` | New file | Register content models for translation |
| `gyrinx/content/admin.py` | Inherit from TranslationAdmin | Enable translation editing in admin |
| `.gitignore` | Add `*.mo` | Exclude compiled message files |
| `docker/entrypoint.sh` | Optionally add `update_translation_fields` (first deploy only) | Populate default language translations |
| `requirements.txt` | Add `django-modeltranslation` | New dependency |

### 6.2 Files That Do NOT Need Modification

| File | Reason |
|------|--------|
| `cloudbuild.yaml` | No changes needed if .po files are committed to repo |
| `docker/entrypoint.sh` | `manage migrate` already handles new columns |
| Content model files | django-modeltranslation patches models externally |
| Template files | Can be done incrementally (templates without `{% trans %}` just show English) |

### 6.3 New Files Required

| File | Purpose |
|------|---------|
| `locale/en/LC_MESSAGES/django.po` | English source strings (auto-generated) |
| `locale/<lang>/LC_MESSAGES/django.po` | Per-language translation files |
| `gyrinx/content/translation.py` | Model translation registration |
| `.github/workflows/sync-translations.yml` | Optional: automated translation sync |
| `lokalise.yml` | Optional: CLI configuration |

### 6.4 Secrets/Config Required

| Secret | Where | Purpose |
|--------|-------|---------|
| `LOKALISE_API_TOKEN` | GitHub Secrets, optionally Cloud Build Secrets | API access for CLI |
| `LOKALISE_PROJECT_ID` | GitHub Secrets or config file | Project identifier |

## 7. Migration Strategy for Existing Content Data

### Phase 1: Add translation infrastructure
1. Install django-modeltranslation
2. Register key content models (ContentHouse, ContentFighter, ContentEquipment, ContentSkill, ContentWeaponTrait, ContentRule, ContentInjury)
3. Generate and apply migrations (adds `field_en`, etc. columns)
4. Run `update_translation_fields` to populate `_en` columns from existing data

### Phase 2: Enable admin translation
1. Update admin classes to use `TranslationAdmin`
2. Content managers can now enter translations per language via tabbed admin interface

### Phase 3: Integrate Lokalise for DB content (optional)
1. Build custom management command to export translatable DB content to .po-like format
2. Upload to Lokalise for translation
3. Build custom management command to import translations back to DB
4. Or: use Lokalise API directly for DB content sync

### Critical consideration: Content fixtures
The `loaddata_overwrite` command and content JSON fixtures would need updating:
- Existing fixtures only have the original field values
- After modeltranslation, fixtures need `name_en`, `name_de`, etc.
- Or: load fixtures first (populates original field), then run `update_translation_fields`
- The modeltranslation-extended `loaddata` command helps with this

## 8. Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Large migration (many new columns) | Medium | Run on staging first, test migration time |
| Wider database tables | Low | PostgreSQL handles wide tables well; content tables are not high-write |
| Template breakage | Low | django-modeltranslation is transparent; original field returns active language |
| Admin interface complexity | Medium | TabbedTranslationAdmin keeps it organized |
| Fixture/loaddata compatibility | Medium | Test loaddata_overwrite with translated models on staging |
| Build time increase | Low | `compilemessages` is fast; `gettext` is a small package |
| Lokalise API dependency | Low | Use committed .po files, not build-time API calls |
| Performance regression | Low | Same-table approach means no extra queries |
