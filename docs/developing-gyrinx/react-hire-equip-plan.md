# React migration plan: Hire and Equip

Deliver Hire, gang-stash Equip and fighter Equip as complete tasks inside
Django pages. Preserve their existing choices, prices, permissions, confirmations,
figures and navigation. The [workflow anatomy](react-workflow-anatomy.md)
describes the established Django/React boundary; the [migration guide](react.md)
defines the parity and deferral rules.

## Delivery sequence

Each item is a focused PR, stacked when it depends on an unmerged prerequisite.
Preparation PRs retain the existing live task. A conversion switches its complete
task to one React owner. Required CI and actionable review findings must be
resolved on the final head before handoff. Merging and deployment require
separate authorisation.

### 1. Read-only model preview

Build an explicit JSON-safe projection of the model card already derived by
`n26/core/hire.py`. Reuse that derivation; do not calculate a second set of stats,
options or ratings in JavaScript. Add Cotton-derived React presentation and
realistic design-gallery examples. Its first production consumer is Hire's lazy
preview, introduced with the complete Hire conversion.

Cover every fact the current preview displays: identity and rating, statlines,
detail rows, skills and powers, gear and its groups, weapon profiles and traits,
choices, inline provenance and stat explanations. Check actual preview variants
before choosing the wire format. Hire previews have no stored model ID, so the
Cotton renderer omits Lore/Notes tabs. This step does not add a rich-text editor
or migrate owner-only card actions.

Evidence: Python projection tests using real preview builders; React behaviour
and safe-text tests; matched Cotton/React gallery examples at phone and desktop
widths in both themes; keyboard checks for any disclosure or explanatory control.
The display projection must not add database queries to an already built card.

### 2. Shared, retry-safe Hire workflow

Extract the workflow decisions in `core/views/hire.py` into a small owning Python
module. Keep HTTP parsing, URL generation, response formats, messages and
analytics in the adapters. Preserve offered-profile resolution, collection-entry
identity, staged visibility, option validation, quote and paid-price handling,
rating selection, current permissions and the onward result.

Add a durable command identity suited to all records a hire can create. Record
the actor, canonical business input and recoverable result in the same locked
transaction as the hire. Matching concurrent replays must return that result
without another fighter, assignment, ledger entry, charge or side effect.
Changed-input reuse must be refused. A failed transaction must leave no consumed
receipt. Keep command identity distinct from an operation's grouping batch.

Check current access first, then read the receipt before resolving current
offers or options. A catalogue change after a successful purchase must not
prevent its retry from confirming the saved result. Retain the introduced
assignment IDs so replay can derive any still-required onward choice screens without
recording navigation URLs in the command receipt.

Use the existing conventional form as the consumer. Prove unchanged successful
and refused outcomes before introducing another HTTP adapter. Cover free hires,
unlimited credits, grants, pets and onward choice/allowance screens where those
variants already occur. Avoid a generic service or API framework.

Evidence: existing Hire suites plus shared-workflow tests; simultaneous replay,
changed-payload, rollback and locked-access tests; independent ledger and gang
reconciliation; migration checks and fresh-database verification if schema changes.

### 3. Complete React Hire

Embed initial catalogue and figures as explicit display props. Add narrow JSON
preview and command adapters with their consumers, sharing the established
Python builders and workflow. Keep lazy previews lazy. Reuse existing search,
filter, range, dialog and form components; add catalogue presentation only for
the behaviour demonstrated by Hire.

One root owns the catalogue, option drafts, preview loading, name and price
confirmation, errors, notices and all figures changed by hiring. Preserve list,
section and confirmation URL state, including Back, Forward, reload and Cancel.
Keep ordinary navigation to the existing onward task. Remove the superseded
Alpine catalogue/dialog code from this workflow after checking other callers.
No nested island or externally swapped HTML may manage its children.

Evidence: HTML/JSON adapter parity on independent equivalent fixtures; real
selection and pricing variants; rejected and uncertain saves; offline, lost
successful response, reload and reauthentication recovery; stale preview-response
handling; correct URL history and onward destinations. Check query growth for
larger catalogues and avoid building all preview cards on initial page load.

### 4. Complete gang-stash Equip

Use the Hire catalogue work where the actual contracts agree. The gang-stash
workflow owns purchasing, held assignments and their existing actions, option
and price drafts, confirmations, wealth and Trade Point figures. Include every
stash/list variant and preserve list, section and expanded-assignment URL state.

Extract shared purchase and owned-action preparation before adding JSON
adapters. Give each write a durable retry contract appropriate to its effects.
Replace the workflow's htmx replacements with authoritative display data for its
React owner. Keep independent navigation and other complete tasks outside it.
Resolve the existing Equip collection-order work before changing its consumer.

Evidence: purchase, sell, refund, move, option and accessory variants as offered
by this workflow; confirmations; command replays; ledger reconciliation; updated
figures; no stale owned assignments after a write; query-growth and browser checks.

### 5. Complete fighter Equip

Migrate the fighter's whole equipment task, reusing the proven shared purchase
and catalogue paths. Include model-card changes, grants and accessories,
founding/personal allowances, open spending actions, overspend/rating
confirmations and updated credits and Trade Points. Recheck mutable allowance
and permission facts under the write lock.

The React root must own everything the existing `equip_update.html` response
updates for this task. Preserve all model/list variants and navigation. Remove
only obsolete callers and fragments; shared server-rendered consumers remain
until their own complete conversion.

Evidence: parity for every affected figure and card fact, allowance changes
between display and submit, concurrent/retried writes, refunds and grants,
all confirmation paths, command recovery, query growth and real browser use.

## Shared completion checks

- Record permitted users, initial defaults, input choices, writes, failures,
  confirmations and destinations before implementing each conversion.
- Run focused Python and React tests, typechecking, production build and the
  repository's formatting and static checks. Run broader suites where shared
  lifecycle, operations or render structures change.
- Test real local data in an isolated Chrome DevTools context at phone and
  desktop widths, in light and dark themes. Exercise keyboard/focus, history,
  loading, network/session failures and uncertain writes where applicable.
- Inspect database-backed views with the SQL toolbar and retain meaningful
  query-growth tests. Verify monetary effects independently of the response.
- Review all migrated microcopy and comments, including copied text. Preserve
  domain meaning and canonical Python-owned strings.
- Update the React skill and guidance in each PR with a concrete lesson. Keep
  feature rules in the feature; extend shared abstractions only when demonstrated
  callers establish the same behaviour.
- Attach useful visual evidence, remove the superseded implementation, update
  the Alpine baseline where applicable and state any deliberately retained caller.

## Coordination and scope

Coordinate changes to the UI export, Cotton recipe exporter, Hire view, domain
operations and shared templates with active work before pushing. Comment-only
PRs can be integrated without broadening this programme. Inspect current PRs
again before starting Equip, including the collection-order change.

Product or domain changes, N23, print layouts, a client-side router, broad CRUD
APIs and unrelated security or performance refactors are outside this plan.
Record a concrete dependency if it blocks parity; complete useful prerequisites
without substituting a partial live conversion.
