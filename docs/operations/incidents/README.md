# Incident Reports

Write-ups of production incidents: what broke, why, and what changed as a result.
They exist so the next person to meet a similar failure starts with what we
learned rather than from scratch.

## What belongs here

- The failure mechanism, in enough detail to recognise it again.
- Reasoning behind the fixes, especially where an obvious-looking option was
  rejected.
- Diagnostic steps that turned out to matter, including the misleading ones.

## What does not

**This repository is public.** A good incident report describes how a system
failed; it must not double as instructions for making it fail again. So these
write-ups deliberately leave out:

- Specific thresholds, limits and capacity figures.
- The exact composition of allow and deny lists.
- Any description of how a control could be circumvented.
- Current weaknesses and where cover is thin.

That detail is real and worth recording — it lives in the private runbook and in
the cloud console, not here. When a report needs to refer to it, it says so and
stops.

If you are writing one of these, the test is: *could a reader use this to hurt
us more efficiently than they could without it?* If yes, generalise until the
answer is no. The mechanism is the lesson; the numbers are not.

## Reports

- [Crawler overload — 6 August 2026](2026-08-06-crawler-overload.md)
