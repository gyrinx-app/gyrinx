# Content Library Management

This guide explains how to get the content library data from production into your local development environment using the custom-ish `dumpdata` and `loaddata_overwrite` process.

> [!IMPORTANT]
> This process is only available for trusted developers and admins who have been granted access to the production infrastructure.

## Why You Need This

Gyrinx is really limited without the content library data - it's what makes the application useful. The content library includes all the game data (fighters, equipment, weapons, skills, houses) that's managed by the Gyrinx content team in production.

Without this data, you'll have an empty shell of an application that's pretty hard to test or develop against.

## The Process

### 1. Export from Production

The export uses the `gyrinx-dumpdata` Cloud Run job in production:

1. Access the Google Cloud Console (you need permissions)
2. Navigate to Cloud Run → Jobs
3. Find and run the `gyrinx-dumpdata` job
4. The job exports all content data to `latest.json` in the `gyrinx-app-bootstrap-dump` bucket

Or use the gcloud CLI:

```bash
# Trigger the dumpdata job
gcloud run jobs execute gyrinx-dumpdata --region=europe-west2
```

### 2. Download the Export

```bash
# Download latest content from production (requires GCS access)
gsutil cp gs://gyrinx-app-bootstrap-dump/latest.json .
```

### 3. Import Locally

The `loaddata_overwrite` command replaces your local content with the production data:

```bash
# Check what will be changed first
manage loaddata_overwrite latest.json --dry-run

# Actually import the data
manage loaddata_overwrite latest.json
```

## What loaddata_overwrite Does

This custom command is different from Django's built-in `loaddata`:

1. **Clears existing content** - Wipes all content models before importing (destructive!)
2. **Handles foreign keys** - Temporarily disables constraints during import
3. **Skips historical records** - Ignores django-simple-history tables
4. **Actually works** - Django's loaddata would fail on duplicate keys

The command lives at `gyrinx/core/management/commands/loaddata_overwrite.py`.

## Common Tasks

### Getting Started with Development

When you first set up Gyrinx locally:

```bash
# Get the latest content library
gsutil cp gs://gyrinx-app-bootstrap-dump/latest.json .

# Import it
manage loaddata_overwrite latest.json --verbose
```

### Debugging Production Content

Need to investigate a content issue from production?

```bash
# Get fresh data
gsutil cp gs://gyrinx-app-bootstrap-dump/latest.json .

# Import with verbose output to see what's happening
manage loaddata_overwrite latest.json --verbose

# Poke around
manage shell
```

## Warnings

- **This deletes all your local content data** - The command wipes content models before importing
- **Don't commit latest.json** - It's already in .gitignore, keep it that way
- **Need access** - You must be a trusted developer with GCS permissions
- **Big file** - The export can be large, depending on how much content exists

## If Things Go Wrong

### Import Failed?

The database might be partially cleared. Just run the command again - it'll clear everything and start fresh.

### No Access?

If you can't access the GCS bucket or Cloud Run job, you'll need to ask an admin for:
1. Access to the production GCP project
2. Permissions for the `gyrinx-app-bootstrap-dump` bucket
3. Ability to run the `gyrinx-dumpdata` Cloud Run job

### Corrupted JSON?

Re-download from the bucket. The export job creates valid JSON, so corruption usually happens during download.

## Technical Details

The command uses PostgreSQL's `TRUNCATE CASCADE` for fast deletion, but falls back to regular `DELETE` if that fails. Foreign key checks are disabled with `SET session_replication_role = 'replica'` during import.

Historical models (from django-simple-history) are automatically detected and skipped - they're managed separately by the history system.
