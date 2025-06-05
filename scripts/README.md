# Gyrinx Scripts

This directory contains utility scripts for development and maintenance.

## Scripts

### `screenshot.py`

Automated UI screenshot utility using Playwright for capturing views without manual intervention.

**Usage:**

```bash
# Basic usage
python scripts/screenshot.py <url_name> [options]

# Capture before/after screenshots for UI changes
python scripts/screenshot.py core:campaign --before --args <campaign_id>
python scripts/screenshot.py core:campaign --after --args <campaign_id>

# Multiple viewports
python scripts/screenshot.py core:list --viewports desktop,mobile --args <list_id>

# Specific element only
python scripts/screenshot.py core:campaign --selector ".campaign-header" --args <id>

# Check Playwright installation
python scripts/screenshot.py --check
```

**Options:**

- `url_name`: Django URL name (e.g., 'core:campaign', 'core:list')
- `--args`: Arguments for the URL (e.g., IDs)
- `--before`: Label screenshot as 'before'
- `--after`: Label screenshot as 'after'
- `--label`: Custom label for the screenshot
- `--viewports`: Comma-separated viewports (desktop,tablet,mobile)
- `--theme`: Color scheme (light/dark, default: light)
- `--output-dir`: Output directory (default: ui_archive)
- `--selector`: CSS selector for specific element
- `--no-full-page`: Capture only viewport (not full page)
- `--username`: Username to authenticate as (default: admin)
- `--check`: Check if Playwright is installed

**Requirements:**

- Playwright must be installed: `pip install playwright`
- Django project must be properly configured
- User account must exist for authentication
- Chromium browser will be automatically installed on first run

**Output:**

- Screenshots are saved to `ui_archive/` directory
- Files are named: `<url_name>_<label>_<viewport>_<timestamp>.png`
- Latest versions: `<url_name>_<label>_<viewport>_latest.png`
- Comparison markdown is generated for before/after pairs

### Other Scripts

- `check_migrations.sh`: Checks for migration conflicts
- `fmt-check.sh`: Runs formatting checks
- `manage.py`: Django management wrapper
- `migrate.sh`: Runs database migrations
- `test.sh`: Runs the test suite
