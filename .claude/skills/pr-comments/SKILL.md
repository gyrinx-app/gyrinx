---
description: |
  Fetch all PR comments, reviews, and review threads in a single GraphQL call.
  Use when you need to check PR feedback, address review comments, see review
  status, or understand what reviewers are asking for on a pull request.
user-invocable: false
---

# PR Comments

Fetch and display all comments, reviews, and review threads for a pull request.
Uses a single GraphQL query via `scripts/fetch-pr-comments.sh` in this skill's directory.

## Fetching the data

Run the script, passing an optional PR number or URL. If omitted, it detects the
PR from the current branch.

!`.claude/skills/pr-comments/scripts/fetch-pr-comments.sh $ARGUMENTS 2>&1`

## Presenting results

Adapt your presentation based on context.

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

### Truncation

The query fetches up to 100 review threads, 50 reviews, 100 comments, and 100 files.
Each connection includes `totalCount`. If `totalCount` exceeds the number of returned
`nodes`, warn the user that some data was not fetched.

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
