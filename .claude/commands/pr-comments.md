---
description: Fetch and display PR comments, reviews, and discussions
argument-hint: [pr-number-or-url]
---

# PR Comments

Below is all data for the pull request, fetched via a single GraphQL query.
It includes PR metadata, reviews, inline review threads (with resolved/outdated status),
conversation comments, and changed files.

!`./scripts/fetch-pr-comments.sh $ARGUMENTS 2>&1`

## Instructions

Present the PR data above to the user. Adapt your presentation based on context.

### Default presentation

1. **Overview** — PR title, state, author, base/head branches, review decision, draft status,
   size (+additions/−deletions, N files).
2. **Reviews** — Each reviewer's latest state (APPROVED, CHANGES_REQUESTED, COMMENTED, PENDING).
   Include the review body if non-empty.
3. **Inline review threads** — Group by file path. For each thread show:
   - File path and line number(s) as `path:line`
   - Status: Resolved, Unresolved, or Outdated
   - The conversation (author: comment body), keeping formatting concise
   - Prioritise unresolved threads — show them first
4. **Conversation comments** — Top-level discussion comments in chronological order.
5. **Action items** — Summarise what must happen before the PR can merge:
   - Unresolved review threads (file:line + one-line summary of the ask)
   - Reviewers who requested changes
   - Any other blockers visible in the data

### Contextual adaptation

- If the user is working on this branch, emphasise unresolved threads and action items.
- If the user asks about a specific file, filter to show only comments on that file.
- If the user asks about a specific reviewer, filter to that reviewer's comments.
- If asked for a summary, be brief — skip resolved threads and minor nits.
- If asked to help address a comment, read the relevant source file and suggest a fix.
- If the data contains an ERROR, report it clearly and suggest how to fix it
  (e.g. provide a PR number, check `gh auth status`).

### Follow-up capabilities

You can help the user with any of the following based on the fetched data:

- Filter comments by file, author, or resolution status
- Summarise all feedback from a specific reviewer
- List only unresolved or outdated items
- Draft replies to review comments
- Read source files and propose code fixes for feedback
- Compare feedback against the current code to check if concerns are already addressed
- Identify patterns across comments (e.g. recurring themes from reviewers)
