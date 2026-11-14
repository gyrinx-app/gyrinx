---
name: n26-react
description: Build or migrate interactive N26 UI using React within Django pages. Use for controls, forms, filters, pickers, dialogs, complete workflow page bodies and their display and command endpoints. Static Cotton markup and N23 alone do not require React.
---

# N26 React islands

Use React for new N26 interactions. When changing an existing interactive task,
assess its complete workflow: reads, commands, confirmations, failures and
navigation. Migrate that workflow when the required extraction, endpoints,
components and parity checks fit the task. Task-specific APIs are part of a
migration, not a reason to reject it. Keep small islands for independent controls.
Static content stays Cotton; do not introduce Alpine directives or new uses of
kit components that carry Alpine, such as `<c-ui.dropdown>`, `<c-ui.tooltip>`
and `<c-ui.tabs>`.

Read `docs/developing-gyrinx/react.md` for the workflow plan, deferral criteria and
technical decisions. Read `n26/frontend/AGENTS.md` for the source hierarchy.
Load the design-system and
microcopy skills for UI work. N26 uses Tailwind tokens, not N23's Bootstrap
styles.

## Select and prepare the workflow

- Report whether the touched workflow is already React, migrated by this change,
  or deferred with a concrete blocker. Do not ask the user to choose a framework
  when the documented default applies.
- Before adding JSON endpoints, inspect all existing entry points. Extract
  shared access, validation, selection resolution, quote calculation and command
  behaviour as needed. HTML and JSON adapters must call that shared path,
  including locked permission checks, domain effects and the result used for
  feedback and analytics. Calling
  the same low-level operation alone does not prove parity.
- Protect existing behaviour with shared tests and adapter tests using equivalent
  independent fixtures. Compare allowed actions, errors, writes, ledger events,
  totals and destinations. Test deliberate response differences separately.
- Keep one React owner for the migrated task, including confirmations and
  mutable figures. Use ordinary navigation to other workflows and keep shared
  chrome independent. Do not add migration bridges as the default alternative
  to a complete workflow boundary.
- Defer migration for changes limited to copy, static content or backend
  behaviour, urgent fixes, overlapping work, unresolved product or domain
  decisions, or unavailable primitives or parity checks. Finish the authorised
  change and name the exact dependency and smallest verifiable preparation step.
  In a dedicated migration task, implement a useful prerequisite when it fits
  the scope. Do not remove
  behaviour or widen into N23 or print work to complete a migration.

## Implementation shape

- Prepare JSON-safe display props in the Django view: strings for ULIDs, lists,
  numbers and booleans. Do not expose ORM objects or fetch the same initial data
  again in the browser. Pass only data this user may see.
- Mount with `{% load react %}` and
  `{% react_island "authoring-list" authoring_list %}`. This tag safely embeds
  JSON, preloads the entry and shared runtime, and installs the lifecycle loader.
  Never use `|safe`, an inline JS object, or `dangerouslySetInnerHTML` for props.
  The host sets `data-react-name` to that island name. `data-react-module` is
  the hashed asset URL. Select `[data-react-name="authoring-list"]` in Django
  tests and Playwright, then read JSON from the element named by
  `data-react-props`.
- Co-locate a component, its tests and a small `mount(element, props)` export in
  `n26/frontend/islands/<name>/`. Copy the existing authoring-list shape; use
  the shared `runtime/mount` helper and return its disposal function. Vite
  discovers `entry.tsx` in each island automatically. No router, hydration, SSR
  or client cache framework is needed for an island.
- Use `n26/frontend/ui/` primitives. For a missing variant, extend the
  build-time recipes in `tooling/export_cotton_recipes.py` from the actual
  Cotton primitive and add a typed adapter. Do not fork its class strings or
  render `<c-…>` tags in JSX.
  Behaviour and accessibility need a React implementation; Alpine markup cannot
  be reused as an interactive primitive. Use the common app stylesheet, not
  island CSS imports (the template loader does not load CSS chunks).
- A component's slot content (nested controls, a figure in a named slot)
  becomes typed props built in Python when it moves to React; the island draws
  it and Cotton draws any fallback from the same props. Never move server-drawn
  nodes into React or keep the old version for the hard variant. Keep the
  behaviour; if content cannot be data yet, ask before changing it. See
  `docs/developing-gyrinx/react.md`.
- React exclusively owns the host's children. No nested island, Alpine binding,
  htmx swap or externally moved DOM inside it. Keep htmx outside islands and use
  the provided cleanup lifecycle for an island inside an htmx-swapped region.
  The loader also mounts a host that enters the page later, such as inside an
  Alpine `x-if`, and unmounts it when that node leaves.
