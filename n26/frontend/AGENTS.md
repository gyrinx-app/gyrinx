# N26 frontend

This directory contains client-rendered React islands embedded in Django pages.
A root may contain an independent interaction or a complete workflow's page body,
including its confirmations and failure states. Compose components within that
root; do not nest or import other island entry points to assemble a page.
Read `.agents/skills/n26-react/SKILL.md` and
`docs/developing-gyrinx/react.md` before changing an interaction.

## Source hierarchy

```text
n26/frontend/
├── islands/
│   └── <island-name>/
│       ├── entry.tsx          # Public mount(element, props) boundary
│       ├── <Feature>.tsx      # Feature component and prop types
│       └── <Feature>.test.tsx # Behaviour tests beside the feature
├── runtime/                   # Generic island mounting and lifecycle code
├── http/                      # Shared form-encoded JSON transport
├── ui/                        # Shared Cotton-derived React primitives
├── generated/                 # Ignored output produced by the tooling
├── tooling/                   # Build-time exporters and migration inventories
└── test/                      # Test setup shared across islands
```

The repository-root `tsconfig.json`, `vite.config.mts`, and
`vitest.config.mts` configure this source tree. They live beside `package.json`
because the repository has one npm project; do not create a config per island.
If a genuinely independent TypeScript project appears later, its leaf config
may extend the root config and replace `include`; keep shared compiler options
at the root instead of copying them.

## Dependency direction

- An island may import `ui`, `runtime` and shared `http` helpers. It must not
  import another island.
  Keep small similarities local; extract a clearly named shared module only
  when at least three real callers have established the same behaviour.
  The workflow plan makes two explicit exceptions: shared JSON transport can
  start with the first command consumer, and catalogue presentation can be
  extracted when Hire and Equip use the same contract. Put transport in `http/`
  and shared presentation in `ui/`; keep workflow-specific rules in the island.
- `http` is for session credentials, CSRF and response/error handling. It must
  not depend on feature props, Django routes or domain calculations. Use
  `command.ts` for the shared request and field-error envelope.
- `ui` is the public design-system adapter boundary. Islands import from
  `../../ui`, not from `generated` or an adapter's internal file.
- `runtime` mounts React islands. It must not depend on feature props,
  Django routes, or design-system components.
- `tooling` may read Django and Cotton at build time. Browser code must never
  import it.
- `generated` is disposable output. Change the exporter or Cotton primitive,
  then rebuild; never edit generated recipes directly.

## Adding an island

Create `islands/<kebab-name>/entry.tsx` and co-locate its component and tests.
The entry is deliberately small: import the feature, call `runtime/mount`, and
return its disposer. Vite discovers island directories automatically, and the
Django tag resolves the same kebab-case name. The rendered host exposes that
name as `data-react-name`. `data-react-module` is the built file URL. Add no
registry by hand.

Use `npm run js:dev` for a local one-shot JavaScript build. It selects React's
development runtime and emits unminified code with source maps, so React DevTools
shows source component names. `npm run watch` and `./scripts/dev.sh` use the same
development build. Production and CI use `npm run js`, which selects React's
production runtime, minifies code, and omits source maps. Both scripts start
with a Python exporter, so put the worktree venv on PATH (`PATH=$PWD/.venv/bin:$PATH
npm run js`, or `.codex/run.sh npm run js`). After a rebase, `.codex/run.sh`
runs `npm ci` and `npm run js` when the install or manifest is stale. If
island, Cotton, or icon sources contain Git conflict markers, `.codex/run.sh`
skips that rebuild and the command you asked for still runs. Package
discovery excludes the gitignored Vite output, `generated/`, `node_modules`,
`staticfiles`, and `logs`, so an editable install does not keep those
directories. Do not
run `npm audit fix` unless the task is the audit itself.

## Saving workflow forms

The shared `http/command.ts` posts form data with same-origin credentials and a
CSRF token. It distinguishes rejected requests from writes whose outcome is
unknown. Keep domain response parsing and draft state in the island. After an
unknown outcome, retain the exact payload and request key and prevent editing
until retry resolves the save. Protect navigation while pending or uncertain,
and clear the warning before confirmed-success navigation. Manage credits is
the first consumer; its tests cover lost responses and rejected retries.
Retain unresolved input across reloads, scoped to actor and workflow. Restore
the command key and business values using fresh page credentials; do not persist
CSRF tokens. Test reauthentication, which rotates the token, before promising
recovery from session expiry.
`WorkflowPage` sets `data-busy="off"` so the shared busy-link handler cannot
mutate React-owned controls or leave a cancelled navigation disabled.
Check restoration from the back-forward cache after success. Refresh completed
forms whose command identity was consumed; preserve unsaved drafts and retain
the original identity of unresolved saves.

For absolute-edit conflicts, show current facts alongside the frozen draft and
require an explicit review action before loading a new baseline. Recovery input
can differ from the native POST that produced page props: do not apply that
POST's conflict/errors to a different retained command. Keep workflow-specific
conflict decisions outside shared HTTP transport.

## Shared workflow form controller

`ui/useWorkflowForm.ts` now serves Manage credits, Edit holding and Edit asset
type. Import it from `../../ui`. It owns pending/recovery state, focus and
navigation guards; the island interprets each domain response. Only a specific,
validated revision conflict may enable review of a newer baseline. A general
409 or validation refusal cannot resolve an earlier uncertain write. Run all
three consumers' tests when changing this shared lifecycle.

Hire is also a `useWorkflowForm` consumer. For explicit reload or sign-in actions,
use `recoverAt` to preserve the current draft. A rejected draft can remain
editable; never downgrade an earlier unknown outcome because a retry was rejected.
Keep retained URLSearchParams compatible with cached clients and keep every
expected scalar in the form, including an empty hidden value for an unticked
controlled checkbox. After changing this lifecycle, run the Hire confirmation
and recovery tests as well as the other workflow consumers.

Equip refreshes its existing root after a confirmed command. Use `onComplete`
for that refresh and preserve `recoverAt` for sign-in or reload navigation.
Match confirmation metadata to the retained request key before displaying it.
Keep a readable snapshot of selected options and destinations with unresolved
input, so recovery can describe the original action even on another panel.
Add presentation-only fields through `optionalRecoveryFields` to keep older
retained commands recoverable.

Fighter and stash Equip share the `equip` island. Compose the stored `ModelCard`
adapter inside that root; independent Edit, Options and action-flow screens stay
ordinary links. Use `WorkflowLayout` when card controls include native forms,
so they are not nested inside a page form. Its busy-script opt-out is required.
Keep counter steps in sequence with one request key per deliberate click; stop
unsent steps visibly on uncertainty while retaining the active command.
