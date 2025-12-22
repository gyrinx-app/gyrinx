---
description: Create a GitHub issue from an analysis file, with the full analysis uploaded to a gist
argument-hint: <path-to-analysis-file>
---

# Gist + Issue Creator

You are helping create a GitHub issue from an analysis or research document. The workflow is:

1. Read and understand the analysis file
2. Extract the top recommendations
3. Ask the user for feedback on which recommendations to prioritize
4. Create a secret gist with the full analysis
5. Create a GitHub issue with a summary, linking to the gist

## Step 1: Read the Analysis File

The analysis file path is: $1

If no path is provided, look for the most recently modified `.md` file in `.claude/notes/`:

!`ls -t .claude/notes/*.md 2>/dev/null | head -1`

Read the analysis file to understand its contents.

## Step 2: Extract Recommendations

After reading the file, identify:

1. **Quick wins** - Low effort, high value improvements
2. **High-value improvements** - More effort but significant impact
3. **Other recommendations** - Nice to have items

Create a mental list of the top 3-5 actionable recommendations.

## Step 3: Get User Feedback

**IMPORTANT**: Before creating the issue, you MUST use the AskUserQuestion tool to get feedback.

Ask the user which recommendations they want to prioritize in the issue. Present the top recommendations as options and let them select which ones to highlight.

Example question structure:
- Header: "Priorities"
- Question: "Which recommendations should be highlighted in the issue?"
- Options: The top 3-4 recommendations extracted from the analysis
- multiSelect: true (allow multiple selections)

Wait for the user's response before proceeding.

## Step 4: Create the Gist

Create a secret gist with the full analysis file:

```bash
gh gist create <filepath> --desc "<Brief description of the analysis>"
```

Capture the gist URL from the output.

## Step 5: Create the Issue

Create a GitHub issue with:

1. **Title**: A clear, actionable title (e.g., "Improve X integration", "Address Y findings")

2. **Body structure**:
   - Summary section explaining what the analysis covers
   - Link to the full analysis gist
   - Current State section with key metrics (if available)
   - Prioritized Recommendations section (based on user feedback from Step 3)
   - Quick Wins section
   - Files to Create/Modify section (if applicable)
   - Effort estimate (if available)

Use this command:

```bash
gh issue create --title "<title>" --body "<body>"
```

Use a heredoc for the body to preserve formatting:

```bash
gh issue create --title "Title here" --body "$(cat <<'EOF'
## Summary

<Brief description>

**Full analysis:** <gist-url>

## Prioritized Recommendations

<Based on user selections from Step 3>

## Quick Wins

<List quick wins>

## Additional Recommendations

<Other items from the analysis>
EOF
)"
```

## Step 6: Report Results

After creating both the gist and issue, report:

- The gist URL
- The issue URL
- A brief summary of what was created

## Error Handling

- If `gh` is not authenticated, instruct the user to run `gh auth login`
- If the analysis file doesn't exist, ask the user for the correct path
- If gist creation fails, report the error and don't proceed to issue creation

## Example Output

```
Done:
- Gist: https://gist.github.com/user/abc123
- Issue: https://github.com/org/repo/issues/123

Created issue "Improve Claude Code integration" with 4 prioritized recommendations.
```