- Use native links and forms when they suffice. For asynchronous server work,
  add narrowly scoped display and command views with the consumer. Reuse the same
  display builder for initial props and later reads. Keep authentication,
  permissions, CSRF, validation and transactions on the shared server path.
  Return structured errors and authoritative display data or a validated next
  URL. Handle session/network failure and uncertain writes; client pending
  state is not server idempotency. Do not add a generic CRUD API.
- Keep shareable navigation in the URL, including Back/Forward handling when
  changed without navigation. Keep temporary selection, loaded-row search,
  focus and unsaved drafts in React. Never trust client-submitted prices,
  permissions or calculated domain totals.

## Verify and finish

Review every user-facing string and comment in the migrated implementation,
including copied text. Use microcopy rules for product text and a plain-English
pass for comments. Preserve domain meaning, variables and useful invariants;
delete comments that repeat code or record agent/change history. Keep rewrites
within the workflow and changed shared code. Update canonical Python-owned
strings once for both transports. Report the review of copy and comments in the PR.

Run in the project environment (`.codex/run.sh` locally):

```bash
npm run build
npm run typecheck
npm run test:react
python scripts/check_n26_alpine.py --update
python scripts/check_microcopy.py --diff
```

Add Django tests for shared behaviour, props, permissions and endpoints; React
tests for forms, accessible controls, errors and recovery. Keep query-growth
tests when a data-backed region changes. Check phone and desktop widths, both
themes, keyboard use, focus behaviour and URL history. Check loading with and
without cached assets. Attach visual evidence using the pr-screenshots skill.
The bar already loads React on N26 pages; check that unrelated feature entries
do not load and the migrated root has no Alpine owner.

Compare matched data in the same rendering mode, viewport and theme. Inventory
each control's variant, size, padding, icon treatment and menu contents; sharing
the base button recipe alone does not preserve its call-site configuration.
Check open menus, destructive separators, long names, repeated accessories,
choice controls, counters and crowded headers. Use the paired model-card gallery
for stored cards and verify the real workflow too. Record concrete differences
and fixes in the PR; a functional smoke check does not establish visual parity.
Use `Tooltip` in its small Cotton style for short card facts and provenance.
Reserve a popover for structured explanations such as a rating breakdown. An
informational preview prompt becomes a ghost button only when a picker URL exists.
Check numeric zero targets as well as missing values. When the workflow draws
queued messages, empty the Django layout's messages block so each appears once.

Keep loading feedback in the initiating control. Use `Button`'s `busy` prop or
`BusyControlScope` with the shared `data-busy` styling; keep the label and control
dimensions stable. Reserve inline space for counter progress and price differences.
Keep an existing preview visible while its replacement loads. Avoid page-level
loading paragraphs and transient saving dialogs. Delay responses in the browser
and compare control and neighbour rectangles before and during reads, saves and
retries at phone and desktop widths. Confirm cancellation still reaches React
through the native busy guard.

Switch the complete workflow to one renderer per request. Do not mount both
renderers and hide one. Remove obsolete code after checking every caller; name
any short-lived rollback cleanup. Independent shared chrome can stay unchanged.

Lower the Alpine baseline with the command above. Each template has a `direct`
ceiling for Alpine written in it and a `kit` ceiling for Alpine that `<c-ui.*>`
components add. The check fails when either rises. `--update` raises a kit
ceiling only when a kit upgrade changed a component's weight: the check names
the change, you review it, then run `--update`. Delete superseded interaction
code after checking its other callers. Report the feature and migration outcomes,
including any concrete deferral reason.
These instructions do not authorise unrelated refactors, scheduled jobs,
deployment, automatic merges or access to another user's data.

## Command migration checks

Use Manage credits (`n26/core/credits.py` and the `manage-credits` island) as the
first complete form example. Its form-encoded command shares Django validation
with native POST, uses `http/command.ts`, and records a durable request key.
Choose the receipt from the workflow's actual effects; a ledger grouping batch
is not a unique command key. Test concurrent replay and changed-payload rejection.

For an uncertain write, keep the exact submitted payload and key and freeze
editing until a retry confirms its outcome. A rejected retry cannot prove an
earlier write failed. Protect navigation during pending saves as well as after
network failure. Test the real CSRF failure handler, which runs before the view,
and preserve success feedback without duplicating it on replay. Generic transport
tests in `.test.ts` are included by the shared Vitest configuration.

