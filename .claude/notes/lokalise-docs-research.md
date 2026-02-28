# Lokalise Documentation Research

Research conducted 2026-02-05 for integrating Lokalise with Gyrinx Django application.

## 1. Django Integration (.po/.mo File Workflow)

### How It Works

Lokalise integrates with Django's standard i18n framework based on gettext `.po` files:

1. **Extract strings**: Run `./manage.py makemessages -l en` to generate `.po` files from Django template tags (`{% trans %}`, `{% blocktrans %}`) and Python source (`gettext()`, `gettext_lazy()`)
2. **Upload to Lokalise**: Push `.po` files via CLI or API
3. **Translate in Lokalise**: Translators work in Lokalise's web UI
4. **Download translations**: Pull translated `.po` files back via CLI or API
5. **Compile**: Run `./manage.py compilemessages` to generate `.mo` files

### File Structure

Django stores translation files in:
```
locale/<lang>/LC_MESSAGES/django.po
locale/<lang>/LC_MESSAGES/django.mo
```

### CLI Commands for Django

**Upload (push) source strings:**
```bash
lokalise2 --token <token> --project-id <project_id> \
  file upload --file "locale/en/LC_MESSAGES/django.po" --lang-iso en
```

**Download (pull) translations:**
```bash
lokalise2 --token <token> --project-id <project_id> \
  file download --format po --original-filenames=true \
  --directory-prefix "" --unzip-to "./"
```

This downloads a `.zip` bundle and extracts it into the project, preserving the `locale/<lang>/LC_MESSAGES/` directory structure.

## 2. Static Content (Templates & Python Source)

### What Gets Extracted

- **Template strings**: `{% trans "Welcome" %}`, `{% blocktrans %}...{% endblocktrans %}`
- **Python strings**: `gettext("Hello")`, `gettext_lazy("Hello")`, `pgettext("context", "text")`
- **Form labels/help text**: Anything wrapped in translation functions

### Workflow

1. Django's `makemessages` scans templates and Python files
2. Produces `.po` files with `msgid` (source) and `msgstr` (translation) pairs
3. These files are uploaded to Lokalise, which parses them into key-value pairs
4. Translators work in Lokalise's editor with context, screenshots, etc.
5. Translated `.po` files are downloaded back

### Key Naming

