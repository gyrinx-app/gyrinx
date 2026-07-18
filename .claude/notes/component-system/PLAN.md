# Component System Migration — Plan

**Goal:** Replace Django templates with a Python component library (JSX-like, renders static
HTML), remove the Bootstrap class-string explosion via reusable design-system components,
minimal view changes, fully tested + browser-verified, single PR.

## Findings (recon)
- 398 templates / ~25.9K lines in main worktree. SCSS is small (~1.7K lines): the "style
  explosion" is **repeated Bootstrap utility-class strings across templates**, not SCSS.
- Design system is well-specified: `docs/DESIGN-SYSTEM.md`, live ref `core/debug/design_system.html`,
  tokens `_tokens.scss`, `design-system` skill. This is the component vocabulary.
- Django 6.0, standard `DjangoTemplates` backend, `APP_DIRS=True`, DIRS include core/pages templates.
- Layout chain: `foundation.html` (head) ← `base.html` (nav/footer) ← pages; `page.html` simple shell.
- Custom tags: `custom_tags` (dot, active_*, safe_rich_text), `badge_tags` (user_badge),
  `pages` (get_page_by_url, get_root_pages), `color_tags` (house_icon). Context processors:
  site_banner, gyrinx_debug, notifications, impersonation.

## Architecture — `gyrinx/components/`
- `elements.py` — Element/VoidElement/Fragment/Safe engine. `tag(**attrs)[children]` API.
  Full Django SafeString interop (conditional_escape), clsx-style class handling, attr
  normalization (`class_`→class, `hx_get`→hx-get, `data_bs_toggle`→data-bs-toggle), boolean
  attrs, None/False drop.
- `tags.py` — HTML element factories (div, span, a, button, i, ...).
- `render.py` — render_to_string + Django response helpers + CsrfToken(request).
- `backend.py` — `ComponentsBackend` Django template backend: resolves ONLY explicitly
  registered page components by name (zero view change); TemplateDoesNotExist otherwise so
  Django falls through for legacy + third-party templates. Runs context processors itself.
  Registered FIRST in TEMPLATES. Only page-level names registered (never base/includes) →
  no `{% extends %}` hijack. Legacy templates + components coexist during migration.
- `design/` — design-system components mapping DESIGN-SYSTEM.md:
  icons, buttons, feedback(alerts), containers, typography, page(header/shells/Base layout),
  forms, tables, nav, badges, search, empty states, inline action menus, comma-list.
- `bridge.py` — bridge existing template tags: dot, active_view/path, user_badge, house_icon,
  safe_rich_text, page lookups, so components can use them.
- `tests/` — engine unit tests, design component output tests, backend resolution tests,
  golden HTML-equivalence tests vs legacy templates.

## Migration strategy
- Coexistence: convert a full page + its include subtree into components, register page under
  its template name, view unchanged. Legacy pages keep using files. Component pages use the
  component `Base` layout; both coexist.
- Order: engine → design layer → Base/foundation/page layouts → convert vertical slice
  (index, simple pages) → browser verify → fan out remaining via workflow, gated on tests.

## Inventory (from recon)
- ~200 full-page templates: ~185 core content pages, overwhelming majority extend
  `base.html` overriding ONLY `head_title` + `content`. Layout roots:
  foundation.html → base.html / base_print.html → page.html.
- ~130 includes/partials/widgets. Big ones: fighter_card*, list.html/list_row, campaign
  includes, pack includes.
- DO NOT convert: allauth/, account/, mfa/, usersessions/, admin/ overrides, error pages,
  .txt email/message templates, django/forms/field.html.
- Tags to bridge: custom_tags (214 uses!), color_tags (33), badge_tags (10), pages (3).
- foundation.html: exact head (favicons, typekit, bootstrap-icons CDN, GTM), body scripts
  (GTM noscript, bootstrap 5.3.8 JS, index.js module, figma capture if debug). Blocks:
  head_title, stylesheet, base, extra_script.
