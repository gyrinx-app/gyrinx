#!/bin/bash
# Script to update CHANGELOG.md using Claude Code

set -e

# Check for arguments
if [ $# -eq 0 ]; then
    CHANGELOG_FILE="CHANGELOG.md"
else
    CHANGELOG_FILE="$1"
fi

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Updating $CHANGELOG_FILE with recent commits...${NC}"

# Check if changelog file exists
if [ ! -f "$CHANGELOG_FILE" ]; then
    echo -e "${YELLOW}Changelog file not found: $CHANGELOG_FILE${NC}"
    echo "Creating new changelog file..."
    SINCE_DATE="2 weeks ago"
else
    # Find the last date in the changelog
    LAST_DATE=$(grep -E "^### [0-9]{4}-[0-9]{2}-[0-9]{2}" "$CHANGELOG_FILE" | head -1 | sed 's/### //')

    if [ -z "$LAST_DATE" ]; then
        echo -e "${YELLOW}No date found in $CHANGELOG_FILE. Using 2 weeks ago as default.${NC}"
        SINCE_DATE="2 weeks ago"
    else
        echo -e "${GREEN}Last changelog date: $LAST_DATE${NC}"
        # Add one day to the last date to avoid duplicates
        # Use different date command syntax for macOS vs Linux
        if [[ "$OSTYPE" == "darwin"* ]]; then
            SINCE_DATE=$(date -j -v+1d -f "%Y-%m-%d" "$LAST_DATE" "+%Y-%m-%d")
        else
            SINCE_DATE=$(date -d "$LAST_DATE + 1 day" '+%Y-%m-%d')
        fi
    fi
fi

# Check if there are any new commits
NEW_COMMITS=$(git log --since="$SINCE_DATE" --oneline 2>/dev/null | wc -l)

if [ "$NEW_COMMITS" -eq 0 ]; then
    echo -e "${YELLOW}No new commits found since $SINCE_DATE${NC}"
    exit 0
fi

echo -e "${GREEN}Found $NEW_COMMITS new commits since $SINCE_DATE${NC}"

# Get recent commits for context
echo -e "${GREEN}Gathering recent commits...${NC}"
RECENT_COMMITS=$(git log --since="$SINCE_DATE" --date=format:"%Y-%m-%d" --pretty=format:"%ad %h %s" | sort -r)

# Read the current changelog
CURRENT_CHANGELOG=$(cat "$CHANGELOG_FILE")

# Call LLM to generate the updated changelog
echo -e "${GREEN}Calling LLM to generate updated changelog...${NC}"

# Create the prompt for LLM
PROMPT="Please analyze these git commits and generate the COMPLETE updated changelog content.

Current changelog file content:
---
$CURRENT_CHANGELOG
---

Recent commits since $SINCE_DATE:
$RECENT_COMMITS

Instructions:
1. Output the ENTIRE updated changelog file content (not just the new entries)
2. Group new commits by date (newest first)
3. For each date, categorize changes as:
   - Features (feat: commits)
   - Fixes (fix: commits)
   - Documentation (docs: commits)
   - Dependencies (dependency updates)
   - UI/UX (UI improvements)
   - Other (anything else significant)
4. Add new entries at the top of the 'Recent Changes' section (right after the ## Recent Changes heading)
5. Maintain the existing format and style exactly
6. Update the 'Last updated' date at the bottom to today's date
7. Only include days that have commits
8. Use the PR numbers from commit messages when available (e.g., #256)
9. Write clear, concise descriptions for each change
10. Do not include any explanatory text, just output the updated changelog content

Important: Insert new entries right after the '## Recent Changes' heading, before any existing date entries."

# Create temporary file for the updated changelog
TEMP_FILE=$(mktemp)

# Call llm and save to temp file
echo "$PROMPT" | llm -m claude-3.5-sonnet > "$TEMP_FILE"

# Check if the output looks like a valid changelog
if grep -q "# " "$TEMP_FILE" && grep -q "## Recent Changes" "$TEMP_FILE"; then
    # Backup the original
    cp "$CHANGELOG_FILE" "$CHANGELOG_FILE.bak"

    # Replace with the new content
    mv "$TEMP_FILE" "$CHANGELOG_FILE"

    echo -e "${GREEN}Changelog updated successfully!${NC}"
    echo -e "${YELLOW}Original backed up to $CHANGELOG_FILE.bak${NC}"
else
    echo -e "${RED}Error: Generated content doesn't look like a valid changelog.${NC}"
    echo -e "${YELLOW}Output saved to: $TEMP_FILE${NC}"
    echo -e "${YELLOW}Please review and update manually.${NC}"
    exit 1
fi
