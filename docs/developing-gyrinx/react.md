# Incremental React in N26

N26 keeps Django routes and page shells. React owns bounded interactive regions
inside those pages; Cotton continues to render the surrounding UI. React regions
are client-rendered, not hydrated or server-rendered. A single useful interaction
can migrate without converting its page, its API or its neighbours.

## Diagnosis

The migration's hard part is shared ownership, not installing React:

- N26's design system is Tailwind, CSS tokens and Cotton templates, including an
  installed `django-cotton-ui` kit. React cannot render Cotton tags: they are
  Django compiler input, not browser components. A separately styled React kit
  would drift from the existing pages.
- Alpine behaviour is spread across pages, first-party primitives and the
  installed kit. Removing its script now would break menus, navigation and theme
  controls even on a page whose main interaction has migrated.
- htmx can replace a fragment containing a React root. Without a lifecycle
  boundary, that replacement can leave subscriptions alive or give both
  systems ownership of the same DOM.
- Django already prepares display structures and owns domain operations. A broad
  API rewrite would add work before the first useful React component appears.
- Existing agent instructions prohibit React and require no-JS forms. Without
  changing those instructions, agents would keep adding Alpine or reject the
  intended migration during review.
- Production uses Django manifest staticfiles and WhiteNoise. Vite also hashes
  assets. Giving a shared module two URLs can load two React instances; loading
  a cached document's deleted chunk can leave a blank region after a deployment.

## Decisions

| Question | Decision | Consequence |
| --- | --- | --- |
| Replace htmx with an API layer? | Gradually, within migrated interactions only. | Keep working htmx outside React; use native Django links/forms where sufficient. Add small JSON endpoints only when an interaction needs them. |
| Load React everywhere? | Yes, in N26: the bar's quick switcher is an island, so every page with the bar loads React. Other islands still load only where a template includes them. | The shared React chunk (about 68 kB gzip) is cached as an immutable asset; each full navigation still parses and runs it. |
| Minimise bootstrap cost? | One shared cached React chunk, small per-component entries, modulepreload, embedded initial props. | No initial data-fetch waterfall, duplicate runtime or framework/router dependency. |
| Pass initial state? | A plain JSON-safe view model through `react_island` and Django `json_script`. | Safe escaping, no executable inline state, no ORM objects or hidden permission assumptions. |
| Reuse the design system? | Generate presentation recipes from real rendered Cotton primitives at build time; implement their behaviour in typed React adapters. | The actual Cotton classes and app tokens stay authoritative. Only supported variants cross the bridge. |
| Where first? | Authoring lists, then authoring filters and pickers. | Repeated, well-tested interactions with existing server contracts; no ledger or player-purchase redesign in the first step. |

### DOM and state ownership

The template tag emits an empty host, an inert JSON script, modulepreloads and a
small module loader. `{% react_host %}…{% endreact_host %}` is the same host with
server-rendered markup inside it instead of a loading box, for a control that
holds its place in a bar: the page shows that markup until React mounts and
replaces it, and a reader without JavaScript sees only that markup. `x-ignore` and `hx-disable` prevent Alpine and htmx from
processing the host's children. An entry exports `mount(element, props)` and
returns a disposer. The loader mounts each host once, including a host inserted
after the first paint (an Alpine `x-if` disclosure, for example), handles
`htmx:load`, and unmounts the root when htmx or that insertion removes it,
including cancellation during an outstanding module import. Each root gets its
own React ID prefix.

The host's `data-react-name` is the kebab-case island name passed to the tag.
`data-react-module` is the content-addressed file URL, so a selector such as
`[data-react-module*='/pick-list-']` matches a hash, not a stable id. In Django
tests and Playwright, select `[data-react-name="campaign-asset-selection"]`,
then read the JSON script whose id is the host's `data-react-props`.

React owns everything inside its host. Django owns the host and surrounding
page. Do not nest islands, pass live Cotton DOM as React children, or swap part
of a React root with htmx. Compose React children inside one root when they need
shared state. Independent widgets can have separate roots without a global store.

