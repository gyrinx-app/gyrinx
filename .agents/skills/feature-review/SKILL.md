---
name: feature-review
description: >
  Review a Gyrinx feature from the arbitrator or player's perspective, explain
  its purpose, and develop contextual UI copy and empty states. Use when a
  feature's meaning, entry point or next action is unclear, or the user asks
  for a feature review. For wording-only edits, use microcopy directly.
---

# Feature review

Establish what the person is trying to see or do before proposing labels or
layouts. Assume they know Necromunda but do not know how Gyrinx models it.

## Understand the task

Trace the entry point, destination and resulting action. Read the relevant
views, display structures, models and tests to check what the feature actually
supports. Inspect the rendered page when layout or interaction matters. Follow
the repository's edition-specific conventions.

Identify the actor: arbitrator, gang owner, participant, viewer or content
author. Explain their goal, when they would use the feature, what they need to
see, and what changes after acting. Distinguish configuration from using that
configuration, and definitions from actual campaign or gang records where
that distinction matters.

Check assumptions explicitly:

- Separate Necromunda concepts from Gyrinx terminology and implementation
  restrictions. A restriction in the code is not evidence of a game rule.
- Distinguish missing prerequisites, an empty collection, unavailable content
  and lack of permission. One generic empty state rarely explains them all.
- Verify what an action enables. Do not imply that configuring availability
  allocates assets, performs a roll or writes another result.
- Mark uncertainty and inference. Use examples supported by the feature;
  avoid inventing mechanics to make an explanation sound complete.

Start the explanation with the person's task and outcome. Introduce internal
terms only as needed to connect that task to Gyrinx. A description of database
relationships is supporting evidence, not the feature's purpose.

## Develop the copy and context

Load [microcopy](../microcopy/SKILL.md) before drafting product strings. For
layout or interaction proposals, also load
[design-system](../design-system/SKILL.md), and
[n26-react](../n26-react/SKILL.md) for N26 interactions.

Review the whole path: the section containing the entry point, its label,
the destination title and introduction, choices, empty states, next action
and feedback. A clearer destination cannot explain an isolated button on
the previous page.

Offer a small set of concrete alternatives when ideation is requested. Show
the actual labels and sentences together in their intended context, explain
the tradeoff, and recommend one. Use the specific domain noun when known;
keep general wording for features that genuinely cover several kinds.

An empty state should establish what belongs here and offer an attainable
next step. Explain a prerequisite where it is needed; avoid presenting an
action that immediately leads to a dead end. Put optional background in an
existing help pattern when useful. Keep instructions needed to proceed and
the next action visible.

## Revisit the feature at design checkpoints

For implementation work, use this review before choosing the layout, after
structural changes, and on the final rendered result. Keep each revisit
focused on what changed: task and prerequisites first; reading order and
disclosure next; a cold read of entry point, action and feedback last. Reuse
the established domain facts rather than repeating the full investigation.

For layout, whitespace, alignment and typography, run
[design-refinement](../design-refinement/SKILL.md). It adds browser inspection,
grid overlays, blockframing and a normal-resolution detail pass. A clearer
layout must still preserve information needed to decide and act. Recheck any
content moved behind disclosure from both the player and read-only roles
where relevant.

## Match the requested stage

If the user asks for an explanation, deliver that before UI ideas. If they
ask for options, develop options without treating the discussion as permission
to edit code. Once implementation is authorised, carry the chosen direction
through the relevant states and preserve existing permissions and behaviour.
Do not introduce additional approval steps for work already authorised.

Cold-read the result as a player encountering the feature for the first time.
They should be able to identify its purpose, why it is empty or unavailable,
and the next useful action. For implementation, follow the repository's
focused-test and visual-evidence requirements, including applicable mobile
and read-only states. Report any implementation restriction that still
prevents the proposed experience.
