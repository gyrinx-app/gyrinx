---
description: |
  Generate a structured technical explanation of the current branch's work.
  Useful for PR descriptions, handoff notes, or getting your bearings on a branch.
user-invocable: true
---

# Explainer

Generate a structured overview of the work on the current branch. Use git state, code changes, and your
understanding of the codebase to produce a clear explanation.

## Output format

Cover these sections:

1. **What was the problem** — What issue or need motivated this work? Be specific about the user-facing or
   developer-facing impact.

2. **Why was it complex** — What made this non-trivial? What constraints, trade-offs, or subtleties existed?
   Skip this section if the work was straightforward.

3. **What were the options** — What approaches were considered? Brief description of each with key trade-offs.
   Skip this section if there was only one obvious approach.

4. **How was it solved** — What approach was taken and why? Walk through the key decisions and the shape of the
   implementation. Reference commits if there are multiple.

5. **Critical code to understand** — List the 3-7 most important code locations (file:line or file:function) with
   a one-sentence explanation of what each does and why it matters. These are the places a reviewer or future
   developer should read first.

## Guidelines

- Be concrete — reference specific files, functions, and line numbers
- Explain the "why" not just the "what"
- Keep each section focused — if a section would be empty or trivial, skip it
- Use the git log and diff to ground your explanation in what actually changed
- Assume the reader is a competent developer who knows the codebase but not this specific change