Page identity and state people should share or restore belong in the URL:
server-backed filters, meaningful tabs and form variants. Use normal navigation
first; an island that changes them with the History API must also handle
Back/Forward. Search over already loaded rows, temporary selection, open menus,
focus and unsaved drafts can live in React. Permission decisions, prices and
calculated domain totals remain server-owned.

No-JS rendering is deliberately not required for a migrated region. Its host
shows a loading status; module or render failures offer a page reload, and
`noscript` explains the requirement. The rest of the page remains Django HTML.

### Design-system bridge

`n26/frontend/tooling/export_cotton_recipes.py` renders fixed examples through
the real Cotton compiler, checks their element structure, and extracts their
classes and icon geometry. `ui/` applies those recipes to ordinary React
elements. It does not
evaluate Alpine, inject HTML or transpile arbitrary templates. Generated recipes
and bundles are ignored by git; CI, Docker and the development command build
them with the installed Python and npm dependencies.

The first adapters cover buttons, links, tables, the staged badge, action bars,
search and a checkbox filter menu. Unsupported options are not a hidden second
implementation: add a recipe and a typed adapter when a real caller needs one.
Changes to the extracted element sequence fail the build; nesting and extra
wrappers still require visual review. For rich
primitives such as a combobox or dialog, share the visual recipe but implement
keyboard, focus and selection behaviour in React, with tests. Do not copy the
kit's Alpine attributes and expect them to work.

`ActionMenu` is the first such menu. It draws a menu whose items are all links,
using the kit dropdown's panel, item and separator classes, and implements the
WAI-ARIA menu button pattern in React: arrow keys, Home and End, Escape back to
the button, and Tab out. Templates use it through `<c-n26.action-menu>`, which
takes `Action` links or a `{% link_actions %}` list. Python decides each item's
order, tone and whether a separator sits above it; the island only draws them.
The wrapper renders the same button as the island until it mounts, so the row
does not move, and its `:scriptless` option adds a `<noscript>` list of the
links. `c-ui.dropdown` stays for menus with button or `hx-get` items, groups,
shortcuts or other composite content.

Both renderers use `designsystem/app.css`, the same typography, spacing, colours,
dark-mode class and CSS tokens. Tailwind scans the React source and generated
recipes. No new theme provider or CSS reset is introduced. The loader currently
supports JavaScript-only entries; do not import per-island stylesheets.

### Server interactions

The PoC needs no API: its links and GET form use existing Django views. This is
a useful default, not a restriction on later React forms.

For asynchronous reads or writes, add an endpoint beside the owning view:

1. Authenticate and check object-scoped permissions on every request; filter
   lookups to records that user may access.
2. Validate with existing forms/domain validation and call the same operation
   used by the HTML flow. Keep transactions and audit records there.
3. Return explicit display data on success and field/non-field errors on
   validation failure. Do not return ORM dumps, trusted HTML or raw exceptions.
4. Use same-origin session credentials and Django's CSRF token for unsafe
   requests. Preserve normal 401/403/404 behaviour; show session-expiry and
   network errors in the region. Do not disable CSRF to make `fetch` work.
5. Disable duplicate submissions while pending. Use server concurrency checks
   and idempotency where duplicate domain actions would spend or grant things;
   client button state is not a transaction guarantee.

Do not introduce a generic REST CRUD layer, duplicate domain logic in TypeScript
or replace unrelated htmx routes. A shared fetch helper becomes useful with the
first actual JSON write; it is not required scaffolding for a local list filter.

### Assets and cost

`npm run build` exports Cotton recipes, builds production Vite entries, then
builds CSS. `npm run js` is enough for Django tests that need the island
manifest. `npm run js:dev` selects React's development runtime and emits
unminified local assets with source maps, so source component names remain
visible in React DevTools. `./scripts/dev.sh` runs that development build before
serving and watches frontend changes with the same mode.

