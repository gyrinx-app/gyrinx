# N26 frontend

This directory contains client-rendered React islands embedded in Django pages.
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

- An island may import `ui` and `runtime`. It must not import another island.
  Keep small similarities local; extract a clearly named shared module only
  when at least three real callers have established the same behaviour.
- `ui` is the public design-system adapter boundary. Islands import from
  `../../ui`, not from `generated` or an adapter's internal file.
- `runtime` knows how to mount React but knows nothing about feature props,
  Django routes, or design-system components.
- `tooling` may read Django and Cotton at build time. Browser code must never
  import it.
- `generated` is disposable output. Change the exporter or Cotton primitive,
  then rebuild; never edit generated recipes directly.

## Adding an island

Create `islands/<kebab-name>/entry.tsx` and co-locate its component and tests.
The entry is deliberately small: import the feature, call `runtime/mount`, and
return its disposer. Vite discovers island directories automatically, and the
Django tag resolves the same kebab-case name. Add no registry by hand.

Use `npm run js:dev` for a local one-shot JavaScript build. It selects React's
development runtime and emits unminified code with source maps, so React DevTools
shows source component names. `npm run watch` and `./scripts/dev.sh` use the same
development build. Production and CI use `npm run js`, which selects React's
production runtime, minifies code, and omits source maps. Both scripts start
with a Python exporter, so put the worktree venv on PATH (`PATH=$PWD/.venv/bin:$PATH
npm run js`, or `.codex/run.sh npm run js`). After a rebase, `.codex/run.sh`
runs `npm ci` and `npm run js` when the install or manifest is stale. Do not
run `npm audit fix` unless the task is the audit itself.
