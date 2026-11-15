---
name: design-refinement
description: >
  Inspect and refine a rendered Gyrinx UI before handoff: composition, wasted
  space, alignment grids, typography, progressive disclosure and fine detail.
  Use after a substantial UI implementation or when a design feels unfinished.
  Includes browser measurement and monochrome blockframing tools.
---

# Design refinement

A working page still needs a design pass. Review the rendered result, make
specific corrections within the authorised scope, then inspect it again.
Load [design-system](../design-system/SKILL.md) for the edition's primitives
and [microcopy](../microcopy/SKILL.md) for product text. Use
[feature-review](../feature-review/SKILL.md) when purpose or flow is uncertain.

## Set the intended reading order

State the actor, immediate task, primary information and next action in a few
sentences. Identify what should be noticed first, second and third, and what
can wait. Establish this before interpreting a blockframe: the tool cannot
infer importance from rectangles. Preserve the task and domain behaviour.

Open the real page with representative local data. Record viewport, zoom,
theme, state and role; capture a baseline. Use the worktree preview and local
agent login from [dev-server](../dev-server/SKILL.md). Check a phone and a wide
viewport at actual size, including the page shell and a scrolled section. Review the surrounding
header, navigation, filters and explanatory copy as carefully as the feature
content; they consume the same attention and viewport space.
For a small change, scope this pass to its surrounding section and affected
states. Do not expand into unrelated screens.

## Review in three passes

### 1. Structure and visual weight

Look at the actual page first, then use the two-scale blockframe and grid
procedure in [browser-inspection.md](references/browser-inspection.md).

- Compare observed visual prominence with intended reading order. Is the
  workspace subordinate to introductory chrome, metadata or toolbars?
- Identify wasted space by its consequence: repeated padding hides useful
  entries, an empty column separates related facts, or a tall header pushes
  the first decision below the viewport. Record the region and measurement.
  Keep space that separates tasks, supports reading or protects touch targets.
- Inspect common left/right edges, column tracks, repeated row starts and
  vertical spacing. Derive the rhythm from existing tokens and primitives.
  Use browser grid/flex overlays and the helper's measured anchors; do not
  guess alignment from a screenshot or force every glyph onto a square grid.
- Distinguish within-group spacing from between-group spacing. A heading
  should read with its own content. Similar tasks should share anchors and
  rhythm; unrelated tasks need not have equal-sized cards.
- If structure is wrong, sketch two materially different arrangements before
  polishing margins. For a local defect, make the local correction directly.

### 2. Meaning and disclosure

Run a task-focused [feature-review](../feature-review/SKILL.md): entry point,
choice, action, result. Read the words in context, including the preceding
section and the state reached after acting.

- Keep the information needed to decide and act visible. Put occasional
  explanation and rare controls behind a clearly named existing disclosure
  pattern. Do not hide prerequisites, validation, current status, prices or
  consequences needed for the decision, or frequently compared facts.
- Make primary, secondary and destructive actions recognisably different.
  Repeated rows may each have a primary action; avoid several competing page
  actions. Use existing action bars, button groups and menus where appropriate.
- Remove redundant headings, labels and instructions. Replace vague actions,
  unexplained internal terms and generic empty states with task-specific copy.
- Check discoverability, keyboard access, open state, focus and dismissal for
  any disclosure changed. Follow N26 React conventions for interactions.

### 3. Detail at normal resolution

Walk top to bottom and through a representative interaction. Inspect actual
computed styles for anomalies rather than assuming a utility class won.

- Audit heading levels, size, weight and line height. A label, value, heading
  and secondary fact should have intentional roles. Find isolated bold text,
  oversized counts, tiny essential facts, inconsistent muted text and accidental
  inherited weights. Keep essential text readable; density is not smaller type.
- Compare siblings: padding, icon size and baseline, button height, border,
  radius, separator, wrapping and truncation. Look for a local recipe that
  should use a shared primitive, and inspect its real component API.
- Test long names, empty and dense content, error/read-only states and mobile
  wrapping where affected. Ensure alignment survives content changes and that
  disclosure has not made a common task harder.

Use the [review rubric](references/review-rubric.md) for deeper diagnosis and
`/n26/design/refinement/` for paired examples. Examples demonstrate decisions;
they are not universal layouts or permission to copy the deliberate defects.

## Fix, recheck and finish

Prioritise task/comprehension blockers, then structural waste, then local
inconsistencies. Fix coherent groups of issues and rerender after each group.
After structural changes, repeat the relevant feature review with real copy;
a tidy blockframe does not prove the feature is understandable.

Finish when the task and next action are clear, the relevant alignment and
spacing have been inspected, material findings are fixed or explicitly
constrained, and affected states survive the final normal-resolution pass.
Do not keep generating cosmetic churn. A compact handoff names corrections,
remaining constraints, inspected states and matching visual evidence. Do not
claim usability has been proven without observing people use the feature.

## Independent reviewer

When delegation is available and appropriate, give a reviewer the page URL,
local login, actor/task, affected states, these instructions and a bounded
scope. Ask for read-only diagnosis first. Do not supply your expected findings.
Require a short prioritised list, each with:

- Exact region/selector, viewport and state.
- Observed defect and its effect on the task.
- Measurement or capture supporting it; interpretation marked separately.
- Concrete correction using a named existing component/token where possible.
- What must remain visible or usable after the change.

The implementing agent checks domain assumptions, applies justified findings
and performs the final pass. The reviewer may find no material issue. Never
invent findings to satisfy a quota or use a numerical aesthetic score as a gate.