After rebasing an older worktree onto a branch that added or changed the React
islands, install from the lockfile and rebuild the gitignored manifest with the
worktree venv on PATH:

```bash
npm ci --no-audit --no-fund
PATH="$PWD/.venv/bin:$PATH" npm run js
```

`.codex/run.sh` does both when `node_modules` or the manifest is missing or
stale. `npm run js` starts a Python exporter, so a bare `npm run js` without the
venv fails. Do not run `npm audit fix` unless the task is the audit itself.

Vite owns the content-hashed filenames under `n26/react/assets/`. The template
uses those exact URLs and preloads their static imports. The ordinary bootstrap
script still uses Django's `static` tag. WhiteNoise marks Vite assets immutable;
`collectstatic` must keep the original Vite-named files, not only Django's
second-hashed copies. Do not enable `WHITENOISE_KEEP_ONLY_HASHED_FILES` without
changing that integration.

The first production build is about 68 kB gzip of shared React/React DOM and
3 kB gzip for the authoring-list entry, plus a small loader. These are measured
build sizes, not a mobile performance score. React still parses and executes on
each full page navigation, even with a warm cache. Alpine and the kit remain
loaded for unconverted chrome, so the transition temporarily carries both.
Avoid mounting React for static content or adding a router/state library.

Eagerly preload visible islands; do not put their first interaction behind an
intersection observer. Defer substantial below-fold tools only after measuring
the page. Preserve sensible loading space to limit layout shift. Large datasets
eventually need server pagination/search; React is not a reason to send every
record. Keep the previous deployment's hashed assets available during rollout
where the hosting setup permits it. If a stale page requests a removed chunk,
the loader's reload affordance is the recovery path, not a silent blank region.

## The proof of concept

`/n26/design/react/` is a staff-only, database-free demo. It compares Cotton and
React tables using the same sample content, offers live filtering, and prints the
actual template and React entry used to embed the component. Use the gallery's
theme control to compare both renderers in light and dark mode.

`/n26/authoring/weapon/` is a working example. All populated leaf-list pages use
the same `AuthoringList` component; the heading, help and New action stay Cotton.
An empty list stays Cotton and loads no React.

React replaces the list's Alpine search and bulk selection. It preserves name
links, qualifiers outside links, prices, author notes and staged markers. Search
uses the server's prepared search text. Select-all applies to shown rows, has an
indeterminate state, and does not discard selections hidden by a later filter.
Hidden inputs submit the selected IDs to the existing bulk-attach GET route.
No authoring operation or database schema changes.

`/n26/authoring/modifiers/` is the second working migration. Its populated list
uses a separate `modifier-list` island for search, scope/effect/carried facets,
the count and the table; the page header and empty state remain Cotton. The
filters narrow the complete set already embedded by Django, so their state stays
transient just as it was under Alpine. The shared `FilterMenu` adapter renders
the Cotton component's extracted presentation while React owns its popup,
checkbox, Apply, Cancel, outside-click and keyboard behaviour.

The leaf-list source path is:
`library.views.leaf` → `authoring/leaf.html` → `react_island` →
`islands/authoring-list/entry.tsx` → `AuthoringList.tsx` → `ui/`.

The modifier-list source path is:
`library.views.modifiers` → `authoring/modifiers.html` → `react_island` →
`islands/modifier-list/entry.tsx` → `ModifierList.tsx` → `ui/`.

Frontend source follows four dependency layers. Feature code is co-located under
`islands/<name>/`; generic mounting belongs in `runtime/`; Cotton-derived React
primitives form the public `ui/` boundary; Django-aware build code stays in
`tooling/`. The ignored `generated/` directory is output, never an authoring
surface. The repository-root TypeScript, Vite and Vitest configs are shared by
all islands beside the single root `package.json`; do not create per-island
configs. `n26/frontend/AGENTS.md` is the concise directory-level reference.

The Django view prepares ordinary display data, including server-generated URLs:

