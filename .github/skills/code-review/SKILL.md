---
name: code-review
description: >
  Review Gyrinx pull requests using the repository's N23 and N26 conventions.
  Use during Copilot code review or when asked to review a diff for bugs,
  security issues, data integrity, query growth, or broken UI contracts.
---

# Gyrinx code review

Review the pull request diff and trace the affected behaviour through its callers, models, components, and tests. Read the root `AGENTS.md` and the nearest directory instructions for the changed files. Distinguish N23 from N26 before applying a rule; directory instructions take precedence over general guidance in skills.

## Load relevant guidance

Shared guidance lives in `.agents/skills/`. Read only the skills relevant to the diff, following their references when needed to assess the changed behaviour.

| Changed area | Guidance |
| --- | --- |
| Django views, forms, handlers, or domain models | [Gyrinx conventions](../../../.agents/skills/gyrinx-conventions/SKILL.md) |
| Templates, styling, or UI components | [Design system](../../../.agents/skills/design-system/SKILL.md) |
| N26 interactions or React islands | [N26 React](../../../.agents/skills/n26-react/SKILL.md) |
| Querysets, database-backed pages, or repeated template components | [SQL performance](../../../.agents/skills/sql-performance/SKILL.md) |
| User- or author-facing strings | [Microcopy](../../../.agents/skills/microcopy/SKILL.md) |

Use shared skills as review criteria. Their implementation workflows do not require a reviewer to start a dev server, provision a database, create accounts, or modify files. Run relevant existing checks when the review environment supports them; distinguish checks actually run from conclusions based on reading code.

## Verify findings

Before reporting a finding, inspect the definitions and call sites that could confirm or disprove it. For example, read a Cotton component's declared props before assessing its use, and trace server-side permissions and validation before judging a control's visibility. Check existing tests for intentional behaviour.

Prioritise concrete regressions in permissions, data integrity, transactions, idempotency, query growth, and rendered or interactive behaviour. Explain the trigger, the resulting failure, and the changed line responsible. Keep convention or copy findings specific to an applicable repository rule. Avoid unrelated cleanup, speculative abstractions, and findings already enforced by a passing static check unless the check misses this case.

Report findings against the reviewed head commit. If a proposed issue depends on an unverified assumption, verify it or clearly state the missing evidence rather than present it as a confirmed defect.
