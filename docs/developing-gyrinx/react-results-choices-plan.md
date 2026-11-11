# React post-battle and model-choice migration plan

Deliver three complete React workflows in two parallel streams. Post-battle owns
one stream; Fighter Options, followed by skill selection, owns the other. Each
workflow must be independently reviewable and retain its current behaviour and
appearance. Leave verified PRs ready for human review. Do not merge or deploy.

The existing [React guide](react.md), [workflow anatomy](react-workflow-anatomy.md)
and [Hire and Equip plan](react-hire-equip-plan.md) remain the implementation
references. This plan builds on their command recovery, display and design
adapters rather than introducing a new frontend architecture.

## Scope and completion

Post-battle includes the complete results editor: mission credits and counters,
model participation and XP, results and dependent choices, final status,
equipment disposition, notes, autosave, explicit Save draft, Check changes,
Apply results and the correction editor. Preserve the required acknowledgement
that model participation has been checked and the read-only campaign territory
summary. Territory outcome changes stay on Edit battle. Preserve campaign and standalone
reports, owner and arbitrator access, vehicle and pet rules, and recorded-result
deltas. Report lists and immutable receipt pages remain normal linked pages.

Fighter Options includes current choices, every one, any, and one-or-none group,
charge or return of credits, authoritative figures and the stored model card.
Independent model actions remain links to their owning tasks. Preserve the
current Edit/Equip/Options navigation, card variants and empty state.

Skill selection includes available collections and placed tiers, choice display,
selecting one offered skill or power, matching an open starting-skill offer or making a standing
selection, existing-skill refusals, empty states and onward navigation. The
collection stays in the URL. This is not a conversion of every generic choice
screen or the rest of Fighter Edit.

No redesign, game-rule change, broad CRUD API, client-side router, N23 conversion,
rich-text editor replacement or production data change is part of this batch.
Gang-sheet and card redesign proposals are separate work.

## Ownership and parallel delivery

Use a dedicated durable worktree and branch for each independent stream. The
integration owner keeps the plan, shared guidance, shared React lifecycle,
transport, UI exports, Cotton recipe exporter and route integration coordinated.
The post-battle worker owns its feature modules, editor template, frontend root
and tests. The model-choice worker owns Options and Skills modules, templates,
roots and tests. Neither worker changes the other's files.

Agree on request, response and display types before parallel server/UI work.
If shared behaviour needs extending, identify the demonstrated consumers and
ship a small prerequisite or obtain an explicit ownership handoff. Do not make
concurrent speculative changes to useWorkflowForm, its storage format, UI
exports or the recipe exporter. Existing retained commands must remain usable.

The two streams need not wait for each other's feature PR. Skills follows
Options in the model-choice stream, but should depend on it in Git only when
there is a real code dependency. Keep each cutover complete and independently
reviewable. Update PR descriptions and evidence after integration or rebasing.

## First checkpoint: contracts and parity

Before changing a renderer, inventory every entry point and permitted actor,
input, default, choice source, confirmation, write, failure and destination.
Record applicable query parameters, money and rating figures, messages,
analytics and archived/staged content behaviour. Search edition-wide callers
before extracting or deleting shared helpers.

Build equivalent independent fixtures for native and JSON adapter scenarios.
Compare allowed actions, validation meaning, persisted effects, ledger events,
credits, ratings and destinations. Test intentional HTTP response differences
separately. Neither calling the same low-level operation nor rendering the same
base button recipe alone establishes parity.

Initial props and later reads use the same explicit JSON-safe display builder.
HTTP adapters call shared authorization, validation and command preparation;
player-data writes continue through operation(...). Keep request-specific
messages and analytics at the adapter, once per newly completed action.

## Stream A: post-battle editor

### A1. Shared display and command preparation

Inventory the current post_battle view, post_battle_forms projection,
post_battle domain services, templates, post-battle.js and the preview/toolbar
islands. Retain the existing gameplay calculations. Extract only workflow
orchestration that native and JSON adapters both need.

Expose explicit initial editor data, permitted controls, dynamic choice groups,
field errors, authoritative previews and navigation. Add narrowly scoped
commands for the existing intents; do not expose internal ORM or plan objects.
Keep unfinished text distinct from cleaned or applied values.

### A2. Draft and application recovery

Define and test the save protocol before building autosave. The report already
has a generation, draft revision and Apply submission key. Reuse those concepts
without assuming an incrementing revision alone confirms a lost save response.

Serialize draft mutations and preserve the exact in-flight payload and identity
until its outcome is known. Keep newer local edits separately; a delayed save
response must not replace them. Coalesce later autosaves only after resolving
the active save. Reject stale versions under the same lock as the write.