- Context processors inject: banner, gyrinx_debug, is_impersonating/impersonator,
  unread_notification_count.

## Delivery tiers
- T1 (core lib): engine ✓, design layer, bridge, layouts (Foundation/Base/Page), backend,
  gallery page. HIGH confidence.
- T2 (prove end-to-end): convert home/index + confirm + form + index page, browser-verify,
  golden tests.
- T3 (breadth): fan out remaining page conversions via workflow, gated on tests.

## Status
- [x] engine + tests (46 passing)
- [x] design layer + tests (35 passing) — icons/buttons/badges/alerts/containers/typography/
      nav/search/tables/forms/page-patterns
- [x] bridge (active_*, safe_rich_text, user_badge, house_icon, credits, flatpages)
- [x] layouts Foundation/Base/SimplePage + tests (6 passing)
- [x] backend Components (registered FIRST in settings) + registry + autodiscover + tests (5)
- [x] gallery page `/_debug/components/` — BROWSER-VERIFIED, renders full app shell + all
      components correctly (nav, footer flatpages, badges, alerts, tables, icons, etc.)
- [x] 92 component tests passing; existing view tests still green (no regression)
- CONVENTION: raw HTML tags use `tag[children]`; design components use call form `C(children)`.
- [x] convert real pages + golden tests — 14 committed & golden-verified:
      list_fighter_delete/kill/mark_captured/restore_confirm, list_archive, list_clone,
      campaign start/end/reopen/archive/remove_list/new/edit.
- [x] fan out via workflow — batch1 (3 pages) done & verified; batch2 (6 form pages) running.
- [x] full suite green (3450 passed, 0 regressions) + e2e view-render test + PR #1997 open.
- CONVERSION PIPELINE (proven, repeatable): read template+view context → write
  @register_page component (design components + _shared back/cancel + CsrfInput + reverse) →
  golden test via testing.assert_equivalent → central `pytest gyrinx/components/`.
- Remaining: big detail/index pages (list/campaign/pack detail, fighter card subtree) are
  large multi-include jobs, left for incremental follow-up (documented in PR).
## Progress log (PR #1997, branch components-system)
- 79 pages converted & golden-verified across 13 batches (list/fighter domain ~complete,
  campaign forms/confirms, vehicle flow, print). Full suite green (3528), zero regressions.
- Backend hardened: emits `template_rendered` (response.context works). Harness neutralises
  CSRF + `{% cachebuster %}` tokens.
- Reusable workflow: `convert_generic.workflow.js` — pass args=[{slug,template,view,confirm?,
  fixtureArgs?}]. Handles string-args (JSON.parse). Central verify: `pytest gyrinx/components/`.
- Commit routine: move `.claude/notes/migrate_project_fields_to_issue_fields.py` aside (its
  B404 is the only non-baseline bandit hit); pre-scan bandit before commit.
- Gotchas learned: (1) ContentFighter.name is a METHOD — call `.name()`; (2) delete-confirm
  titles with "delete…from" trip bandit B608 → `# nosec B608` on the string line; (3) unique
  constraints in test seeds (e.g. ContentRollTableRow.sort_order) need distinct values;
  (4) `list.get_absolute_url` doesn't exist → template silently "" → use `safe_referer(req,"")`.
- DEFERRED: list_fighter_weapons_edit (filter-branch edge case; stays on legacy template).
- REMAINING: campaign detail/index + actions/copy/captured/packs, battle (8, needs Battle
  fixtures), crew (6, needs Crew fixtures), pack/ (37, needs CustomContentPack fixtures),
  and the big index/detail pages (lists/list/campaigns/campaign/packs/pack) + fighter-card
  subtree. All follow the same pipeline.
- [ ] design layer + tests + gallery
- [ ] Django backend + context processors + tests
- [ ] layouts (foundation/base/page) as components
- [ ] convert slice + browser verify
- [ ] fan out conversions
- [ ] full suite + fmt + PR