Prove reload and reauthentication recovery as well as an immediate retry. Persist
unresolved business input and its key before sending, scoped to actor and task;
restore that input with a fresh CSRF token. Never retain credentials or an old
CSRF token with the recovery payload. A reload instruction must not discard an
unresolved command's identity.
Test a lost response after the server commits, both before and after reload.
Assert that the frozen screen immediately shows the submitted names, choices,
roles and counts. Saving a readable snapshot in the request body does not update
React state by itself. Keep that snapshot synchronized before submission; retain
the exact raw command separately from its display labels.

A mutable crew refusal includes availability, even when a removed saved member
still has form fields. Classify status overrides, removed members and a shrunken
draw pool explicitly. Record a no-write receipt under the same locks before
letting an uncertain request become an editable draft; retain its role, card,
override and draw count until the player reviews and changes them.

Inventory older native form payloads before choosing a compatibility key. A
revision can distinguish a cached crew edit; an unkeyed repeatable pick or roll
cannot distinguish a retry from a new action. Reject ambiguous commands before
writing, retain readable intent and require reload. Never invent a fresh key in
POST or silently add one in a test fixture.

Round-trip actual GET display values through the command: give JSONField native
lists or dictionaries as initial values, because BoundField.value already encodes
them. Keep known unsent or rejected drafts scoped to their original URL task when
nested choice pages open, while unresolved submitted commands keep their exact
body and protect the actor's workflow across those URLs. Reconcile passive
selections against each question's saved starting state when returning from a
nested choice; keep unaffected siblings and transfer them into an expanded task
only after its confirmed continuation. Use fresh page metadata and command keys
for passive drafts, and retain displayed roll identifiers in recovery URLs.
Keep owning-action and allowance guards on result-writing branches under the
write locks, including generated and entered rolls, after receipt recall. Replay feedback
must describe an earlier save rather than assert current state. A same-task
dialog confirmation should refresh its existing owner with a fresh issued key;
keep presentation context optional and navigate normally for onward tasks.

Keep an earlier uncertain save frozen after any rejected retry, including a
structured form refusal. Opt workflow forms out of the shared busy-link handler
with `data-busy="off"`; the React `WorkflowPage` adapter does this by default.
Test Back after saving: a cached completed form must not submit a consumed key
as a new command. Manage credits prevents HTTP caching and refreshes completed
forms restored from the back-forward cache, while retaining unsaved drafts.
Read recovery storage again on persisted history restoration. A cached older
form can predate a later unresolved save for the same task; refresh it rather
than allowing it to replace that command's key or payload. Preserve an unsaved
draft only when no command needs recovery.

## Absolute edits

Use Edit campaign holding (`n26/core/asset_edit.py`, `edit-holding`) as the
absolute-edit example. Sign the subject, actor and starting state; compare current
values and revision under the same lock as the write. A matching desired state
is a no-op success; a stale different state returns a specific revision conflict
with current facts. Keep the draft frozen until an explicit review action loads
a fresh baseline. Never automatically overwrite a newer edit.

A retained submission takes precedence over native POST props. Ignore errors or
conflict metadata for another submission until retry resolves the retained one.
Test simultaneous drafts, delayed old requests, same-value retries, blank versus
zero, and reload recovery. Do not reuse a money-adjustment receipt for an absolute
edit merely because the forms look similar.

## Reuse the established form lifecycle

Manage credits, Edit holding and Edit asset type use `useWorkflowForm`, exported
from `ui`. Keep pending state, retained input, fresh CSRF, focus and navigation
handling there. Each island still validates and interprets its server response.
Never treat every 409 as a confirmed revision conflict: a credits key refusal
cannot resolve a lost adjustment response. Run all three forms' tests after a
shared lifecycle change.

For Edit asset type, the signed snapshot also contains whether ownership was
locked. Related assets or tables can change this constraint without updating the
type row. Validate a disabled field against its signed starting value, then
compare current state under the lock. Return current facts and require review
when a new constraint changes the submitted intent. Preserve Inherent and
Transferable, the displayed labels from the model.

Signed snapshots can outlive a deployment. Validate their shape as well as their
signature and return a form error for unsupported input. Keep retry formats
compatible with retained commands; a validation refusal cannot resolve an
earlier uncertain write.

## Catalogue preview preparation

For Hire and Equip, follow `docs/developing-gyrinx/react-hire-equip-plan.md`.
`core/model_preview.py` projects already built, unstored hire cards without
queries or domain calculations. `ui/ModelPreview` draws those facts with recipes
from the existing Cotton card. Import that component within the workflow root;
the `model-preview` island entry is for independent gallery use, not a nested
root inside Hire.

