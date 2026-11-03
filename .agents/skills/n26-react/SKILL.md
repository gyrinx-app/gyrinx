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
