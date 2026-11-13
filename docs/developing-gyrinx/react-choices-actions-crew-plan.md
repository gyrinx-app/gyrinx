# React choices, action flows and crew selection

Migrate three complete workflows in two implementation streams. Keep the current
game rules, permitted actors, recorded results and visual layout. Leave PRs tested and ready for human review, with actionable review findings
resolved. Merge and deployment need separate
instructions.

This plan is for the technical lead and the agents implementing these workflows.
Use [the React guide](react.md) and [workflow anatomy](react-workflow-anatomy.md)
for the established Django, transport, recovery and Cotton adapter patterns.
Post-battle, Fighter Options and standalone Skills are complete in the previous
batch. Advancement selection remains a separate workflow.

## Workflow boundaries and PR order

| Stream | PR | Complete task |
| --- | --- | --- |
| A | Generic choices | Choose one or several results, add or remove picks, generate or enter a roll, dismiss or restore an offer, and continue through newly opened choices. Include the post-hire arrival screens and campaign-label dialog. |
| A | Action and advancement flows | Start, choose an outcome, choose augmentation or advancement, roll or enter results, choose a skill or power, review payment, apply, resume, cancel, reopen, mark as applied by hand, undo and correct. Include unavailable and on-hold states. |
| B | Choose crew | Select models and equipment sets, set starting crew or reinforcements, override availability where currently permitted, draw random models, save a draft and confirm the crew. |

Stream A handles choices first, then action flows in a separate PR. Stream B can
proceed independently. The integration owner coordinates shared UI recipes,
routes, exports and guidance. Keep each feature's tests and changes in its own
worktree. Stack PRs with `gh stack` when dependencies require it; combine both
streams locally before the final handoff.

The crew sheet and its print view stay linked, read-only destinations. Fighter
Edit, rich-text editing, image cropping, campaign scheduling and current roster
redesigns are outside this batch. Coordinate with their owners before changing
shared files. Do not introduce a client router or a general API framework.

## Shared server and command contracts

For each workflow, extract HTTP-independent preparation from its views into a
small owning module. Native POST and JSON adapters use the same current access
checks, validation, commands, outcome and feedback. Keep request-dependent
messages and analytics in the adapters. Emit analytics once per new action; keep
at most one queued confirmation per request key, including recovery after a lost
response.

Initial props and later reads use one explicit display builder. Include only
permitted, JSON-safe facts. Embed initial data in the page; do not fetch it again
after mount. JSON command results contain structured errors, an authoritative
display or a validated destination. Django continues to calculate prices,
ratings, available choices, random outcomes and domain effects.

A command identifies its actor, owning gang or battle, intent and exact business
input. Retain that input and its request key before sending. Store credentials
separately and use fresh CSRF on retry. Bind changed intent or input to a new
command; refuse reuse of an existing key with different input.

Recheck current authority under the existing write locks, then recall an earlier
result before resolving mutable offers, roster entries or catalogue records.
Serialise identical keys under those locks. Commit any generated randomness,
domain writes and success receipt in the same transaction. A failed transaction
leaves none of them committed. Replayed confirmations describe the historical
result when the current state may have changed; they must not imply a fresh write.

A retry recalls the original result even when a choice closes itself. It must
not create another roll, repeated pick, payment, assignment or crew draw.
Failed transactions leave no success receipt. When a refusal for a removed target resolves an uncertain command, store the
refusal durably. Delayed retries must return that refusal.
A generic validation or authentication refusal cannot settle an uncertain write.

New forms carry explicit keys. Cached native forms need a deterministic fallback
only where the actor, target, submitted revision and exact input distinguish the
original command. Do not generate a random replacement key while handling POST.
Test compatibility with the actual older payload, including absent and blank
fields, rather than only testing new keyed forms. Generic cached choice forms
have no revision or key that distinguishes identical intentional repeats. Reject
those unkeyed commands before writing and ask the reader to reload. Preserve a
readable account of the submitted choice; never guess whether it already ran.

## Generic choices

Extract the shared behaviour currently in `views/choose.py`; preserve helpers used
by card links, arrivals and campaign-asset boons. Keep their remaining callers
on that shared path or retain explicit forwarding imports during the cutover.
The operation layer deliberately permits some off-list assignments, so the
workflow must rebuild and validate the offered choice under the lock.

Preserve model, gang, holding and status-revision choice addresses, staged-content
visibility, capacity and repeat rules, optional None, current picks and separate
add/remove ratings. Hold campaign locks in their existing order before the gang
lock. Preserve dismissal eligibility, restoration of vanished keys, and the rule
that dead models have no dismissal controls.

Use `ModelChoiceReceipt` with a distinct versioned computed-choice payload.
Include choose/remove/roll/enter/dismiss/restore intent, exact choice address,
selection, roll identity, entered total and validated navigation context. Keep
existing Options and Skills payloads readable. Retain enough result facts and
written identities to reproduce feedback and onward choices without interpreting
today's catalogue as the historical result.

One React root owns each task page, including the arrival sequence. The campaign
label dialog uses the same workflow behaviour and display contract; replace its
htmx-owned dialog contents and update its caller explicitly. The external
htmx caller may insert or remove the independent React host through the existing
runtime lifecycle. React exclusively owns the dialog children. Preserve the
gang-sheet backdrop, dismissal and focus; do not swap HTML into the React root. Preserve normal return links and all arrival rules:
single picks continue onward, multiple picks stay open while appropriate, and
lasting-effect results return to the affected model's Edit page.