```python
authoring_list = {
    "rows": [{**row, "pk": str(row["pk"])} for row in rows],
    "pluralLabel": "weapons",
    "bulkActionUrl": reverse("authoring-attach-modifier", args=["weapon"]),
}
```

The template embeds it where the interaction belongs:

```django
{% load react %}
{% react_island "authoring-list" authoring_list %}
```

The entry mounts the component with the shared lifecycle and error boundary:

```tsx
import { mount as mountRoot } from "../../runtime/mount";
import { AuthoringList, type AuthoringListProps } from "./AuthoringList";

export function mount(element: HTMLElement, props: AuthoringListProps) {
    return mountRoot(element, AuthoringList, props);
}
```

Python tests cover initial data and existing view contracts; React tests cover
rendered behaviour and safe text handling. The actual worktree page should also
be checked with realistic data, keyboard selection, phone width and dark mode.
Keep database query-growth assertions: client rendering cannot fix N+1 queries.

## Migration as part of ordinary work

The defaults are in root and N26 `AGENTS.md`, the conventions/design skills,
Copilot instructions and `.agents/skills/n26-react/SKILL.md`. Agents should:

- Use React for new N26 interactions without asking for a framework decision.
- Convert the existing interaction they are already changing when it has a
  bounded DOM owner, existing server contracts and a reviewable test surface.
- Leave static Cotton and unrelated interactions alone. A copy-only edit does
  not justify replacing an entire composer.
- Explain a concrete migration blocker when conversion would require a domain
  redesign, new API contract or unbuilt complex primitive. Do not quietly add
  more Alpine as the default solution.
- Lower the per-template Alpine ceilings with
  `python scripts/check_n26_alpine.py --update`. CI fails when a template's
  Alpine increases. The guard counts Alpine attributes, not all possible
  JavaScript: review is still needed, and deleting a caller does not prove a
  shared primitive is unused.

This removes the need for the maintainer to repeatedly request React. It is a
default plus executable checks, not a guarantee that every agent will make the
right scoping decision without review.

### The Alpine baseline

`n26/frontend/tooling/alpine-baseline.json` gives each N26 template two
ceilings:

- **direct**: Alpine written in the template. That is `x-*` and `@event` on any
  tag, `:attr` on HTML tags, and `::attr` on Cotton tags, which Cotton renders
  as `:attr`. `:attr` on a Cotton tag is a Python expression, so it is not
  counted.
- **kit**: Alpine that `<c-ui.*>` kit components add to the page. Each use is
  charged the component's weight: the Alpine in its template plus the kit tags
  it nests, counting only the largest `{% if %}` branch. Weights come from the
  installed `django_cotton_ui` templates, or from the override in
  `n26/core/templates/cotton/ui/` when there is one.

Moving a menu to React lowers the kit column even when the template had no
Alpine of its own. Replacing hand-written Alpine with a new `<c-ui.dropdown>`
still fails, because the kit ceiling is per template too. Tooltips and tabs
are charged like any other kit component.

Two things are not charged in the kit column:

- page chrome (`ui.breadcrumbs`, `ui.alert`, `ui.avatar`), up to the cap for
  each tag in `UNCHARGED_TAGS`;
- kit tags in the design-system gallery, `n26/designsystem/`. The gallery's
  direct Alpine still counts.

Counts are per file. A component that repeats on a page counts once, and
`{% include %}` is not followed.

**Kit upgrades.** The baseline also records each kit tag's weight. When a
`django_cotton_ui` upgrade changes a weight, the check fails and names the
change, for example `ui.dropdown 13→15`. Review the change, then run
`--update`. `--update` accepts new weights, but it still fails when a template
has more direct Alpine or more kit tag uses. The first use of a kit tag with no
recorded weight also needs `--update`, so its weight is in the baseline before
an upgrade can change it. A kit tag with no template also fails the run, so a
renamed component cannot quietly drop to 0.

An override in `n26/core/templates/cotton/ui/` is a first-party template with
its own ceilings. Adding Alpine to one fails as new direct Alpine, even with
`--update`. Removing Alpine from one lowers its weight, which `--update`
records.

