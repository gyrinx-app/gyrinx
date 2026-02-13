---
name: pr-feedback
description: |
  Review PR feedback from reviewers and Copilot, triage each comment
  (implement / acknowledge / decline), plan changes, and implement approved
  fixes. Use when you need to act on pull request review feedback.
argument-hint: "[PR number or URL]"
disable-model-invocation: true
---

# PR Feedback

Reviewers (humans and/or Copilot) have left feedback on your pull request.
Your job is to review it, decide what is correct and worth implementing, and act on it.

## Phase 1: Fetch feedback

Run the pr-comments fetch script to get all PR comments, reviews, and review threads.

!`.claude/skills/pr-comments/scripts/fetch-pr-comments.sh $ARGUMENTS 2>&1`

## Phase 2: Triage

Go through every piece of feedback (review comments, inline threads, conversation comments)
and categorise each item into one of these buckets:

| Bucket | Criteria | Action |
|--------|----------|--------|
| **Implement** | Correct, improves the code, and in scope | Will fix |
| **Acknowledge** | Valid observation but out of scope or a deliberate choice | Note why — may reply to reviewer |
| **Decline** | Incorrect, based on a misunderstanding, or would make things worse | Note why — may reply to reviewer |

Present the triage as a table so the user can review your reasoning before you start work.

### Triage guidelines

- **Bug fixes and correctness issues** — almost always Implement.
- **Security concerns** — always Implement unless clearly a false positive.
- **Style nits** — Implement if they match project conventions (check CLAUDE.md / gyrinx-conventions),
  otherwise Acknowledge.
- **Suggestions to add features or scope** — usually Acknowledge (out of scope for this PR).
- **Copilot auto-review comments** — evaluate on merit like any other review. Copilot can be wrong;
  don't implement something just because a bot said it.
- **Conflicting feedback** — flag it and ask the user.

## Phase 3: Plan

For all items in the **Implement** bucket:

1. Create a todo list with one item per change
2. Group related changes that touch the same file
3. Note which feedback items are addressed by each change
4. Consider whether any changes require new tests

Present the plan to the user and wait for approval before proceeding.

## Phase 4: Implement

After user approval:

1. Work through the todo list, marking items as you go
2. For each change, read the relevant source file first
3. Follow project conventions (run `./scripts/fmt.sh` when done)
4. Run `pytest -n auto` to verify nothing is broken

## Phase 5: Summary

After implementation:

1. Summarise what was changed and why
2. List any feedback items you deliberately did not implement and the reason
3. Suggest replying to reviewers if appropriate (but do not post replies without asking)