Keep selected roll IDs in the URL. Generating or entering a roll is an explicit
command; GET never rolls. Render stored faces, totals, thresholds, spent state
and the existing Add or Roll again actions from server facts.

## Action and advancement flows

Extract transport-independent workflow preparation from `views/action_flows.py`
and `views/advancement_flows.py`. Reuse `action_records`, `advancements`, existing
forms, signed reviews and operation commands. Preserve earned allowances,
thresholds, available outcomes, promotions and their decline path, manual and
random skills or powers, carried rolls, retained correction payments and rolls,
undo consequences, and by-hand results that change no model data.

Keep a distinct URL for each existing step and form variant. Direct entry,
refresh, Back/Forward and resume must recover the correct server stage and retain
unsaved input where appropriate. Do not replace those URLs with a local step
counter. Navigation to another task remains an ordinary link.

Existing start and roll keys do not bind every submitted field. Add a versioned
action-flow command receipt around the shared workflow so a changed entered roll
or stage intent cannot reuse an earlier key. Recall recorded results before
revalidating a now-closed offer. Preserve existing signed review and undo
snapshots; an outdated review requires explicit review of current facts.

Move the existing advancement-roll presentation into the new workflow as a
component. Retire its independent entry only after checking both current template
callers and gallery or test callers. The full action page owns progress, choices,
rolls, payment, confirmation, errors and result; never nest its old island entry.

## Crew selection

Reuse `CrewForm` and `save_crew`. Preserve their campaign, gang, battle and crew
lock order, current participant and owner/arbitrator checks, archive rules and
revision comparison. Keep availability notes and explicit permitted overrides.
Preserve selected equipment snapshots, ratings, missing equipment warnings,
vehicle labels and pets that accompany their owner without counting as another
crew member. Do not widen the rules governing selectable models or equipment.

Add `CrewCommandReceipt`, scoped by gang and request key and bound to the actor,
battle and exact raw input. Keep its versioned original result: revision,
confirmation, draw number, recorded draw and selection facts. Compare only business input: exclude credentials, CSRF, the separately stored
request key and presentation-only summaries. Preserve absent, blank, unchecked
and repeated business values deliberately, including fields for removed models.
A newer current draft must not be presented as the old command's historical draw. Replay acknowledges the immutable original draw without saving it again. Return
the current revision separately. Replacing a newer draft requires explicit review
and a new command. Apply the same separation to historical choices and their
current onward destinations.

The complete React root includes draw inputs and all save actions. Keep every
selection submitted when search hides its control. Preserve the clicked action
as an explicit scalar before constructing FormData. Keep role, equipment set and
override values distinct, including unchecked overrides and missing cards.

The form controller already retains the entire uncertain request body. Treat
roster-specific fields as optional recovery fields so newly added models do not
invalidate an older retained command. Keep a readable submitted-selection snapshot
for removed models. Retry the original fields and key with fresh credentials;
do not reconstruct the command from the current roster. Prove added and removed
roster recovery before considering any shared-controller change.

Draft and draw may navigate back to the complete editor after confirmed success;
Save crew continues to the existing crew sheet. Confirming or redrawing is a new
intent. Retrying an uncertain draw confirms its recorded models and equipment.

## Verification and completion

Build equivalent independent fixtures for native and JSON commands. Compare
allowed actions, validation meaning, written records, ledger events, credits,
ratings, crew revision and draw facts, messages and destinations. Preserve the existing sandbox tests that follow rulebook scenarios. Add meaningful concurrency tests with
committed fixtures that other connections can see.

For choices, cover repeatable and full multi-picks, optional None, holding and
status revisions, dismissed or removed carriers, staged options, generated and
entered rolls, dependent arrivals and campaign-label dialogs. For action flows,
cover each stage, costs and allowances, promotion decline, manual and random
skills or powers, stale signed review, correction, undo and exact roll replay.
For crew, compare members, role and card source, equipment IDs, ratings,
revision, confirmation, draw number and last draw. Check stale tabs, empty first
drafts, removed cards/models, archived battles and changed authority.

Exercise lost responses before and after commit, concurrent identical requests,
changed-payload key reuse, reload, reauthentication and rejected retries. Confirm
readable retained input, exact command replay, no repeated randomness and no
write after a refusal. Reconcile gangs after monetary scenarios.

Run focused Python and React tests, TypeScript, production build, formatter,
static checks and migration checks. Inspect representative SQL and payload size;
query counts must remain bounded as models, picks and equipment grow. Test the
combined final tree, including generated migrations, against current main and a
fresh database. Preserve other branches' migration leaves.

Use real Chrome at phone and desktop widths in both themes. Match native data,
viewport and crop for comparisons. Check compact ghost buttons, menu and card
content, URL history, keyboard/focus, zero and blank values, fixed action docks
and single message delivery. Hold responses to inspect button loaders and
control geometry; keep previews visible and avoid transient loading paragraphs.
Attach useful screenshots and short interaction recordings to each feature PR.

Review migrated copy and comments, including copied text. Keep shared product
strings in Python where both adapters use them. Each feature PR records one
verified improvement to the skill or guide. Remove obsolete templates, scripts
and entries only after searching all callers, and update the recorded Alpine usage counts with
`scripts/check_n26_alpine.py --update` when Alpine code is removed.

Finish with current-head required CI green, actionable introduced review findings
resolved, a readable PR dependency chain and one-click local test URLs. Report
real blockers rather than bypassing checks or changing unrelated code.