### Sequence and exit conditions

1. **Leaf lists:** prove packaging, visual reuse, props and lifecycle with a real
   interaction. Retain the existing bulk action.
2. **Modifier listing:** its loaded-row search/facets now use the shared React
   primitives, with the existing transient state and query-growth guards intact.
3. **Authoring pickers:** build one accessible React picker used by a real field.
   Preserve native field names and server validation. Port consumers gradually.
4. **Authoring composer:** migrate bounded sections after the picker and JSON
   validation contracts exist. Do not make the whole authoring application a SPA.
5. **Player interactions and shared chrome:** move reusable menus, dialogs and
   collection controls when their consumers are touched. Test money/state-changing
   paths against the real server operations, including repeat submissions.
6. **Remove old runtimes:** only after inventorying first-party templates,
   installed-kit components and all page shells. An empty Alpine baseline
   alone is insufficient, because page chrome and the gallery are not charged
   for kit Alpine. Remove htmx independently when no remaining
   consumers need HTML swaps.

Each step ships independently. Stop and reassess if adapter complexity exceeds
the interaction being migrated, the initial bundle grows substantially, or a
conversion needs a second source of domain truth. Track deleted directives,
converted interactions, cold/warm loading behaviour and visual defects rather
than a percentage of JSX lines.

## Optional scheduled migration

Enable a scheduled agent only after this foundation is merged and normal UI
work has exercised it. Start weekly with one unmerged migration PR at a time;
increase frequency only if review is keeping up. It should propose small changes,
never auto-merge or deploy. No schedule is installed by this PoC.

When authoring templates have no Alpine left, the job continues with one
page-local player interaction or shared control. It still ships a single
reviewable PR and leaves kit-owned controls alone.

A ready-to-use job prompt:

> Read the repository instructions and load the n26-react skill. Check for an
> open automated React migration PR; if one exists, stop. Check overlapping
> active work and avoid those candidates. From the `direct` column of the
> Alpine baseline, choose one small first-party interaction. Prefer a remaining authoring interaction. When
> `n26/library/templates` has no Alpine, take the next documented step: one
> player interaction or shared control whose Alpine owner is that template. It
> must already have a server contract (a native form, a link, or an existing
> endpoint) and be drawable with a supported primitive (`Button`, `Input`,
> `Switch`, `SearchBar`, `FilterMenu`, `CheckboxCard`, `PickBox`, `PickLegend`,
> `Dialog`, `Badge`, or an exported Cotton recipe). Prefer a template that owns
> its `x-data`, such as `cotton/n26/share.html` or `n26/trade_points.html`, over
> one that publishes values into a parent scope. Leave these until a smaller
> owner is gone: `c-ui.mode-toggle`, `c-ui.drawer`, `c-ui.dropdown`,
> `c-ui.popover`, `c-ui.tabs`, `c-n26.collection-picker`, `c-n26.range-menu`, and
> any fragment swapped by htmx. A React primitive that does not submit `name`
> and `value` does not replace a posting checkbox. Do not add a mode-toggle,
> dropdown, or range menu in order to unlock a larger page. Explain the
> boundary, migrate it without changing its behaviour, remove the superseded
> Alpine code and lower the baseline. Run Python and React tests, typechecking
> and the production build; check the real UI at phone and desktop widths in
> both themes. Open one reviewable PR with the changed interaction, test
> results and useful UI evidence. Do not change domain rules, add any API or endpoint,
> merge, deploy, or work around missing access. If every remaining candidate
> needs one of the deferred owners, report that dependency and make no PR.

## Framework references

React explicitly supports [multiple roots in partially React pages and unmounting
roots removed by other systems](https://react.dev/reference/react-dom/client/createRoot).
Vite documents [backend integration through its build manifest and modulepreload
graph](https://vite.dev/guide/backend-integration). This implementation keeps that
integration inside Django; it does not require a separate application server.
