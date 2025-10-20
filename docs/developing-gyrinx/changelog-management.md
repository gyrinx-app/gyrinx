---
hidden: true
---

# Changelog Management

Gyrinx uses an automated changelog management system to keep track of changes and releases. The changelog follows the [Keep a Changelog](https://keepachangelog.com/) format and helps users and developers understand what has changed between versions.

## Automated Changelog Updates

The project includes a script that automates the process of updating the changelog based on Git commits.

### Running the Update Script

```bash
# Update the default CHANGELOG.md file
./scripts/update_changelog.sh

# Update a specific changelog file
./scripts/update_changelog.sh path/to/changelog.md
```

### How It Works

The changelog update script (`scripts/update_changelog.sh`) performs the following steps:

1. **Date Detection**: Finds the last date entry in the existing changelog
2. **Commit Analysis**: Retrieves all commits since that date using `git log`
3. **Content Generation**: Uses the `llm` CLI tool with Claude 3.5 Sonnet to analyze commits and generate formatted entries
4. **Categorization**: Groups changes by:
   - Features (commits with `feat:` prefix)
   - Fixes (commits with `fix:` prefix)
   - Documentation (commits with `docs:` prefix)
   - Dependencies (dependency updates)
   - UI/UX (user interface improvements)
   - Other (any other significant changes)
5. **File Update**: Creates a backup and updates the changelog file
6. **Validation**: Ensures the generated content is valid before replacing the original

### Prerequisites

- The `llm` CLI tool must be installed and configured with Claude 3.5 Sonnet
- Git repository with commit history
- Write permissions to the changelog file

### Changelog Format

The changelog follows this structure:

```markdown
# Changelog

All notable changes to the Gyrinx project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## Recent Changes

### YYYY-MM-DD

#### Features
- Description of new features (#PR)

#### Fixes
- Description of bug fixes (#PR)

#### Documentation
- Documentation updates

---

_Last updated: YYYY-MM-DD_
```

### Best Practices

1. **Commit Messages**: Use conventional commit prefixes (`feat:`, `fix:`, `docs:`, etc.) for better categorization
2. **PR References**: Include PR numbers in commit messages (e.g., `#256`)
3. **Regular Updates**: Run the script regularly to keep the changelog current
4. **Review Generated Content**: Always review the generated changelog entries for accuracy

### Manual Changelog Helper

If you prefer to update the changelog manually or need to see what changes need to be added:

```bash
./scripts/update_changelog_manual.sh
```

This will display:

- The last changelog date
- Recent commits that need to be added
- A formatted prompt you can use with Claude or another LLM

## Development Workflow Integration

### For Claude Code Users

When working with Claude Code on this repository, Claude will check the last date in CHANGELOG.md. If it's more than 2 days old, Claude will proactively offer to run the changelog update script to ensure the changelog stays current with recent development activity.

### For Developers

Consider updating the changelog:

- Before creating a new release
- After merging significant features or fixes
- As part of your regular maintenance routine
- When the last update is more than a few days old

### Troubleshooting

If the script fails:

1. **Check LLM Installation**: Ensure `llm` is installed and configured

    ```bash
    llm --version
    llm models
    ```

2. **Verify Git Repository**: Make sure you're in a git repository with commits

    ```bash
    git status
    git log --oneline -10
    ```

3. **Check File Permissions**: Ensure you have write access to the changelog file
4. **Review Generated Content**: If the script creates a temp file but doesn't update the changelog, check the temp file for issues

### Alternative Update Methods

If the automated script doesn't work for your setup:

1. Use the manual helper script to get the update prompt
2. Copy the prompt and run it with your preferred LLM tool
3. Manually update the changelog following the established format

The goal is to maintain an accurate, helpful changelog that documents the project's evolution for both users and contributors.