An uncertain response needs a server-verifiable replay or recovery contract.
Reload and sign-in must retain unresolved input without storing old CSRF tokens
or credentials. A conflict must show current facts and preserve the local draft
for explicit review; never silently overwrite or automatically merge game data.

Apply must first settle pending draft work, then submit the reviewed server
state with a stable submission identity. An outdated preview, failed save or
changed rule result cannot become an unreviewed application. Lost Apply responses
must replay the existing receipt. Opening a correction starts a new generation; its retries retain that
generation and submission identity. Commands from an older generation must not
modify the correction. Apply only the existing domain-calculated difference
from recorded results.

Test slow saves followed by more typing, multiple rapid intents, two tabs,
permission loss, stale offers, removed models, network failure before/after
commit, reload, reauthentication, repeated Apply and correction replay. Cover
participation acknowledgement after save/reload and refusal without it; cover
pending and applied territory summaries.

### A3. Complete React owner and cutover

One post-battle root composes mission results, model sections, toolbar, preview,
errors and footer actions. Compose React components directly; do not nest the
existing independent island entries. Inputs, dependent choices and derived
server displays must remain consistent after every accepted response.

Replace DOM queries, custom-event bridges and htmx section swaps within this
owner. Delete superseded scripts, fragments or entries only after searching all
callers. Preserve the existing editor layout, accessible labels, focus,
sticky controls, keyboard use and validation navigation.

For autosave, retain a compact reserved save-status position. Explicit actions
use their initiating button's spinner; do not add loading paragraphs that move
the page. Keep the last valid preview visible while refreshing it.

## Stream B: model choices

### B1. Fighter Options

Extract the current option offer, validation, authorization, rechoose operation
and result preparation into one shared workflow. Reuse the actual Hire/Equip
selection contracts where they agree, including stable identities rather than
mutable catalogue positions. Keep one, any, and one-or-none defaults and blank values exact.

Establish whether a keyed receipt, signed starting state or both are necessary
for an option replacement that can charge or return credits. Decide from the
existing operation's effects, then prove retries and stale-state behaviour with
independent fixtures. Do not reuse an acquisition receipt solely because the
controls look similar. Recheck current permissions and mutable facts under lock.

Render option groups, messages, current figures and the existing ModelCard in
one owner. Refresh authoritative state after success, without changing menu
contents, button variants or navigation. Preserve refusal input and resolve
uncertain saves across reload and sign-in.

### B2. Skill selection

Extract the current offer and selection command without breaking shared helpers
used by Fighter Edit or other choice workflows. Display and submit must apply
the same staged-content visibility, placement and known-content rules. Include
a placed power and preserve usability notes and no-charge selection.

Preserve the distinction between answering a matching open offer and creating
a standing selection. Validate the selection and recheck access/current state
under the operation lock. Determine replay behaviour from the actual assignment
effects. A retry, reload or sign-in after a lost successful response must
recover the original successful result and destination, including when selecting
settled a starting offer that is no longer open. Do not create another
assignment or emit duplicate analytics or success messages.

Replace the page body with one root, using existing choice primitives and
workflow transport. Keep collection navigation shareable, the return route
correct, and models with no available content usable. Test permission loss,
known/stale selections, changing collections, relevant grants and replay.

## Verification and review gates

Each migration needs focused Python parity, permission, concurrency and replay
tests, React state/error/recovery tests, typechecking and a production build.
Run the repository formatter, static checks and Alpine baseline update. Run
broader shared-controller tests when that code changes. End monetary scenarios
with independent ledger reconciliation.

Use realistic repeated data for query-growth checks. Record payload size and
representative read behaviour where a new display contract changes loading.
Initial props must avoid a second initial-data request. Do not calculate domain
consequences independently in the browser.

Exercise real isolated Chrome sessions at phone and desktop widths, in both
themes. Use matched data and viewports for visual comparisons. Check tab widths,
compact ghost controls, tooltips/help cursors, menus, wrapping, zero values,
error placement and single delivery of queued messages. Delay responses to
measure control and neighbour geometry; cover retry, cancellation, history and
keyboard/focus restoration. Tests do not replace useful attached UI evidence.

Review all migrated microcopy and comments, including unchanged copied text.
Preserve game terms and meaning. Update canonical Python-owned strings once for
both adapters. Each feature PR adds a concrete demonstrated lesson to the React
skill or guide; avoid generic instructions added without a real failure case.

Commit and push focused PRs. Resolve actionable in-scope review feedback and
require current-head CI to pass. Report unavailable human approval honestly.
The final handoff lists the three workflows, PR dependencies, evidence and
specific test URLs. Leave PRs ready for the user to review; do not merge.
