---
name: n26-react
description: Build or change interactive N26 frontend UI using React islands within Django pages. Use for N26 controls, forms, filters, pickers, dialogs, Alpine migration, and frontend component work. Static Cotton markup and N23 alone do not require React.
---

# N26 React islands

Use React for new N26 interactions. When editing existing behaviour, convert the
touched Alpine interaction if it has a bounded DOM owner, existing server
contracts and manageable tests. Do not sweep unrelated pages into the change.
If migration would require domain/API redesign or a complex shared primitive,
finish the requested task and name the dependency that blocked conversion.
Static content stays Cotton; do not introduce Alpine directives.

Read `docs/developing-gyrinx/react.md` for the technical decisions. Load the
design-system and microcopy skills for UI work. N26 uses Tailwind tokens, not
N23's Bootstrap styles.

## Implementation shape

- Prepare JSON-safe display props in the Django view: strings for ULIDs, lists,
  numbers and booleans. Do not expose ORM objects or fetch the same initial data
  again in the browser. Pass only data this user may see.
- Mount with `{% load react %}` and
  `{% react_island "authoring-list" authoring_list %}`. This tag safely embeds
  JSON, preloads the entry and shared runtime, and installs the lifecycle loader.
  Never use `|safe`, an inline JS object, or `dangerouslySetInnerHTML` for props.
- Put a component in `n26/frontend/` and a small `mount(element, props)` export
  in `n26/frontend/entries/<name>.tsx`. Copy the existing authoring-list entry;
  use the shared `mount` helper and return its disposal function. Entries are
  discovered by Vite automatically. No router, hydration, SSR or client cache
  framework is needed for an island.
- Use `n26/frontend/ui.tsx` primitives. For a missing variant, extend the
  build-time recipes in `export_ui.py` from the actual Cotton primitive and add
  a typed adapter. Do not fork its class strings or render `<c-…>` tags in JSX.
  Behaviour and accessibility need a React implementation; Alpine markup cannot
  be reused as an interactive primitive. Use the common app stylesheet, not
  island CSS imports (the template loader does not load CSS chunks).
- React exclusively owns the host's children. No nested island, Alpine binding,
  htmx swap or externally moved DOM inside it. Keep htmx outside islands and use
  the provided cleanup lifecycle for an island inside an htmx-swapped region.
- Use native links and forms when they suffice. For asynchronous server work,
  add a narrowly scoped JSON view calling the same server operation. Keep
  authentication, permissions, CSRF, validation and transactions on the server.
  Do not add a generic CRUD API merely to mount a component.
- Keep shareable navigation in the URL, including Back/Forward handling when
  changed without navigation. Keep temporary selection, loaded-row search,
  focus and unsaved drafts in React. Never trust client-submitted prices,
  permissions or calculated domain totals.

## Verify and finish

Run in the project environment (`.codex/run.sh` locally):

```bash
npm run build
npm run typecheck
npm run test:react
python scripts/check_n26_alpine.py --update
```

Add Django tests for props, permissions and any endpoint; React tests for
behaviour, accessible controls and error/empty states. Keep query-growth tests
when a data-backed region changes. Check the real page at phone and desktop
widths, in light/dark mode, with keyboard and mouse. Verify ordinary pages do
not load React and the migrated region has no remaining Alpine owner.

Lower the Alpine baseline with the command above; it refuses increases. Delete
superseded interaction code after checking its other callers. Report the
feature outcome normally; mention a deferred migration only when useful.
These instructions do not authorise unrelated refactors, scheduled jobs,
deployment, automatic merges or access to another user's data.