Preserve composed detail parts, choice prompts, provenance, stat explanations
and weapon profile grouping. Keep names in their inline text container: making
each name a separate flex child changes wrapping. A hire card has no stored
model ID, so its Cotton preview has no Lore/Notes tabs; do not add a rich-text
editor as a prerequisite for that consumer. Compare the real preview with its
delivered hire as well as checking gallery examples.

For acquisition retries, inspect the saved command before resolving mutable
catalogue data. `core/hire_workflow.py` binds a request key to the actor and
submitted business input, then recalls `HireReceipt` after checking current
access under the gang lock. A changed price, removed option or archived profile
must not prevent confirmation of an earlier committed hire. Failed transactions
must leave no receipt. Retain the written assignment IDs needed to rederive
onward choice screens; do not store an arbitrary client return URL as a result.
Keep native form keys required and stable across validation errors. Update real
POST payloads in tests explicitly, and separately prove missing-key rejection.

For Hire catalogue controls, submit library Option row IDs in `selection`, not
option positions or default-set IDs. Distinct options can share a default set;
reordering a catalogue must not change an unsaved choice. Preserve legacy receipt
payloads when adding a new input format. After a rolled-back operation, reload
and reauthorise the gang before projecting current figures.

Every retained scalar must be present in the submitted form. A controlled,
non-posting checkbox can use one hidden field containing either its value or an
empty string; an omitted unchecked field cannot restore a complete draft.
`useWorkflowForm.recoverAt` keeps an explicit recovery navigation's draft and
uses fresh page CSRF on return. Known rejections remain editable; a rejected retry
does not resolve an earlier uncertain save. Preserve the raw URLSearchParams
storage format so cached clients can still recover pending commands.

Preserve a native confirmation's populated payment. An untouched React form must
post the displayed amount, rather than blank input that may resolve to a higher
quote after a catalogue edit. Keep deliberate blank and zero payments distinct.
Preserve queued messages' severity and dismissal alongside their text.

Search the whole edition for workflow callers and tests before deleting a shared
helper. Page contracts also live in colocated `core/test_*.py` modules. Move
remaining consumers onto the shared parser rather than another view's private
helper, and preserve browser navigation hints alongside visible controls.

For Equip, a receipt can settle a confirmation question without writing a purchase.
Replay that question and its stored continuation key; use a distinct key for the
explicit confirmation. Otherwise a lost question can become an unreviewed write
after prices or allowances change. Recall receipts before resolving removed
possessions, and test every owned-item action as well as purchases.

Stable selection IDs alone do not preserve a payment. A pick-one default can move
part of the price between the base and the option surcharge. React Equip posts
the full displayed payment; native indexed forms retain their base-plus-surcharge
format. Test a reordered default with the same selection and payment. Carry the
root's current section and expanded entry into panel reads, rather than trusting
links generated before those controls changed.

For commands that refresh an existing root, interpret a confirmed terminal result
as `completed` and use `useWorkflowForm.onComplete`. Keep `onNavigate` available
for recovery navigation. Correlate fresh confirmation metadata with the retained
request before showing it: a restored command for one item must never use another
item's title, choices or consequences. Retain readable selection details alongside
unresolved input. Add non-business display fields through `optionalRecoveryFields`
so older pending commands still restore; request keys and business input remain
required. Test both rejected and uncertain recovery against an unrelated panel.

Keep catalogue purchase drafts above any filtering or section boundary that can
unmount an entry. Test edited base prices, stable choices and selected profile
payments after hiding and restoring that entry. A selected profile must display
its retained payment after a quote refresh. A follow-up confirmation without a
rating checkbox preserves the carried rating policy. Native keyed adapters must
also reach receipt replay before requiring a live assignment.

For fighter Equip, compose `ui/ModelCard` within the shared `equip` owner.
Project linked stored cards through `core/model_card_display.py`; keep previews
read-only. Preserve independent task links and native dismiss forms without
nesting forms: use `WorkflowLayout`, including `data-busy="off"`. Give repeated
card controls stable assignment/choice keys so a refresh cannot reuse another
item's menu state.

Counter steps must preserve the native sequential queue. Give each intentional
step a new key, retry the active step with its original key, and stop unsent
steps with an explicit notice after refusal or uncertainty. Do not make rapid
clicks disappear behind a pending modal. Test queue draining and interruption,
draft preservation, replay after removal, model scope and the separate campaign
arbitrator path. Distinguish receipt formats before reading result fields.