When `.po` files are uploaded, Lokalise uses the `msgid` as the key name by default. For Django, this means the English source string is the key (which is Django's standard pattern).

## 3. Dynamic Content (Database Translation)

### The Challenge

Gyrinx stores game content (ContentFighter, ContentEquipment, etc.) in PostgreSQL. These strings are not in `.po` files - they're in database records. Lokalise does not natively sync with databases.

### Lokalise's Recommended Approach

From Lokalise's documentation on dynamic content:

1. **Separate Lokalise project** for dynamic content (distinct from the static strings project)
2. **Key naming uses database identifiers**: e.g., `contentfighter.<id>.name`, `contentequipment.<id>.description`
3. **Sync via API**: Build a sync service that:
   - Reads database content
   - Creates/updates keys in Lokalise via the API
   - Pulls translations back from Lokalise
   - Stores translated values in the database

### Sync Strategies

- **Full sync**: Process all content (suitable for small datasets)
- **Delta sync**: Only process new/changed content (better for scale)
- **Sync trigger**: Can be manual (management command), scheduled (cron), or webhook-triggered

### Key Naming Convention for Database Content

Recommended pattern: `<model>.<id>.<field>`

Examples:
```
contentfighter.uuid-1234.name
contentfighter.uuid-1234.description
contentequipment.uuid-5678.name
contentweaponprofile.uuid-9012.trait_description
```

### Database Schema Options for Storing Translations

Three approaches (to be used alongside django-modeltranslation or custom solution):

1. **Localized columns** (django-modeltranslation approach): Add `name_en`, `name_fr`, `name_de` columns to existing tables
2. **Separate translation table**: A generic translation table with `(model, field, record_id, language, value)`
3. **Separate database**: A dedicated translations database (overkill for most projects)

### django-modeltranslation Integration

django-modeltranslation adds language-specific columns automatically:
- Register models in `translation.py` specifying which fields to translate
- Creates `field_en`, `field_fr`, etc. columns via migrations
- Transparently returns the active language's value when accessing `model.field`
- Admin integration for editing translations

The Lokalise sync would populate these `field_<lang>` columns via the API.

## 4. Lokalise Project Setup

### Recommended Structure

- **Project 1: Static strings** - For `.po` files from Django templates/Python
  - Platform: "Web"
  - File format: Gettext PO
  - Sync via CLI in CI/CD

- **Project 2: Dynamic content** - For database content
  - Platform: "Other" or "Web"
  - Keys managed via API
  - Sync via management commands or scheduled jobs

### Key Organization

- Use **tags** to categorize keys (e.g., `ui`, `content-library`, `fighter-names`, `equipment`)
- Use **descriptions** to provide context for translators
- Use **screenshots** (Lokalise supports them) to show where strings appear
- Limit nesting to 2-3 levels: `section.subsection.key_name`

### Key Naming Best Practices

- Be descriptive: `campaign.settings.max_players_label` not `label1`
- Use consistent separators (dots for nesting)
- Include component/page context: `fighter_card.name`, `equipment_list.empty_state`
- For database content, use model and field: `contentfighter.<id>.name`

### Key Quotas

Keys have quota limits at the team level across all projects. Translations per key are unlimited. Project languages are also unlimited.

## 5. Lokalise API

### Authentication

```python
import lokalise
client = lokalise.Client('YOUR_API_TOKEN')
```

Or with OAuth 2:
```python
client = lokalise.OAuthClient('YOUR_OAUTH2_API_TOKEN')
```

### Python SDK: python-lokalise-api

Install: `pip install python-lokalise-api`

### Key Operations

**Create keys with translations:**
```python
client.create_keys('PROJECT_ID', [
    {
        "key_name": "contentfighter.uuid-1234.name",
        "platforms": ["web"],
        "description": "Fighter name in content library",
        "tags": ["content-library", "fighter"],
        "translations": [
            {"language_iso": "en", "translation": "Ganger"}
        ]
    }
])
```

**List keys (with cursor pagination):**
```python
keys = client.keys('PROJECT_ID', {"limit": 500})
# Use cursor pagination for large datasets
```

**Update keys:**
```python
client.update_keys('PROJECT_ID', [
    {
        "key_id": 12345,
        "translations": [
            {"language_iso": "en", "translation": "Updated value"}
        ]
    }
])
```

**Delete keys:**
```python
client.delete_keys('PROJECT_ID', [34567, 78913])
```

### File Upload (for .po files)

```python
import base64

with open('locale/en/LC_MESSAGES/django.po', 'rb') as f:
    data = base64.b64encode(f.read()).decode('utf-8')

process = client.upload_file('PROJECT_ID', {
    "data": data,
    "filename": "locale/en/LC_MESSAGES/django.po",
    "lang_iso": "en"
})
# Returns a QueuedProcess - upload is asynchronous
```

### File Download

```python
response = client.download_files('PROJECT_ID', {
    "format": "po",
    "original_filenames": True,
    "directory_prefix": ""
})
# Returns URL to download .zip bundle (valid for 12 months)
```

**Important limitation (June 2025+)**: Download endpoint limited to projects with under 10,000 key-language pairs.

### Rate Limiting

- 6 requests per second
- Only 1 concurrent request per token

## 6. Webhooks

### Setup

Configure in Lokalise project settings > Apps > Webhooks. Provide:
- Endpoint URL (must accept POST, respond with 2xx within 8 seconds)
- Optional custom headers for authentication
- Select events to subscribe to

### Security

Each webhook includes headers:
- `X-Secret`: Auto-generated token for verification
- `Project-Id`: Lokalise project ID
- `Webhook-Id`: The webhook handler ID

IP whitelist (if needed): `3.67.82.138`, `3.123.244.162`, `3.124.254.35`, `18.185.175.152`, `18.192.113.205`, `18.194.146.34`

### Key Events for Translation Workflow

| Event | Description |
|-------|-------------|
| `project.translation.updated` | Single translation changed |
| `project.translations.updated` | Bulk translations changed (max 300/event) |
| `project.translation.proofread` | Translation reviewed |
| `project.task.language.closed` | Language completed in a task |
| `team.order.completed` | Professional translation order done |
| `project.imported` | File uploaded to project |
| `project.exported` | File downloaded from project |
| `project.key.added` / `project.keys.added` | New keys created |

### Retry Behavior

Failed webhooks retry with progressive backoff:
- ~1 min, ~5 min, ~10 min, ~20 min, ~30 min, then hourly for 24 hours
- After 24 hours, events are discarded and handler is disabled

### Integration with Django

The Gyrinx app already has a webhook handler in the `api` app. A Lokalise webhook endpoint could:
1. Receive `project.task.language.closed` events
2. Trigger a management command to pull translations
3. Update the database or `.po` files accordingly

## 7. CLI Tool (lokalise2)

### Installation

```bash
# macOS
brew tap lokalise/cli-2 && brew install lokalise2

# Docker
docker pull lokalise/lokalise-cli-2
```

### Configuration

Create `config.yml` or pass flags directly:
```yaml
token: "YOUR_API_TOKEN"
project_id: "YOUR_PROJECT_ID"
```

### Key Commands

```bash
# Upload .po file
lokalise2 file upload --file "locale/en/LC_MESSAGES/django.po" --lang-iso en

# Download all translations
lokalise2 file download --format po --original-filenames=true --directory-prefix "" --unzip-to "./"

# Filter by tags
lokalise2 file download --format po --include-tags "production"

# List projects
lokalise2 project list

# Manage keys
lokalise2 key list
lokalise2 key create --key-name "my.key" --platforms web
```

### Flag Syntax Notes

- Boolean flags require `=`: `--original-filenames=true`
- String lists use commas: `--include-tags=one,two`
- JSON objects are escaped strings

### Rate Limiting

Same as API: 6 requests/second, 1 concurrent request per token.

## 8. Existing Django-Lokalise Package

The `django-lokalise` package (pip install django-lokalise) exists but is **unmaintained** (last release: March 2017, version 0.1.5). It provides:
- Middleware for reloading translations
- Webhook endpoint for auto-pulling translations
- Basic integration with Django's i18n

**Recommendation**: Do NOT use this package. Instead, build a custom integration using the official `python-lokalise-api` SDK, which is actively maintained.

## 9. Automation & CI/CD Integration

### Recommended CI/CD Workflow

1. **On feature branch merge to main**:
   - Run `makemessages` to extract new/changed strings
   - Upload `.po` files to Lokalise via CLI
   - Optionally tag keys with version/branch info

2. **Translation completed in Lokalise**:
   - Webhook triggers download of translations
   - OR: Scheduled job pulls translations periodically
   - OR: CI step pulls before deployment

3. **On deployment**:
   - Pull latest translations from Lokalise
   - Run `compilemessages` to generate `.mo` files
   - Deploy with updated translations

### For Dynamic Content

1. **Content changes in Django admin**:
   - Post-save signal or management command pushes new content to Lokalise
   - Keys created with model/field naming convention

2. **Translation completed**:
   - Webhook or scheduled job pulls translations from Lokalise API
   - Updates django-modeltranslation fields in database

3. **On deployment / periodically**:
   - Full sync management command ensures database translations are current

## 10. Summary & Recommendations

### Static Content (Templates/Python)
- Standard Django i18n with gettext `.po` files
- Lokalise CLI for push/pull in CI/CD
- One Lokalise project for static strings

### Dynamic Content (Database)
- django-modeltranslation for schema
- Separate Lokalise project for dynamic keys
- Python SDK (python-lokalise-api) for API sync
- Management commands for sync operations
- Webhook integration for automated updates

### Key Tools
- `lokalise2` CLI for file operations
- `python-lokalise-api` Python SDK for programmatic access
- Lokalise webhooks for automation triggers

### Estimated Complexity
- Static i18n: Moderate (standard Django pattern, well-documented)
- Dynamic content: High (custom sync logic, schema changes, ongoing maintenance)
- CI/CD integration: Moderate (CLI commands in pipeline)