Inventory navigation flags as well as visible tabs. Equip carries `dismissed`
through display reads, commands, confirmations and onward control links. Test
such flags on native and JSON adapters; a complete renderer can still lose
navigation state if a retained scalar is missing. Add navigation-only fields as
optional recovery inputs so older unresolved commands still restore.

Keep navigation order separate from quote precedence. A reordered collection
rail must not change which held list prices Unrestricted purchases. Test an
item present in both the moved list and the Trading Post through both command
adapters. Inventory secondary submit actions too: fighter reassignment offers
both another model and the stash. The retained payload must match the clicked
destination before submission.

## Replacing model options

An absolute choice that changes payment needs a signed starting state as well as
an actor- and input-bound command receipt. The snapshot covers the recorded
selection, current option identities and prices, and recorded payment. A matching
desired selection can be a no-op, but that alone cannot confirm an earlier save
after another editor changes the selection again. Recall the receipt under locked
authorization before resolving today's catalogue or model. Retain the gang
identity so a confirmed command can return safely after its model is removed.
Use stable library Option identities and preserve one, any, and one-or-none modes.

Check composed layout variants as well as individual controls. ModelHeader keeps
the native model heading, card and tabs together; a general form layout's section
spacing changes those gaps. Card's header prop preserves Cotton's header divider
and default body padding. Independent card commands can stay native forms and
links, with no htmx inside the root. Compose them outside the workflow form so
counter and dismissal forms remain valid HTML.

## Selecting skills and powers

Build placed tiers, usability notes and known-content markers for display without
matching starting offers. Match the current Choose list only during a command;
Fighter Edit and the dedicated selection page share that lookup. Guard its query
growth independently of the number of held skills and models.

Recall the command receipt before checking known content or current offers. A
successful starting selection can close its own offer. An already-known refusal
without a matching receipt cannot confirm an earlier save.

Compare the complete native choice layout: tier caption, card detail slot, rating,
text truncation and collection tabs. Extend RadioCards, RadioCard and TabLinks
before adding feature markup. Keep collections in the URL and preserve existing small ghost actions. Put the
spinner inside the initiating button so loading preserves neighbouring controls.
A switcher search inside a workflow form must prevent Enter from submitting that
form even when no search result is active.

For removable models, stamp an owned recovery URL before sending the command so
reload and sign-in can restore the original retry. Ordinary unavailable-model
pages remain 404; explicit recovery checks current gang ownership and exposes no
editable replacement form. Record terminal no-write results under the gang lock
too. An absent receipt cannot settle uncertainty: a delayed original request
could arrive after the model is restored.

## Autosaved results editors

Keep the exact in-flight command and key, newer local edits, and the last
acknowledged server revision separate. A delayed response must not replace later
typing. Serialize draft mutations, and let Apply wait for acknowledgement of the
current draft and its authoritative review. Use refs for queue decisions so a
queued action does not use an earlier render's dirty state.

Receipt replay can confirm an older save while the report has a newer draft.
Confirm the earlier outcome, preserve local entries and require explicit review
of the newer draft. Do not keep a confirmed save uncertain or adopt a newer
revision as permission to overwrite. Validate and normalize the response before
clearing retained input; malformed display data must leave the original command
available for retry. Keep participation acknowledgement in the typed display
and field serializer, including explicit review of a newer draft.

Clear recovery storage after a clean acknowledgement. Unsent local entries must
retain their acknowledged generation and revision, even when no command is active.
On reload, a different server version or a missing legacy baseline requires
explicit review. Never attach an older local draft to fresh page versions and
silently autosave over another tab or a new correction generation.

Keep blank editor entry IDs stable across reloads, including an empty credits
list. Expose an applied report as read-only with receipt navigation; it cannot
be adopted as an editable draft. Freeze entries for the final Apply request,
while allowing later typing during autosave. NativeSelect multiple questions
must use Cotton's multiple-select recipe, including its size and option marks.

A cached native form can derive a stable command identity from its actor, report,
version and exact intent/input. Replay the stored canonical result for actions
that create random draft identities, such as adding a result. Preserve existing
Apply receipts as well as new command receipts. Opening a correction starts a
new generation; commands from the previous generation cannot modify it.

Match Input and NativeSelect controlSize to the Cotton call site's size. A shared
default recipe alone does not preserve a large control's dimensions. Keep
explicit progress in the initiating button; an autosave status can use a small
reserved position without moving nearby content.
