# Design-system page upgrade — build specification

Target: `gyrinx/core/templates/core/debug/design_system.html` (1,679 lines today) becomes a
five-page, 39-section, server-routed reference under `/_debug/design-system/`.

---

## 1. Summary

### What the page becomes

Today the design-system page is a single 1,679-line scroll with 20 sections, no anchors, no
navigation and no way to cite a section in a code review. It documents swatches and primitives
well and composed UI badly — pagination, dropdowns, stat rows, filter bars, timelines, steppers
and breadcrumbs are all shipping in the app and appear nowhere on it.

The upgrade turns it into **five real URLs with a server-rendered sticky sidebar**, organised
around the question a reader actually arrives with. Not "what components do you have?" but
"I am about to build a thing — what does it look like here?". The groups are:

| Group | URL | Sections | What lives here |
|---|---|---|---|
| A. Start here | `/_debug/design-system/` | 3 | What the page is, the seven principles, and the URL-driven-state rule |
| B. Foundations | `/_debug/design-system/foundations/` | 5 | Colour, layout and spacing, typography, icons, light/dark |
| C. Components | `/_debug/design-system/components/` | 15 | Buttons, badges, callouts, boxes, fields, tables, dropdowns, pagination… |
| D. Patterns | `/_debug/design-system/patterns/` | 11 | Page shells and headers, filter bars, tabs, confirm pages, stat rows, collections |
| E. Reference | `/_debug/design-system/reference/` | 5 | Custom CSS, spaceless lists, flash, deprecated recipes, deliberate absences |

Plus `/_debug/design-system/all/` (every group concatenated — the Ctrl-F, print and
"link the whole system" target) and `/_debug/design-system/s/<section-id>/` (a 302 to the owning
group page plus fragment, so a section can move groups without breaking a two-year-old PR
comment).

**39 sections.** 20 carried forward from the existing page (several merged, split or renamed),
19 new.

### How the merge works

The brief's framing — "cover the same breadth as django-cotton.com/ui" — needed one correction
before it could be executed. The 15 blocks on cotton's landing page are a *marketing showcase*,
not the library. The real surface is 37 components, and the 15 blocks are compositions of them.
Matching the 15 blocks alone would undershoot by a wide margin; matching all 37 would import a
foreign visual language wholesale.

So the merge works from **capability**, not from component name. Cotton's 37 components abstract
to roughly 29 capabilities. For each one we asked: does Gyrinx already do this, and where? The
answer was "yes, and it is undocumented" far more often than expected:

- **Pagination** — `core/includes/pagination.html`, 11 include sites, zero reimplementations,
  entirely server-driven. It is the closest thing in the codebase to a finished component and
  the page has never mentioned it.
- **Activity timeline** — `core/includes/campaign_action_item.html`. Richer than cotton's,
  because ours carries dice rolls, outcomes and an actor.
- **Metric tiles with deltas** — the rating/credits/stash/wealth row in
  `core/includes/list_common_header.html`, 37 uses. Our deltas are real events, which makes it
  strictly better than "Revenue +20.1%".
- **Dropdown action menus** — `dropdown-menu` in 44 places, `dropdown-item` in 60, and the page
  shows them only incidentally inside two other demos.
- **Number stepper** — `core/includes/number_stepper.html`, which replaces cotton's range slider
  for every Gyrinx use (credits, XP, wounds are small integers).
- **Segmented controls, switches, radio cards, filterable checkbox groups, breadcrumbs, step
  progress, search bars, card grids** — all present, all undocumented or thinly documented.

So the upgraded page documents **our** versions of these. It does not import Tailwind idioms,
Alpine interaction models or SaaS furniture.

### What it deliberately excludes

- **No modals, dialogs or drawers as components.** The app ships zero Bootstrap modals
  (verified: no `data-bs-toggle="modal"`, no `class="modal"` anywhere) and exactly one
  offcanvas — the read-only embed-code panel at `core/includes/list.html:378-390`. A
  confirmation is a page. `#confirm-pages` states this as a deliberate divergence with the
  reasoning written down, rather than leaving each engineer to re-derive it.
- **No theme builder.** Tokens are documented, not editable. There is one brand.
- **No calendar or datepicker.** Battle and campaign dates use the native `<input type="date">`.
- **No range slider.** Superseded by the stepper.
- **No accordion component.** `bootstrap/scss/accordion` is imported at `styles.scss:68` and used
  zero times — dead CSS. We use `<details>`, and one-open-at-a-time is a section switch, which
  belongs in the URL.
- **No toast.** A transient message is a server-rendered banner at the top of the page.
- **No pricing, billing, payment or system-status content.** The *capabilities* underneath three
  of those are kept and re-expressed in domain terms; the content is discarded.
- **No client-side tab, filter or form mutation anywhere on the page.** The current page
  demonstrates nav tabs with `href="#"`, which actively mis-teaches the project's hardest rule.
  That is fixed.

---

## 2. Coverage map

Every one of the 15 django-cotton.com/ui blocks, with an explicit verdict.

| # | cotton-ui block | Gyrinx capability | Our section | Drawn from | Verdict |
|---|---|---|---|---|---|
| 1 | Payment method form | Labelled control envelope; form action row | `#form-field`, `#form-controls` | `core/includes/form_field.html` (36 uses); form pages under `gyrinx/core/templates/core/list/` | **Adapt** — keep the capability (label + widget + help + errors, self-wrapping), discard payments. Re-expressed as a real Gyrinx edit form. |
| 2 | System status (Operational/Degraded/Syncing) | Semantic status token | `#badges` | `core/campaign/includes/_status_indicator.html`; `core/includes/fighter_card_content.html:26-66` | **Adapt** — service-health framing rejected. Fighter states (active/injured/captured/dead/sold) and campaign statuses substituted; they carry real meaning. |
| 3 | Active project selector (+ "No options found") | Enriched single-select; in-widget empty state | `#dropdowns`, `#pickers`, `#empty-states` | `core/includes/fighter_gear_filter.html:32-72`; `core/includes/lists_filter.html` | **Adapt** — the trigger becomes a Bootstrap dropdown; the search becomes a server-filtered picker page. An Alpine listbox would break the URL-state rule. The empty state is lifted out of the widget to collection level, where we actually need it. |
| 4 | Processing status (Processing/Complete/Failed + Retry) | Async job status with recovery action | `#task-status` | `core/campaign/includes/list_row.html:8-18`; `core/campaign/includes/campaign_list_row_actions.html:9-21` | **Adapt** — real need (`gyrinx/tasks` background jobs). Ours is the "Joining Campaign…" spinner plus a Retry POST — the only `spinner-border` in the entire codebase. |
| 5 | Article tags | Tag chip | `#badges` | `core/campaign/includes/campaign_lists.html:52-62`; `gyrinx/templates/cotton/badge/chip.html` | **Adopt** — direct match. `badge fw-normal text-bg-light border` with a colour dot is the only true tag render in the app. |
| 6 | Billing period toggle (Monthly/Yearly) | Segmented n-ary choice | `#segmented-tabs` | `core/campaign/campaign_add_lists.html:78-101`; `core/lists.html:19-33` | **Adapt** — capability kept, billing content discarded. Rebuilt as a link group with server-computed `.active`; the `btn-check` radio form is documented as the second, narrower case. |
| 7 | Team members (+ Invite Members) | Roster collection with a primary action | `#collections` | `core/campaign/includes/campaign_lists.html`; `core/includes/list_row.html` | **Adapt** — genuinely re-expressible as the campaign gangs list with an "Add gang" action. Domain changes entirely; shape survives. |
| 8 | Notifications (Email/Push/SMS checkboxes) | Checkbox group | `#choices` | `core/includes/lists_filter.html:128-168`; `core/badge_settings.html:19-36` | **Adapt** — 174 `form-check` uses in 38 files and the current page shows two bare checkboxes. Adds the hidden-zero companion rule and the radio-card variant. |
| 9 | Required skills (searchable, creatable tags) | Searchable multi-select | `#pickers` | `core/list/list_fighter_skills_edit.html`; `core/pack/includes/weapon_profile_stats_form.html:19-45` | **Adapt** — server-side add/remove, each tag with its own remove form. Free-text creation is not a thing here; skills come from content. |
| 10 | Pricing plans (card grid) | Card grid | `#boxes` | `core/includes/list.html:290`; `core/includes/featured_pack_card.html` | **Adapt the grid, reject the content** — `grid auto-flow-dense g-col-12 g-col-md-6 g-col-xl-4` is documented; tiers and prices are SaaS furniture. The supporter-badge tiers we *do* have are recognition, not a funnel, and stay in `#supporter-badges`. |
| 11 | Security settings (switch + verification status) | Immediate-effect toggle | `#choices` | `core/includes/lists_filter.html:128-168`; `core/campaign/campaign_packs.html:38-52` | **Adapt** — with the switch rule stated for the first time: a switch is a *submit trigger*, never client-side state. Two live bugs named as follow-ups. |
| 12 | Metrics dashboard (3 stat cards with deltas) | Metric tile with delta | `#stat-rows` | `core/includes/list_common_header.html` (37 uses) | **Adapt** — the honest, non-SaaS version. Rating/credits/stash/wealth with real gain/loss after a battle. |
| 13 | FAQ (accordion) | Progressive disclosure | `#disclosure` | `core/pack/includes/_equipment_mods_picker.html:13,32,57`; `core/includes/_list_card_toggle.html` | **Adapt** — `<details>` with a server-set `open`, never `.accordion` and never `data-bs-parent`. The Bootstrap accordion SCSS import is dead and should be dropped. |
| 14 | Recent activity (timeline + clear + pagination) | Event timeline; server pagination | `#activity`, `#pagination` | `core/includes/campaign_action_item.html`; `core/includes/pagination.html` | **Adopt** — the one block we can match almost verbatim, because `core/campaign/campaign_actions.html:127-130` already pairs exactly these two includes. |
| 15 | Theme builder | Design-token theming | `#theme`, `#absences` | `core/layouts/base.html:66-110`; `core/layouts/foundation.html:4`; `core/static/core/js/index.js:55-150` | **Reject the builder, adopt the mode toggle** — `#theme` documents the light/dark/auto switcher that already ships undocumented. `#absences` records why there is no builder. |

Summary: **1 adopt** (#5), **1 adopt with both halves** (#14), **11 adapt**, **1 adapt-grid/reject-content** (#10), **1 reject with the mode toggle salvaged** (#15).

---

## 3. Page architecture

### 3.1 Why five pages and not one

Three forcing factors, only one of them aesthetic.

1. **The `design-system` skill cannot load the page any more.** `.claude/skills/design-system/SKILL.md:20`
   does `` !`cat gyrinx/core/templates/core/debug/design_system.html` ``. At 1,679 lines that is
   already ~20k tokens alongside the 437-line spec. The merged page lands near 4,000 lines.
   Splitting is the only fix that scales.
2. **Nothing on the page can be cited.** There is not one `id` on any section today, so no part
   of it can be referenced in a PR review — which is the main reason to have it. Anchors are the
   deliverable; a routed shell is how they stay stable.
3. **The page breaks the rule it teaches.** Its Nav tabs demo ships `href="#"`. A JS-tabbed or
   accordion navigation would make it a hypocrite on its own flagship rule. Server-routed pages
   make it an instance of its own doctrine.

Rejected alternatives: one long page plus a table of contents (cheapest, solves findability and
nothing else — the skill still chokes and the file stays unreviewable in a diff); per-component
pages on cotton's 37-URL model (too granular — cotton's reader arrives knowing a component name,
ours arrives with a problem); scrollspy (legitimately self-serving here, but it adds JS to a nav
that works without it, and five short pages leave little for active-tracking to earn).

### 3.2 Routing

Extend `_debug_urls` in `gyrinx/urls.py:32-66`. Every view keeps the
`if not settings.DEBUG: raise Http404(...)` guard.

| Path | URL name | Renders |
|---|---|---|
| `_debug/design-system/` | `debug_design_system` *(unchanged)* | Group A plus the A–Z index |
| `_debug/design-system/<slug:slug>/` | `debug_design_system_group` | One group; slugs `foundations`, `components`, `patterns`, `reference`. Unknown slug → 404 |
| `_debug/design-system/all/` | `debug_design_system_all` | Every group in order |
| `_debug/design-system/s/<slug:section_id>/` | `debug_design_system_section` | 302 to the owning group page + `#fragment`, resolved from the manifest. Unknown id → 404 |

**Preserving the `debug_design_system` name is load-bearing** — `gyrinx/core/tests/test_debug_views.py:16-38`
reverses it, and so does anything else in the tree. Register `all/` *before* the `<slug:slug>/`
pattern, or `all` is swallowed as a group slug.

`?theme=light` / `?theme=dark` compose with all of the above.

### 3.3 File layout

```
gyrinx/core/templates/core/debug/design_system/
    _shell.html                  extends core/layouts/base.html; sidebar + body;
                                 owns the single {# djlint:off H021 #} pragma and
                                 the one {% load %} line
    sections/<id>.html           one partial per section, 40–140 lines
gyrinx/core/views/debug.py       DESIGN_SYSTEM manifest + all sample data
gyrinx/core/templatetags/ds_tags.py   {% ds_demo %} / {% ds_props %}
```

The existing 1,679-line `design_system.html` is **deleted and redistributed**. No redirect is
needed because the URL name is preserved on the new index view.

Group pages and `/all/` both `{% include %}` the same partials, so there is exactly one copy of
every demo.

### 3.4 The manifest

A module-level list of plain dataclasses in `gyrinx/core/views/debug.py`:

```python
@dataclass(frozen=True)
class Section:
    id: str          # globally unique, kebab-case
    title: str
    purpose: str     # one sentence, starts with a verb
    kind: str = ""   # "cotton" | "include" | "markup" | "" (non-buildable)

@dataclass(frozen=True)
class Group:
    slug: str        # "" for Start here
    title: str
    blurb: str
    sections: tuple[Section, ...]

DESIGN_SYSTEM: tuple[Group, ...] = (...)
```

It drives the sidebar, the A–Z index, the group pages, `/all/` and the `/s/<id>/` redirect. One
list; no template-side `{% if %}` ladders anywhere.

**Kill the `custom_classes` preview ladder** at `design_system.html:1632-1650`. It is a booby
trap: adding a row to the view's `custom_classes` without adding a matching template branch
silently renders an empty Preview cell. Preview markup moves into the data as a `mark_safe`
snippet beside the class name.

### 3.5 Sidebar

The "Sidebar page" shell already listed in `page_shells` — `row g-4` with a `col-12 col-lg-3`
nav beside a `col-12 col-lg-9` body, sticky from `lg`. Vocabulary taken verbatim from
`gyrinx/core/templates/core/includes/account_sidebar.html`: `nav nav-pills flex-column gap-1`,
`{% active_view %}` / `{% active_aria %}`, `bi-* me-2` leading icons, count badge as `ms-auto`.
That include is used exactly once today; promoting it here makes it a real documented pattern
for free.

Five group links; the current group expands server-side to list its section anchors.

**Mobile:** the sidebar renders first as a single `<details class="border rounded p-3">` labelled
"Jump to…" containing the same links. No offcanvas, no JS — and it doubles as the page's own
worked example of `#disclosure`.

### 3.6 The section template — one idiom, replacing three

The current page frames demos three different ways (unframed, framed, table-as-doc); 14 sections
frame and 7 do not. At 39 sections that inconsistency reads as noise. Every section is:

```html
<section id="{id}">
    <h2 class="h4 mb-1">
        {Title}
        <a class="linked-secondary fs-7" href="#{id}" aria-label="Permalink to {Title}">#</a>
        <span class="badge text-bg-secondary fs-7 align-middle">{kind}</span>
    </h2>
    <p class="text-secondary fs-7 mb-3">{Purpose — one sentence, starts with a verb}</p>

    <h3 class="h6 caps-label mb-2">{Sub-block label}</h3>
    {% ds_demo %} …live markup… {% endds_demo %}
    <p class="text-secondary fs-7 mb-3">{caption}</p>

    {% ds_props "btn" %}   ← cotton-backed sections only
    <div class="table-responsive">
        <table class="table table-sm table-borderless mb-0 fs-7">…rules…</table>
    </div>
</section>
```

Every live demo is framed in `border rounded p-3` (`p-2` when the demo is itself dense), with an
`h3.h6.caps-label` above and a `p.text-secondary.fs-7` caption below. Every table is wrapped in
`<div class="table-responsive">` — reference tables carry long file paths that cannot wrap and
overflow 375px otherwise. The wrapper-`<div>` form is the convention (24 app templates); the
class-on-`<table>` form in `list_common_header.html:39` is a one-off, not a pattern to copy.

### 3.7 The `kind` badge

Every index row and every section documenting something buildable carries one of:

- **`cotton`** — a real `<c-*>` tag exists in `gyrinx/templates/cotton/`. Gets a generated props
  table.
- **`include`** — a Django include is the canonical implementation
  (`core/includes/pagination.html`, `step_progress.html`).
- **`markup`** — no component yet; the section documents raw Bootstrap.

All three are `text-bg-secondary`. Colour signals state, and component maturity is not a state —
a `markup` section is not a warning. This is honest about maturity, tells a reader instantly
whether to write `<c-btn>` or hand-roll, and makes the `markup` sections a visible backlog. It is
the cheapest mechanism for keeping the gallery and the library in step.

### 3.8 Code samples are generated, never hand-written

This is non-negotiable, and it is the lesson the current page teaches by counter-example. It
ships a `bi-person-add` that is not a real Bootstrap Icons name; a
`link-danger link-underline-opacity-50 link-underline-opacity-100-hover` recipe that
`styles.scss:273-288` explicitly supersedes with `.linked-danger`; and a
`linked-secondary`/`link-secondary` mix-up. All hand-copied, all confidently wrong, all
copy-pasteable.

`{% ds_demo %} … {% endds_demo %}` is a block tag in a new
`gyrinx/core/templatetags/ds_tags.py`, implemented the way Django's own `{% verbatim %}` is: the
parser captures the block's raw source text, the node compiles it once, renders it live inside
the `border rounded p-3` frame, then prints the identical captured string `force_escape`d into
`<pre class="fs-7"><code>`. Preview and sample are the same characters by construction; they
cannot drift. It works for cotton tags exactly as for raw Bootstrap, which is what makes the
migration to components visible on the page as it happens.

This also retires the `{% templatetag openblock %}` mess (15 uses) and the
`{% verbatim %}`-inside-`<code>` blocks (4 uses) — one of the latter, at `design_system.html:1226`,
is what currently breaks djlint's indenter and dedents the final 450 lines of the file to
column 0.

**Exception:** sections whose demos are `{% for %}` loops over context data (Colour, Icons,
Layout's sizing scales) should opt out of `ds_demo`, or the captured source prints the loop
rather than the markup a reader wants to copy.

### 3.9 Props tables — half generated, half written, with a test holding them together

`{% ds_props "btn" %}` parses `<c-vars …>` out of `gyrinx/templates/cotton/btn.html` to get prop
**names** and **defaults** — machine-derivable facts, so derive them; they cannot rot.
**Descriptions** are prose and live in a `COMPONENT_PROPS` dict in `debug.py`. A pytest asserts
bijection: every canonical file in `gyrinx/templates/cotton/` has a registry entry, and every
`<c-vars>` prop has a description. A missing description renders an empty cell — a visible nag —
and fails the test.

**Canonical component set, confirmed on disk (14):** `act`, `back`, `badge`, `badge/chip`,
`badge/fighter_state`, `box`, `btn`, `callout`, `cancel`, `confirm`, `disclosure`, `errors`,
`icon`, `messages`, `note`, plus the `filter/` (3 files) and `form/` (9 files) namespaces.
The **`c3/` and `zb/` directories are competing parallel drafts and MUST NOT be documented** —
the namespace question has to be settled before any section renders a live `<c-*>` tag
(see §7).

### 3.10 Heading semantics

The current page preaches one `<h1>` per page (line 39) and renders **nine**. One real `<h1>` per
group page, in the shell: "Design system — {Group title}". Sections are `<h2 class="h4">`,
sub-blocks `<h3 class="h6 caps-label">`. Demo markup that needs to *look* like a heading uses
`<div class="h2">`, never a real heading element — **except in `#typography`**, where the level is
the subject, and even there the previews use classes on `<div>`s because Bootstrap's
`.h1 { @extend h1; }` makes them pixel-identical. `/all/` renders the `<h1>` once, demotes group
titles to `<h2>` and sections to `<h3>`.

### 3.11 Housekeeping

- **Stale banner-comment numbers are deleted, not renumbered.** They already lie:
  `<!-- 13. EMPTY STATES -->` sits on the 16th section, `<!-- 18. FLASH ANIMATION -->` on the 21st.
  The manifest and the ids are the index now.
- **Spec reconciliation.** `docs/DESIGN-SYSTEM.md` is four months stale (2026-03-28) and
  contradicts the page in five places: campaign info columns implementation, `btn-success` in
  toolbars, list/detail header button colours, the type scale, and the Section row size (spec says
  1rem, it is 1.09rem — no `$h5-font-size` override exists). Rule, stated on `#overview`: **the
  page owns markup, the spec owns rationale, and where they disagree the page wins and the spec is
  fixed in the same PR.** `#principles` shrinks from a prose duplicate to a seven-line summary.
- **Skill update is part of this work, not a follow-up.** `.claude/skills/design-system/SKILL.md:20`
  cats a file that will no longer exist. Change it to cat `docs/DESIGN-SYSTEM.md` plus a generated
  `SECTIONS.md` index (id → title → purpose → partial path), and instruct the agent to read
  individual partials on demand. Context cost drops from ~20k to ~2k tokens and stays flat as the
  system grows.

### 3.12 View contract — preserve the two properties that make this page work

It hits **zero database tables** and it **renders logged out**. Both are locked in by
`test_debug_views.py:16-38`. All sample data stays Python literals / `SimpleNamespace` / the
existing `_DSUser` shim. New sample data follows the same rule. `ds_page_obj` must be a fake with
`.number`, `.has_previous`, `.has_next` and `.paginator.page_range` so
`core/includes/pagination.html` can be included for real rather than reimplemented.

### 3.13 Tests

Keep the two existing tests green; both need the `INTERNAL_IPS=[]` override (`_no_toolbar`,
`test_debug_views.py:7-13`) that keeps django-debug-toolbar out. The `b"house-icon"` assertion
moves to `/foundations/`. Add:

- a parametrised 200 over the five slugs plus `all`;
- a 404 for an unknown slug;
- a 404-when-`DEBUG`-off for each new route;
- a 302 from `/s/<id>/` to the right group page + fragment, for every id in the manifest;
- the props-registry bijection test;
- an assertion that every cross-reference fragment and every `ds_aliases` / `ds_index` target
  resolves to a real section id (this catches a rename in CI rather than in a reader's 404).

### 3.14 How it scales past 3,000 lines

- No page exceeds ~15 sections, so no single template file exceeds ~1,200 lines and each partial
  is 40–140 lines — reviewable in a diff.
- Adding a section is **one manifest entry plus one partial**. There is no second registration
  point.
- The skill reads a generated index plus partials on demand: flat context cost.
- The djlint indentation drift disappears with the `{% verbatim %}`-in-`<code>` blocks.
- `/all/` remains for the cases that genuinely want one document, and is the only place render
  cost grows linearly — acceptable for a `DEBUG`-only view.

---

## 4. The sections

### 4.0 Full manifest (39)

`Status`: **kept** = carried from the existing page; **merged** = absorbs another section;
**split** = extracted from one; **new** = did not exist.

| # | id | Title | Group | kind | Status | Priority |
|---|---|---|---|---|---|---|
| 1 | `overview` | Start here | A | — | new | p0 |
| 2 | `principles` | Principles | A | — | kept (trimmed) | p0 |
| 3 | `url-state` | If it changes what you see, it is a navigation | A | — | new | p0 |
| 4 | `colour` | Colour | B | — | kept (badges + links split out) | p0 |
| 5 | `layout` | Layout and spacing | B | — | merged (Spacing + vstack/hstack/grid/sizing) | p0 |
| 6 | `typography` | Typography and semantics | B | — | merged (Typography + heading semantics) | p1 |
| 7 | `icons` | Icons | B | cotton | kept (upgraded to c-icon gallery) | p1 |
| 8 | `theme` | Light, dark and auto | B | — | new | p2 |
| 9 | `buttons` | Button | C | cotton | kept (expanded) | p0 |
| 10 | `badges` | Badge and state | C | cotton | merged (promoted out of Colour) | p0 |
| 11 | `supporter-badges` | Supporter badges | C | include | kept | p2 |
| 12 | `callouts` | Callout and messages | C | cotton | kept (renamed from Feedback) | p0 |
| 13 | `boxes` | Box, card and container | C | cotton | kept (expanded) | p0 |
| 14 | `form-field` | Form field | C | cotton | split from Forms | p0 |
| 15 | `choices` | Checkbox, radio and switch | C | markup | split from Forms | p0 |
| 16 | `form-controls` | Inputs, selects and steppers | C | markup | split from Forms (+ Search input-group) | p1 |
| 17 | `tables` | Table | C | markup | kept (expanded) | p1 |
| 18 | `dropdowns` | Dropdown and button group | C | markup | new | p0 |
| 19 | `pagination` | Pagination | C | include | new | p0 |
| 20 | `links` | Links, back and cancel | C | cotton | kept (corrected; absorbs Colour's link block) | p1 |
| 21 | `tooltips` | Tooltip | C | markup | new | p1 |
| 22 | `empty-states` | Empty states | C | markup | kept (expanded 2→5 forms) | p1 |
| 23 | `disclosure` | Disclosure | C | markup | new | p1 |
| 24 | `page-shells` | Start a new page | D | — | kept | p0 |
| 25 | `page-headers` | Head a page or a section | D | — | merged (two divergent copies collapsed) | p0 |
| 26 | `filter-bars` | Let someone narrow a list | D | — | merged (absorbs Search pattern) | p0 |
| 27 | `segmented-tabs` | Let someone switch between views | D | — | merged (Nav tabs, rewritten URL-driven) | p0 |
| 28 | `confirm-pages` | Confirm a destructive action | D | — | new | p0 |
| 29 | `stat-rows` | Show a number that changed | D | — | new | p0 |
| 30 | `collections` | Show a list of things | D | — | new | p1 |
| 31 | `pickers` | Let someone pick from many things | D | — | new | p1 |
| 32 | `progress` | Show progress through a flow | D | include | new | p1 |
| 33 | `activity` | Show what happened | D | — | new | p1 |
| 34 | `task-status` | Show a background job | D | — | new | p2 |
| 35 | `inline-actions` | Inline action menus | D | markup | kept | p1 |
| 36 | `custom-css` | Custom CSS reference | E | — | kept (ladder removed, 9→~25 classes) | p1 |
| 37 | `spaceless` | Comma-separated lists | E | markup | kept | p2 |
| 38 | `flash` | Flash highlight | E | markup | kept | p2 |
| 39 | `absences` | What we deliberately do not build | E | — | new | p1 |

Seven sections are authored below with complete paste-ready markup. The remainder are specified
in this manifest and in §2's coverage map, and follow §3.6's single section template — they are
mechanical to author once the shell, `ds_tags` and the manifest exist.

### 4.1 `overview` — Start here (Group A)

**Purpose.** Orient the reader: what this page is, how it is organised, how to cite a section,
and the A–Z index for people who arrive knowing a component name rather than a problem.

**Partial:** `core/debug/design_system/sections/overview.html`

```html
<!-- ============================================================ -->
<!-- START HERE (id: overview) -->
<!-- ============================================================ -->
<section id="overview">
    <h2 class="h4 mb-1">
        Start here
        <a class="linked-secondary fs-7"
           href="#overview"
           aria-label="Permalink to Start here">#</a>
    </h2>
    <p class="text-secondary fs-7 mb-3">
        Find the pattern you need, cite it in a review, and add a new one. Every section shows markup taken
        from a real template — copy from here rather than from a page you happened to open. Nothing is styled
        specially because it is on this page; the only page-local CSS is the inline sizing on the colour
        swatches, which is why the shell carries a <code>djlint:off H021</code> pragma. This is also not the
        rationale document — see <a href="#overview-precedence" class="linked">Page and spec</a> below.
    </p>
    <h3 class="h6 caps-label mb-2">The five groups</h3>
    <div class="table-responsive mb-1">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Group</th>
                    <th scope="col">What lives here</th>
                    <th scope="col" class="text-center">Sections</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                {% for group in ds_groups %}
                    <tr>
                        <td class="text-nowrap">
                            <a href="{{ group.url }}" class="linked">{{ group.title }}</a>
                        </td>
                        <td>{{ group.blurb }}</td>
                        <td class="text-center">{{ group.section_count }}</td>
                    </tr>
                {% empty %}
                    <tr>
                        <td colspan="3" class="text-secondary">
                            No groups registered. Add one to <code>DESIGN_SYSTEM</code> in <code>core/views/debug.py</code>.
                        </td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Groups are pages, not tabs — each has its own URL, renders server-side, and is linkable.
        <a href="{{ ds_all_url }}" class="linked">Everything on one page</a> concatenates all
        {{ ds_groups|length }} groups in order: use it for Ctrl-F, for printing, and when you mean
        "the whole system" in a link.
    </p>
    <h3 class="h6 caps-label mb-2">A–Z index</h3>
    <p class="text-secondary fs-7 mb-2">
        For readers who arrive knowing a component name rather than a problem. <strong>Source</strong> is the
        canonical implementation — a cotton component, a Django include, or nothing yet.
        <strong>Uses</strong> is a snapshot count of call sites across app templates; <code>—</code> means
        not counted. A brand-new component can legitimately show no uses: the design system leads the
        codebase, and this column is how far ahead it is.
    </p>
    <div class="table-responsive mb-1">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Section</th>
                    <th scope="col">Kind</th>
                    <th scope="col">Source</th>
                    <th scope="col" class="text-center">Uses</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                {% for row in ds_index %}
                    <tr>
                        <td class="text-nowrap">
                            <a href="{{ row.url }}" class="linked">{{ row.name }}</a>
                        </td>
                        <td>{{ row.section_title }}</td>
                        <td>
                            <span class="badge text-bg-secondary fw-normal">{{ row.kind }}</span>
                        </td>
                        <td>
                            {% if row.source %}
                                <code>{{ row.source }}</code>
                            {% else %}
                                <span class="text-secondary fst-italic">None</span>
                            {% endif %}
                        </td>
                        <td class="text-center">
                            {% if row.uses %}
                                {{ row.uses }}
                            {% else %}
                                <span class="text-secondary">—</span>
                            {% endif %}
                        </td>
                    </tr>
                {% empty %}
                    <tr>
                        <td colspan="5" class="text-secondary">
                            No sections registered yet. Add one to <code>DESIGN_SYSTEM</code> in
                            <code>core/views/debug.py</code>.
                        </td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-3">
        The index is generated from the manifest — a section cannot exist without appearing here, and an
        entry cannot point at a section that has been removed.
    </p>
    <h3 class="h6 caps-label mb-2">If you came looking for…</h3>
    <p class="text-secondary fs-7 mb-2">
        Names from other component libraries that do not exist here, and where the equivalent capability lives.
        Each of these is a deliberate divergence, explained in the target section.
    </p>
    <div class="table-responsive mb-1">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">You searched for</th>
                    <th scope="col">Go to</th>
                    <th scope="col">Because</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                {% for alias in ds_aliases %}
                    <tr>
                        <td class="text-nowrap">
                            <code>{{ alias.term }}</code>
                        </td>
                        <td class="text-nowrap">
                            <a href="{{ alias.url }}" class="linked">{{ alias.target_title }}</a>
                        </td>
                        <td>{{ alias.reason }}</td>
                    </tr>
                {% empty %}
                    <tr>
                        <td colspan="3" class="text-secondary">No aliases registered.</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-3">
        If you reached for one of these and could not find it, that is the point — read the target section
        before building the thing you were about to build.
    </p>
    <h3 class="h6 caps-label mb-2">Citing a section</h3>
    <p class="text-secondary fs-7 mb-2">
        Every section carries a globally-unique kebab-case <code>id</code> and renders a permalink beside
        its heading. Ids are global, not group-scoped, so the same fragment resolves on a group page and on
        the everything page.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="h4 mb-1">
            Badge and state
            <a class="linked-secondary fs-7"
               href="#badges"
               aria-label="Permalink to Badge and state">#</a>
            <span class="badge text-bg-secondary fs-7 align-middle">cotton</span>
        </div>
        <p class="text-secondary fs-7 mb-0">Say what each badge colour means, and show the four shapes a badge takes.</p>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Two things to copy from that demo. The heading is a <code>&lt;div class="h4"&gt;</code>, not a real
        <code>&lt;h2&gt;</code> — demo markup that needs to <em>look</em> like a heading never uses a heading
        element, or it lands in the document outline. Typography is the one section where the level is the
        subject and real elements are used. And the permalink carries an <code>aria-label</code>: a bare
        <code>#</code> announces as "number sign, link", which is useless in a list of forty of them. The
        <code>#badges</code> fragment above is inert on this page and resolves on the Components page and on
        <a href="{{ ds_all_url }}" class="linked">the everything page</a>.
    </p>
    <h3 class="h6 caps-label mb-2">Section heading markup</h3>
    <pre class="border rounded p-2 fs-7 mb-3"><code>&lt;section id="badges"&gt;
    &lt;h2 class="h4 mb-1"&gt;
        Badge and state
        &lt;a class="linked-secondary fs-7"
           href="#badges"
           aria-label="Permalink to Badge and state"&gt;#&lt;/a&gt;
        &lt;span class="badge text-bg-secondary fs-7 align-middle"&gt;cotton&lt;/span&gt;
    &lt;/h2&gt;
    &lt;p class="text-secondary fs-7 mb-3"&gt;Purpose — one sentence, starts with a verb.&lt;/p&gt;
&lt;/section&gt;</code></pre>
    <h3 class="h6 caps-label mb-2">Permalinks that survive reorganisation</h3>
    <div class="table-responsive mb-1">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Use</th>
                    <th scope="col">Form</th>
                    <th scope="col">When</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <td>Citing in a PR</td>
                    <td class="text-nowrap">
                        <code>/_debug/design-system/s/badges/</code>
                    </td>
                    <td>
                        Redirects to the owning group page plus <code>#badges</code>, resolved from the manifest.
                        A section can move between groups without breaking a two-year-old review comment.
                    </td>
                </tr>
                <tr>
                    <td>Linking within a page</td>
                    <td class="text-nowrap">
                        <code>#badges</code>
                    </td>
                    <td>Cross-references between sections on the same page.</td>
                </tr>
                <tr>
                    <td>Linking to the whole system</td>
                    <td class="text-nowrap">
                        <code>/_debug/design-system/all/</code>
                    </td>
                    <td>Print, screenshot, or Ctrl-F across everything.</td>
                </tr>
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Prefer the <code>/s/&lt;id&gt;/</code> form in anything durable. Bare fragments break when a section
        is regrouped; the redirect does not.
    </p>
    <h3 class="h6 caps-label mb-2">Checking both themes</h3>
    <p class="text-secondary fs-7 mb-2">
        Every demo must read correctly in light and dark. The active theme is server-known at first paint:
        <code>core/layouts/foundation.html</code> stamps <code>&lt;html data-bs-theme&gt;</code> from the
        <code>theme_active</code> cookie, falling back to <code>auto</code>. The
        <code>?theme=</code> parameter below is <em>not</em> server-read — <code>core/js/index.js</code>
        applies it after load. It is one of the few sanctioned JavaScript enhancements, and it is worth
        knowing that it is one.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="hstack column-gap-3 row-gap-2 flex-wrap fs-7">
            <a href="?theme=light" class="linked">
                <i class="bi-sun-fill"></i> Preview this page in light
            </a>
            <a href="?theme=dark" class="linked">
                <i class="bi-moon-stars-fill"></i> Preview this page in dark
            </a>
            <a href="?theme=auto" class="linked">
                <i class="bi-circle-half"></i> Follow the OS setting
            </a>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Two caveats, both real. Applying <code>?theme=</code> writes the <code>theme_active</code> cookie for
        a year, so the <em>first paint</em> of every later page uses the previewed theme until the script
        re-reads your saved preference — expect a flash until you set the theme properly from the navbar
        switcher, which is the actual control. And because the parameter is read client-side, the link does
        nothing with JavaScript off. These are plain relative links because the design-system pages take no
        other query parameters; on a page that does, build the link with
        <code>{% templatetag openblock %} qt request theme='dark' {% templatetag closeblock %}</code>
        so the rest of the query string survives.
    </p>
    <h3 class="h6 caps-label mb-2">The kind badge</h3>
    <p class="text-secondary fs-7 mb-2">
        Every index row, and every section that documents something buildable, carries a badge saying what
        actually exists on disk. It tells you whether to write a component tag or hand-roll markup, and it
        makes the remaining backlog visible.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="table-responsive">
            <table class="table table-sm table-borderless mb-0 fs-7">
                <thead>
                    <tr>
                        <th scope="col">Badge</th>
                        <th scope="col">Means</th>
                        <th scope="col">What you write</th>
                    </tr>
                </thead>
                <tbody class="table-group-divider">
                    <tr>
                        <td>
                            <span class="badge text-bg-secondary fw-normal">cotton</span>
                        </td>
                        <td>
                            A component exists in <code>gyrinx/templates/cotton/</code>. The section carries a
                            generated props table.
                        </td>
                        <td>
                            The component tag, e.g. <code>&lt;c-btn variant="success"&gt;</code>
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="badge text-bg-secondary fw-normal">include</span>
                        </td>
                        <td>
                            A Django include is the canonical implementation, e.g.
                            <code>core/includes/pagination.html</code>.
                        </td>
                        <td>
                            <code>{% templatetag openblock %} include {% templatetag closeblock %}</code>, with the context contract the section states
                        </td>
                    </tr>
                    <tr>
                        <td>
                            <span class="badge text-bg-secondary fw-normal">markup</span>
                        </td>
                        <td>No component yet — the section documents raw Bootstrap.</td>
                        <td>The markup shown, copied verbatim</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        All three badges are <code>text-bg-secondary</code> on purpose. Colour signals state, and maturity is
        not a state — a <code>markup</code> section is not a warning. The word carries the meaning.
    </p>
    <h3 class="h6 caps-label mb-2" id="overview-precedence">Page and spec</h3>
    <div class="border rounded p-3 mb-2">
        <p class="mb-2">
            <strong>This page owns markup. <code>docs/DESIGN-SYSTEM.md</code> owns rationale. Where they
            disagree, the page wins and the spec is fixed in the same PR.</strong>
        </p>
        <p class="text-secondary fs-7 mb-0">
            The page is rendered from the same Bootstrap and SCSS the app ships, so it cannot drift from
            reality without visibly breaking. Prose can, and has. If you find a contradiction, do not pick
            whichever suits you — change the spec.
        </p>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Read the spec when you want to know <em>why</em> a rule exists; read a section here when you want to
        know <em>what to type</em>.
    </p>
    <h3 class="h6 caps-label mb-2">Adding a section</h3>
    <p class="text-secondary fs-7 mb-2">
        One manifest entry and one partial. The manifest drives the sidebar, this index, the group pages, the
        everything page, and the <code>/s/&lt;id&gt;/</code> redirect — there is no second place to register anything.
    </p>
    <pre class="border rounded p-2 fs-7 mb-2"><code># gyrinx/core/views/debug.py — inside DESIGN_SYSTEM
Section(
    id="badges",
    title="Badge and state",
    purpose="Say what each badge colour means.",
    kind="cotton",
)

# gyrinx/core/templates/core/debug/design_system/sections/badges.html
&lt;section id="badges"&gt;…&lt;/section&gt;</code></pre>
    <div class="table-responsive">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Rule</th>
                    <th scope="col">Why</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <td>
                        <code>id</code> is globally unique and kebab-case
                    </td>
                    <td>
                        Fragments resolve identically on a group page and on <code>/all/</code>
                    </td>
                </tr>
                <tr>
                    <td>
                        <code>purpose</code> is one sentence starting with a verb
                    </td>
                    <td>It is reused verbatim in the sidebar and this index</td>
                </tr>
                <tr>
                    <td>Never rename an id to tidy it up</td>
                    <td>
                        Ids are cited in review comments; add an entry to the alias table instead
                    </td>
                </tr>
                <tr>
                    <td>
                        Permalinks carry an <code>aria-label</code>
                    </td>
                    <td>
                        A bare <code>#</code> gives a screen reader nothing to distinguish forty links by
                    </td>
                </tr>
                <tr>
                    <td>Sample data goes in the view, never in the partial</td>
                    <td>
                        These pages hit zero database tables and render logged out — keep both properties
                    </td>
                </tr>
                <tr>
                    <td>
                        Wrap every table in <code>&lt;div class="table-responsive"&gt;</code>
                    </td>
                    <td>
                        Reference tables carry long paths and overflow 375px otherwise; the wrapper form is the
                        one used in 24 app templates
                    </td>
                </tr>
                <tr>
                    <td>Frame every live demo in <code>border rounded p-3</code></td>
                    <td>
                        With an <code>h3.h6.caps-label</code> above and a <code>p.text-secondary.fs-7</code> caption below
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</section>
```

**Rules established.** Every section carries a globally-unique kebab-case `id` and a permalink
with a mandatory `aria-label`. Cite sections in durable places with `/s/<id>/`, not a bare
fragment. Never rename an id — add an alias row. Demo markup that must look like a heading uses
`<div class="h4">`. The kind badge is always `text-bg-secondary`. Every table is wrapped in
`table-responsive`. The page owns markup, the spec owns rationale. Adding a section is one
manifest entry plus one partial. Sample data lives in the view. Preview tables are driven from
context data, never an `{% if row.id == 'x' %}` ladder (see `design_system.html:1631-1650`).
When the page documents a mechanism, state where it actually runs — `?theme=` is applied by
`core/js/index.js` after load, not by the server.

**Source files.** `gyrinx/core/templates/core/debug/design_system.html`;
`gyrinx/core/views/debug.py`; `gyrinx/urls.py`; `gyrinx/core/static/core/js/index.js`;
`gyrinx/core/templates/core/layouts/foundation.html`; `gyrinx/core/templates/core/layouts/base.html`;
`gyrinx/core/static/core/scss/styles.scss`; `gyrinx/core/templatetags/custom_tags.py`.

**New context variables.** `ds_groups`, `ds_all_url`, `ds_index`, `ds_aliases` (see §5).

**Cotton targets.** `c-badge` (the three kind badges and the index Kind column), `c-box` (the four
framed blocks), `c-icon` (the three theme-link icons — note the `-fill` variants; a `c-icon` that
silently accepts a non-existent name is how the wrong glyph got in here in the first place), and
two page-local candidates: `c-ds.section` (owns the `<section id>`, heading, permalink and kind
badge — more load-bearing than it looks, because the `aria-label` must derive from the title and
hand-copying that into 39 partials is how half of them end up without one) and `c-ds.table`
(emits the `table-responsive` wrapper; six tables in this section alone).

### 4.2 `principles` — Principles (Group A)

**Purpose.** State the rules everything else obeys, in seven lines, and point at the spec for the
reasoning.

**Partial:** `core/debug/design_system/sections/principles.html`

```html
<section id="principles">
    <h2 class="h4 mb-1">
        Principles
        <a class="linked-secondary fs-7"
           href="#principles"
           aria-label="Permalink to Principles">#</a>
    </h2>
    <p class="text-secondary fs-7 mb-3">
        The seven rules every other section on this page is an application of. They are ordered:
        the ones nearest the top decide whether a feature is built the Gyrinx way at all, the ones
        below decide whether it looks like the rest of the app.
    </p>
    <h3 class="h6 caps-label mb-2">The seven rules</h3>
    <ol class="mb-3">
        <li>
            <strong>Server-rendered HTML, not an SPA</strong> — full-page loads, Django templates,
            standard form POST. There is no client-side store, no view model and nothing to hydrate.
        </li>
        <li>
            <strong>If it changes what you see, it is a navigation</strong> — form variants, visible
            sections, tabs and filters belong in the path or query string and are rendered by the
            server. JS may enhance; it is never the only way to reach a state.
            <a class="linked" href="#url-state">URL-driven state →</a>
        </li>
        <li>
            <strong>Mobile-first</strong> — design at 375px, enhance at <code>md</code>/<code>lg</code>/<code>xl</code>.
            People read gangs on a phone, at the table, mid-game.
            <a class="linked" href="#layout">Layout and spacing →</a>
        </li>
        <li>
            <strong>Colour signals state, never decoration</strong> — active = success,
            injured/captured/in-repair = warning, dead = danger, neutral = secondary. Everything else
            is grey on purpose.
            <a class="linked" href="#colour">Colour →</a>
        </li>
        <li>
            <strong>Dense over spacious</strong> — more data per screen: <code>fs-7</code> in data
            tables, <code>p-2</code> in compact containers, metadata on one wrapping row. A gang
            roster should fit on one screen.
        </li>
        <li>
            <strong>Semantic HTML</strong> — one <code>&lt;h1&gt;</code> per page, heading levels never
            skip. Use <code>.h3</code>/<code>.h5</code> to change the size without changing the level.
            <a class="linked" href="#typography">Typography →</a>
        </li>
        <li>
            <strong>No modals — a confirmation is a page</strong> — a destructive action gets its own
            URL that can be linked, refreshed and backed out of. The app ships zero Bootstrap modals
            and exactly one offcanvas.
            <a class="linked" href="#confirm-pages">Confirm a destructive action →</a>
        </li>
    </ol>
    <p class="text-secondary fs-7 mb-4">
        An eighth rule, left off the list because it is a means rather than an end:
        <strong>Bootstrap 5.3 vocabulary first</strong> — custom classes only where Bootstrap has a
        gap (<a class="linked" href="#custom-css">Custom CSS reference</a>). Rules 1 and 3–6 restate
        the list in <code>docs/DESIGN-SYSTEM.md</code>; rules 2 and 7 come from <code>CLAUDE.md</code>
        and <code>.claude/skills/gyrinx-conventions/SKILL.md</code> and are not in that spec's
        Principles yet. This page owns the markup and wins where the three disagree —
        <a class="linked" href="#overview">why →</a>.
    </p>
    <h3 class="h6 caps-label mb-2">Density, shown</h3>
    <div class="border rounded p-3 mb-2">
        <div class="grid gap-3">
            <div class="g-col-12 g-col-md-6">
                <div class="caps-label mb-1">Ours</div>
                <div class="vstack gap-1">
                    <div class="h5 mb-0">Skulz Prospectors</div>
                    <div class="hstack column-gap-2 row-gap-1 flex-wrap">
                        <div>Squat Prospectors</div>
                        <div class="badge text-bg-primary">1250¢</div>
                        <div class="badge text-bg-secondary">
                            <i class="bi-list-ul"></i> List
                        </div>
                    </div>
                    <div class="text-secondary fs-7">Last edit: 2 days ago</div>
                </div>
            </div>
            <div class="g-col-12 g-col-md-6">
                <div class="caps-label mb-1">Not ours (counter-example)</div>
                <div class="vstack gap-3">
                    <div class="h5 mb-0">Skulz Prospectors</div>
                    <div class="vstack gap-2">
                        <div>Squat Prospectors</div>
                        <div>
                            <span class="badge text-bg-primary">1250¢</span>
                        </div>
                        <div>
                            <span class="badge text-bg-secondary"><i class="bi-list-ul"></i> List</span>
                        </div>
                    </div>
                    <div class="text-secondary">Last edit: 2 days ago</div>
                </div>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-0">
        The same four facts, in roughly twice the vertical space. Metadata rides one wrapping
        <code>hstack column-gap-2 row-gap-1 flex-wrap</code> row rather than a stack of one-per-line
        blocks, and only the timestamp drops to <code>fs-7</code>; the shipping version is
        <code>core/includes/list_row.html</code>. Both titles here are
        <code>&lt;div class="h5"&gt;</code> rather than <code>&lt;h5&gt;</code> — demos borrow heading
        <em>sizes</em>, never heading <em>levels</em> (rule 6). The real row uses a true
        <code>&lt;h2 class="mb-0 h5"&gt;</code>, because there it is genuinely a heading.
    </p>
</section>
```

**Rules established.** Principles is a summary, not a copy: each rule carries one clause of
consequence, never the reasoning. Seven rules in priority order — adding an eighth means demoting
one. Every rule with a section of its own ends in a link to it, so Principles doubles as the
page's routing table. Demos borrow heading sizes, never levels. **Never `{% url %}` a route that
is not in `gyrinx/urls.py`** — `NoReverseMatch` is a 500 on the whole page, not a broken link;
bare fragments degrade to a no-op. Claims of fact must be greppable in one command, and the grep
must actually have been run. Counter-examples are labelled in words, not by position or colour
(the two columns stack at 375px).

**Verified facts behind this section.** `grep -rn 'data-bs-toggle="modal"\|class="modal"' --include='*.html' gyrinx/`
→ no hits. Exactly one offcanvas: `core/includes/list.html:187` (trigger) and `:378-390` (panel).
`grep -i modal docs/DESIGN-SYSTEM.md` → **zero hits across all 437 lines** — the no-modals rule is
*not* in the spec; it lives in `CLAUDE.md` and `.claude/skills/gyrinx-conventions/SKILL.md:88-106`,
along with the URL-state rule. The section says so rather than mis-citing. `1250¢` matches
`format_cost_display` (`gyrinx/models.py:29-44`) — no thousands separator. The current page renders
**nine** `<h1>`s, not ten.

**Divergence for the migration to normalise.** `core/includes/list_row.html` puts
`align-items-baseline` on the *title* row (line 6); the house/wealth/mode row beneath (line 14) is
plain `hstack column-gap-2 row-gap-1 flex-wrap`. The demo above matches that class-for-class. Do
not migrate the baseline modifier between rows when merging them for a demo.

**Source files.** `gyrinx/core/templates/core/debug/design_system.html`; `gyrinx/urls.py`;
`gyrinx/core/views/debug.py`; `docs/DESIGN-SYSTEM.md`;
`.claude/skills/gyrinx-conventions/SKILL.md`; `gyrinx/core/templates/core/includes/list_row.html`;
`gyrinx/core/templates/core/includes/list.html`; `gyrinx/core/static/core/scss/styles.scss`;
`gyrinx/models.py`.

**New context variables.** None.

**Cotton targets.** `c-badge` — the two density-demo badges become
`<c-badge variant="primary" tag="div">1250¢</c-badge>` and
`<c-badge tag="div"><c-icon name="list-ul" /> List</c-badge>`. **`tag="div"` is required**:
`list_row.html` uses divs and the component defaults to `span`. `c-icon` — its semantic map has no
`list` key, so pass the raw name `list-ul`; it emits `aria-hidden="true"` unconditionally, which is
correct here. `c-box` — the demo frame, only if the frame stays inline rather than being owned by
`{% ds_demo %}`.

### 4.3 `url-state` — If it changes what you see, it is a navigation (Group A)

**Purpose.** Teach the project's hardest rule with the wrong and right versions side by side, and
give the test that distinguishes a disclosure from a navigation. This is the flagship section;
every group page's sidebar links back to it. It is also a deliberate inversion of cotton's
Alpine-first interaction model — this is where we say why we diverge from an entire component
library's assumptions, so nobody has to re-derive it.

**Partial:** `core/debug/design_system/sections/url-state.html`

```html
<!-- ============================================================ -->
<!-- URL-DRIVEN STATE -->
<!-- ============================================================ -->
<section id="url-state">
    <h2 class="h4 mb-3">If it changes what you see, it is a navigation</h2>
    <p class="text-secondary fs-7 mb-3">
        Any state that picks a form variant, switches a visible section, filters a list or selects a tab
        belongs in the <strong>URL</strong> — the path or the query string — and the server renders the
        result. JavaScript may <em>enhance</em> (save a click, save a scroll position, save a manual
        refresh) but the page must work, and be linkable, without it.
        <strong>Do not</strong> use a click or <code>change</code> handler to swap fields, hide
        sections, toggle <code>.active</code> or alter validation.
        Not this pattern: revealing content the server already sent (see Disclosure) or repainting the
        page without changing its content (see Light, dark and auto).
    </p>
    <h3 class="h6 caps-label mb-2">The test</h3>
    <div class="border rounded p-3 mb-2">
        <p class="mb-2">Ask two questions about the thing you are about to collapse or toggle:</p>
        <ol class="mb-2">
            <li>Would collapsing it hide something a submit depends on?</li>
            <li>Would expanding it need content the server did not send?</li>
        </ol>
        <p class="mb-0 fs-7">
            <strong>Either answer is yes →</strong> it is a navigation. Give it a URL.
            <br>
            <strong>Both are no →</strong> it is disclosure. <code>&lt;details&gt;</code> is enough,
            and the server still decides the initial <code>open</code> state.
        </p>
    </div>
    <p class="text-secondary fs-7 mb-4">
        The test is about the <em>server</em>, not about the pixels. Two controls can look identical and
        only one of them be legitimate.
    </p>
    <h3 class="h6 caps-label mb-2">
        <i class="bi-check-circle text-success" aria-hidden="true"></i> Right — a segmented control made of links
    </h3>
    <div class="border rounded p-3 mb-2">
        <nav class="btn-group mb-3" aria-label="Equipment category">
            {% for value, label in ds_variant_options %}
                <a class="btn btn-outline-primary btn-sm{% if value == ds_variant %} active{% endif %}"
                   href="?{% qt request ds_variant=value page=None %}#url-state"
                   {% if value == ds_variant %}aria-current="page"{% endif %}>{{ label }}</a>
            {% endfor %}
        </nav>
        <table class="table table-sm table-borderless mb-0 {% if ds_compact %}fs-7{% endif %}">
            <thead>
                <tr>
                    <th scope="col">Item</th>
                    <th scope="col" class="text-end">Cost</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                {% for name, cost in ds_variant_items %}
                    <tr>
                        <td>{{ name }}</td>
                        <td class="text-end">{% credits cost %}</td>
                    </tr>
                {% empty %}
                    <tr>
                        <td colspan="2" class="text-secondary">No wargear in this category.</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-4">
        This demo is live. Click a category and watch the address bar: the choice lands in
        <code>?ds_variant=</code>, the server picks the rows, and the server computes
        <code>.active</code> and <code>aria-current="page"</code>. Refresh, bookmark, share or
        open in a new tab — all of them land on the same view. The third segment shows the empty
        state for a category with nothing in it. A group of links that navigate is a
        <code>&lt;nav&gt;</code> with an <code>aria-label</code>, matching the header action groups in
        Page shells; <code>role="group"</code> is for groups of <em>buttons</em>.
    </p>
    <h3 class="h6 caps-label mb-2">Right — the template and the view</h3>
    <pre class="border rounded p-2 fs-7 mb-2"><code>&lt;nav class="btn-group" aria-label="Equipment category"&gt;
    {% templatetag openblock %} for value, label in variant_options {% templatetag closeblock %}
        &lt;a class="btn btn-outline-primary btn-sm{% templatetag openblock %} if value == variant {% templatetag closeblock %} active{% templatetag openblock %} endif {% templatetag closeblock %}"
           href="?{% templatetag openblock %} qt request variant=value page=None {% templatetag closeblock %}#gear"
           {% templatetag openblock %} if value == variant {% templatetag closeblock %}aria-current="page"{% templatetag openblock %} endif {% templatetag closeblock %}&gt;{% templatetag openvariable %} label {% templatetag closevariable %}&lt;/a&gt;
    {% templatetag openblock %} endfor {% templatetag closeblock %}
&lt;/nav&gt;

# views.py — the server reads the choice, normalises it, and renders.
variant = request.GET.get("variant", "melee")
if variant not in VARIANTS:
    variant = "melee"</code></pre>
    <p class="text-secondary fs-7 mb-4">
        <code>{% templatetag openblock %} qt {% templatetag closeblock %}</code> rebuilds the query
        string with every <em>other</em> parameter intact, so a category change does not silently drop
        the search term. <code>page=None</code> removes the key entirely — changing the filter must reset
        paging. The <code>#gear</code> fragment keeps the reader where they were. Always normalise the
        parameter in the view; never trust it straight into a template comparison.
    </p>
    <h3 class="h6 caps-label mb-2">
        <i class="bi-x-circle text-danger" aria-hidden="true"></i> Wrong — a handler that rewrites the page
    </h3>
    <pre class="border rounded p-2 fs-7 mb-2"><code>&lt;div class="btn-group" role="group"&gt;
    &lt;button class="btn btn-outline-primary btn-sm active" data-variant="melee"&gt;Melee&lt;/button&gt;
    &lt;button class="btn btn-outline-primary btn-sm" data-variant="ranged"&gt;Ranged&lt;/button&gt;
&lt;/div&gt;

&lt;script&gt;
document.querySelectorAll("[data-variant]").forEach((btn) =&gt; {
    btn.addEventListener("click", () =&gt; {
        document.querySelectorAll("[data-variant]")
            .forEach((b) =&gt; b.classList.remove("active"));
        btn.classList.add("active");
        document.querySelectorAll("[data-panel]").forEach((panel) =&gt; {
            panel.classList.toggle("d-none", panel.dataset.panel !== btn.dataset.variant);
        });
    });
});
&lt;/script&gt;</code></pre>
    <p class="text-secondary fs-7 mb-4">
        There is nothing to preview here, and that is the point: this renders exactly the same pixels as
        the version above. The defect is in the URL, not on the screen. If you find yourself adding a
        <code>click</code> or <code>change</code> listener, or reaching for <code>classList.toggle</code>,
        to decide what a form shows, you have skipped a navigation.
    </p>
    <h3 class="h6 caps-label mb-2">Same pixels, different behaviour</h3>
    <div class="table-responsive mb-4">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">What happens</th>
                    <th scope="col">Links (right)</th>
                    <th scope="col">Change handler (wrong)</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <th scope="row" class="fw-normal">URL after the choice</th>
                    <td>
                        <code>?variant=ranged</code>
                    </td>
                    <td>Unchanged</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">Refresh the page</th>
                    <td>Same view</td>
                    <td>Back to the default</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">Browser Back</th>
                    <td>Previous choice</td>
                    <td>Leaves the page entirely</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">Paste the link in a PR</th>
                    <td>Reviewer sees what you saw</td>
                    <td>Reviewer sees the default</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">JavaScript disabled or still loading</th>
                    <td>Works</td>
                    <td>Dead control</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">Server knows the choice</th>
                    <td>Yes — it rendered it</td>
                    <td>No — it is stranded in the DOM</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">Keyboard and screen reader</th>
                    <td>
                        Native link + <code>aria-current</code>
                    </td>
                    <td>Hand-built, usually wrong</td>
                </tr>
            </tbody>
        </table>
    </div>
    <h3 class="h6 caps-label mb-2">The three sanctioned enhancements</h3>
    <p class="text-secondary fs-7 mb-2">
        Each of these saves the reader exactly one thing, and each degrades to a working page.
        If an enhancement is the <em>only</em> way to reach a state, it is not an enhancement.
    </p>
    <div class="table-responsive mb-3">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Hook</th>
                    <th scope="col">Saves</th>
                    <th scope="col">Without JS</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <th scope="row" class="fw-normal">
                        <code>data-gy-toggle-submit</code>
                    </th>
                    <td>A click on the always-present submit button</td>
                    <td>The visible Update button submits the same GET form</td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">
                        <code>data-gy-collapse-url</code>
                    </th>
                    <td>A scroll position — writes the open panel into the query string</td>
                    <td>
                        The panel still opens; the server reads <code>?actions_open=1</code> on the next load
                    </td>
                </tr>
                <tr>
                    <th scope="row" class="fw-normal">The bounded task poller</th>
                    <td>A manual refresh while gangs join a campaign</td>
                    <td>Refresh the page; the "Joining…" placeholders update on load</td>
                </tr>
            </tbody>
        </table>
    </div>
    <h3 class="h6 caps-label mb-2">Live — a filter switch with its fallback submit</h3>
    <div class="border rounded p-3 mb-2">
        <form method="get"
              action="{% url 'debug_design_system' %}#url-state"
              class="hstack gap-3 flex-wrap align-items-center">
            {# A GET submit replaces the whole query string, so every param this page owns #}
            {# has to travel as a hidden input or it is silently discarded. #}
            <input type="hidden" name="ds_variant" value="{{ ds_variant }}">
            {% if request.GET.theme %}<input type="hidden" name="theme" value="{{ request.GET.theme }}">{% endif %}
            <div class="form-check form-switch mb-0">
                {# Hidden field to ensure 0 is sent when unchecked #}
                <input type="hidden" name="ds_compact" value="0">
                <input class="form-check-input"
                       type="checkbox"
                       role="switch"
                       id="ds-compact"
                       name="ds_compact"
                       value="1"
                       data-gy-toggle-submit
                       {% if ds_compact %}checked{% endif %}>
                <label class="form-check-label fs-7 mb-0" for="ds-compact">Compact rows</label>
            </div>
            <div class="btn-group align-items-center">
                <button class="btn btn-link icon-link btn-sm" type="submit">
                    <i class="bi-arrow-clockwise"></i>
                    Update
                </button>
                <span aria-hidden="true">•</span>
                <a class="btn btn-link linked-secondary icon-link btn-sm"
                   href="?{% qt request ds_compact=None %}#url-state">Reset</a>
            </div>
        </form>
    </div>
    <p class="text-secondary fs-7 mb-4">
        Also live — it resizes the table above. The switch is a <em>submit trigger</em>, never client
        state: <code>data-gy-toggle-submit</code> calls <code>requestSubmit()</code> on change, the
        server reads <code>?ds_compact=1</code> and re-renders the switch in its new position. The
        <code>checked</code> attribute is computed from the query string, never from a click handler.
        Four details are load-bearing: the <strong>hidden <code>value="0"</code> immediately before the
        checkbox</strong> (an unchecked box sends nothing, so "off" would be indistinguishable from
        "not submitted"), the <strong>always-visible Update button</strong>, the
        <strong>explicit <code>action</code> URL</strong> ending in the anchor, and the
        <strong>hidden inputs carrying the parameters this form does not own</strong>. That last one is
        the trap: a GET submit <em>replaces</em> the query string rather than merging into it, so
        anything not present as a field disappears. For a multi-valued parameter, loop
        <code>{% templatetag openblock %} qt_getlist request "type" {% templatetag closeblock %}</code>
        into hidden inputs. Canonical implementation:
        <code>core/includes/lists_filter.html</code>.
    </p>
    <h3 class="h6 caps-label mb-2">The one documented exception — the theme switcher</h3>
    <div class="border rounded p-3 mb-2">
        <p class="mb-2">
            The navbar theme picker sets <code>data-bs-theme</code> on <code>&lt;html&gt;</code> from a
            click handler. It is the only sanctioned piece of client-mutated UI state, and it qualifies
            on all three counts:
        </p>
        <ol class="mb-2">
            <li>
                <strong>It changes how the page is painted, never what the server renders.</strong>
                No field appears or disappears; nothing a submit depends on moves.
            </li>
            <li>
                <strong>The choice is persisted to a cookie the server reads.</strong>
                <code>index.js</code> writes <code>theme</code> and <code>theme_active</code>;
                <code>core/layouts/foundation.html</code> stamps <code>theme_active</code> onto
                <code>&lt;html data-bs-theme&gt;</code> on the very next request. The state is not
                stranded in the DOM, and on that path there is no flash of the wrong theme.
            </li>
            <li>
                <strong>It is still linkable.</strong> <code>?theme=light</code> and
                <code>?theme=dark</code> take precedence over the cookie, which takes precedence over
                <code>prefers-color-scheme</code>.
            </li>
        </ol>
        <p class="mb-0 fs-7">
            Check this page in both palettes:
            <a class="linked" href="?{% qt request theme='light' %}#url-state">?theme=light</a>
            <span aria-hidden="true">·</span>
            <a class="linked" href="?{% qt request theme='dark' %}#url-state">?theme=dark</a>
            <span aria-hidden="true">·</span>
            <a class="linked" href="?{% qt request theme=None %}#url-state">clear the override</a>
        </p>
    </div>
    <p class="text-secondary fs-7 mb-4">
        The override is sticky on purpose:
        <code>{% templatetag openblock %} qt {% templatetag closeblock %}</code> carries
        <code>theme</code> into every other link on this page, and the query parameter beats the cookie
        on each load — so clear it when you are done, or the navbar picker will look like it is not
        sticking. Note also that this one route <em>can</em> flash: the parameter is read by
        <code>index.js</code> after the server has already painted from the cookie.
        This is not a precedent. "Auto" tracking the OS live through <code>matchMedia</code> is the same
        exception for the same reason. Anything that changes <em>content</em> — a field, a section, a
        row, a tab pane the server would have to produce — is a navigation.
    </p>
    <h3 class="h6 caps-label mb-2">Verify it yourself</h3>
    <div class="border rounded p-3 mb-4">
        <p class="mb-2 fs-7">
            Every demo in this section works with JavaScript disabled. That is a claim, not a slogan —
            check it:
        </p>
        <ol class="mb-2 fs-7">
            <li>Disable JavaScript for this origin in DevTools and reload.</li>
            <li>The segmented control above still switches categories.</li>
            <li>
                The switch above still applies, via the <strong>Update</strong> button.
            </li>
        </ol>
        <p class="mb-0 fs-7 text-secondary">
            What stops working is everything that is <em>only</em> an enhancement: the theme picker, the
            collapse chevrons, Bootstrap's dropdowns, tooltips and alert dismiss buttons, and the
            computed-pixel columns in Typography. None of them is the only route to a piece of content.
        </p>
    </div>
    <h3 class="h6 caps-label mb-2">Rules</h3>
    <div class="table-responsive">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Rule</th>
                    <th scope="col">Why</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <td>Selected state is computed in the view, never toggled in the browser</td>
                    <td>
                        <code>.active</code> and <code>aria-current</code> must agree with what was rendered
                    </td>
                </tr>
                <tr>
                    <td>
                        Build hrefs with <code>{% templatetag openblock %} qt {% templatetag closeblock %}</code>, never by hand
                    </td>
                    <td>Preserves every other parameter; hand-built links silently drop the search term</td>
                </tr>
                <tr>
                    <td>
                        Reset paging with <code>page=None</code> on any filter change
                    </td>
                    <td>Page 4 of the old result set does not exist in the new one</td>
                </tr>
                <tr>
                    <td>Normalise the parameter in the view before using it</td>
                    <td>Query strings are user input; an unknown value must fall back, not 500</td>
                </tr>
                <tr>
                    <td>Anchor navigations to the section they affect</td>
                    <td>Otherwise every filter change scrolls the reader back to the top</td>
                </tr>
                <tr>
                    <td>Give a GET form an explicit action URL, not a bare fragment</td>
                    <td>The anchor rides along and the target does not depend on the current URL</td>
                </tr>
                <tr>
                    <td>Carry every parameter the form does not own as a hidden input</td>
                    <td>A GET submit replaces the query string; anything absent is discarded</td>
                </tr>
                <tr>
                    <td>A switch always ships a visible submit affordance</td>
                    <td>
                        <code>data-gy-toggle-submit</code> is enhancement; the form must submit without it
                    </td>
                </tr>
                <tr>
                    <td>
                        Pair every checkbox with a hidden <code>value="0"</code> before it
                    </td>
                    <td>An unchecked box sends nothing — "off" and "not submitted" must differ</td>
                </tr>
                <tr>
                    <td>A group of navigating links is a <code>&lt;nav aria-label&gt;</code></td>
                    <td>
                        <code>role="group"</code> describes a set of buttons, not a set of destinations
                    </td>
                </tr>
                <tr>
                    <td>Persisted settings POST to their own action URL and redirect</td>
                    <td>POST/redirect/GET; a filter or view option stays in the page's GET form</td>
                </tr>
                <tr>
                    <td>No modals — a confirmation is a page</td>
                    <td>A modal's open state is UI state that is not in the URL</td>
                </tr>
            </tbody>
        </table>
    </div>
</section>
```

**Rules established.** The two-question test. Selected state computed in the view. `{% qt %}` for
every state-changing href. `page=None` on any filter change. Normalise in the view. Anchor to the
affected section. **A GET form takes an explicit `action` URL with the anchor appended** —
`lists_filter.html:37-39` is `action="{{ action }}#search"`, always explicit. **A GET submit
replaces the query string** — carry every parameter the form does not own as a hidden input. A
switch is a submit trigger with a visible fallback. Hidden `value="0"` before every checkbox. A
group of navigating links is `<nav aria-label>`, not `<div role="group">`. Tables with unbreakable
`<code>` tokens go in `.table-responsive`. Every `<th>` gets a `scope`. Decorative glyphs carry
`aria-hidden="true"`. Only three JS enhancements are sanctioned. The theme switcher is the one
documented exception, and the `?theme=` route is sticky.

**Live violations of this section's own rule, for the migration to normalise.**
`core/campaign/campaign_packs.html:38-52` is a POST-form switch with `data-gy-toggle-submit`, no
visible submit and no `<noscript>` fallback — unusable with JS off.
`core/list/list_skill_trees_edit.html:29` uses inline `onchange="this.form.submit()"`, bypassing
`requestSubmit()` and therefore HTML5 validation. `lists_filter.html` ships three switches and only
the first ("Your Lists Only", line 88) carries the hidden `value="0"`; "Archived Only" (line 100)
and "Subscribed Only" (line 115) cannot express an explicit off. That is the strongest argument for
a `c-switch` that emits the companion input automatically.

**Source files.** `gyrinx/core/templates/core/includes/lists_filter.html` (canonical);
`core/campaign/campaign_add_lists.html`; `core/crew/includes/crew_tabs.html`; `core/lists.html`;
`gyrinx/core/static/core/js/index.js` (`data-gy-toggle-submit` at 415-453, `data-gy-collapse-url`
at 455-486, theme resolution at 55-150); `core/campaign/campaign.html:462-467` (bounded poller,
`INTERVAL = 4000`, `MAX_ELAPSED = 300000`); `core/layouts/foundation.html:2-4`;
`gyrinx/core/templatetags/custom_tags.py` (`qt` at 109-119, `credits` at 443-455);
`gyrinx/models.py:30`; `gyrinx/urls.py`; `gyrinx/core/tests/test_debug_views.py`;
`core/includes/list_campaign_actions.html:16-19`; `core/includes/_list_card_toggle.html`;
`core/campaign/campaign_packs.html`; `core/list/list_skill_trees_edit.html`.

**New context variables.** `ds_variant_options`, `ds_variant`, `ds_variant_items`, `ds_compact`
(see §5). The template also reads `request.GET.theme` directly, which needs no view support.

**Cotton targets.** `c-btn` (segmented links, once an outline variant and an active/aria-current
prop exist); `c-box` (the four framed blocks); `c-field` (the form-check/form-switch block).
Three *new* component candidates fall out of this section: **`c-segmented`** (props `:options`,
`:current`, `param`, `anchor`; must render a `<nav aria-label>` of links with server-computed
`.active`, and must absorb two href shapes — `{% qt %}` for values and `{% qt_rm %}` for an "All"
segment that clears the key, as `lists.html:22-36` does); **`c-switch`** (emits the hidden
`value="0"` automatically and refuses to render without a sibling submit or an explicit fallback
slot); **`c-filter-form`** (a GET form wrapper taking an explicit action URL plus a list of
carry-through parameter names, emitting the hidden inputs itself — six near-duplicate filter forms
each hand-roll this and each forgets a different parameter).

### 4.4 `colour` — Colour (Group B)

**Purpose.** Show the palette and, more importantly, state what each colour is allowed to mean.
Badge swatches split out to `#badges`; link colours split out to `#links` (both were duplicated in
two places with different class sets).

**Partial:** `core/debug/design_system/sections/colour.html`

```html
<!-- ============================================================ -->
<!-- COLOUR -->
<!-- ============================================================ -->
<section id="colour">
    <h2 class="h4 mb-1">
        Colour
        <a class="linked-secondary fs-7" href="#colour" aria-label="Permalink to Colour">#</a>
    </h2>
    <p class="text-secondary fs-7 mb-3">
        Pick a colour by naming the state it reports. If you cannot name one, the answer is
        no colour — default body text on the default surface. The UI is deliberately grey so
        that the few coloured things carry meaning. Colour is never decoration, never
        emphasis, and never a way to tell two equally-neutral things apart.
        Badge shapes live in <a href="#badges" class="linked-secondary">Badge and state</a>;
        link colours in <a href="#links" class="linked-secondary">Links, back and cancel</a>.
    </p>
    <h3 class="h6 caps-label mb-2">Theme colours</h3>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap gap-2">
            {% for name, hex in theme_colours %}
                <div class="text-center" style="width:5rem">
                    <div class="rounded-2 border"
                         style="width:5rem;
                                height:3.5rem;
                                background:{{ hex }}"></div>
                    <div class="fs-7 fw-semibold mt-1">{{ name }}</div>
                    <code class="fs-7 text-secondary d-block">${{ name }}</code>
                    <code class="fs-7 text-secondary d-block">{{ hex }}</code>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        Bootstrap's ten base hues, overridden in <code>styles.scss</code> (lines 24–33)
        <em>before</em> <code>bootstrap/scss/variables</code> is imported, so the five
        semantic colours that derive from a hue are all ours:
        <code>primary</code>←<code>$blue</code>, <code>success</code>←<code>$green</code>,
        <code>danger</code>←<code>$red</code>, <code>warning</code>←<code>$yellow</code>,
        <code>info</code>←<code>$cyan</code>. <code>secondary</code>, <code>light</code>
        and <code>dark</code> come from Bootstrap's grey scale, which we do
        <strong>not</strong> override — that is why a secondary badge looks like stock
        Bootstrap and a primary one does not. You will almost never name a hue directly.
        They are listed so you can recognise a hardcoded hex when you see one.
    </p>
    <h3 class="h6 caps-label mb-2">Semantic colours</h3>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap gap-2">
            {% for name in semantic_colours %}
                <div class="text-center" style="width:5rem">
                    <div class="rounded-2 border bg-{{ name }}"
                         style="width:5rem;
                                height:3.5rem"></div>
                    <div class="fs-7 fw-semibold mt-1">{{ name }}</div>
                    <code class="fs-7 text-secondary d-block">bg-{{ name }}</code>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        The eight names you actually write. <code>bg-*</code> paints a surface;
        <code>text-*</code> paints text; <code>text-bg-*</code> does both and is the only
        form a badge may use. What each name is permitted to mean is the table further down
        — it is the part of this section that matters.
    </p>
    <h3 class="h6 caps-label mb-2">Subtle backgrounds and emphasis text</h3>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap gap-2">
            {% for name in semantic_colours %}
                <div class="text-center" style="width:5rem">
                    <div class="rounded-2 border bg-{{ name }}-subtle"
                         style="width:5rem;
                                height:3.5rem"></div>
                    <div class="fs-7 fw-semibold mt-1">{{ name }}-subtle</div>
                    <code class="fs-7 text-secondary d-block">bg-{{ name }}-subtle</code>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-2">
        A tint for a whole region, where a full-strength fill would shout over its own
        contents. <code>bg-warning-subtle</code> is the only one in real use (31 uses) and
        it does three distinct jobs, which is worth knowing before you assume it means
        "warning":
    </p>
    <ul class="text-secondary fs-7 mb-2">
        <li>
            <strong>A modified stat cell</strong> in a statline —
            <code>{% templatetag openblock %} if stat.highlight {% templatetag closeblock %}bg-warning-subtle{% templatetag openblock %} endif {% templatetag closeblock %}</code>
            in <code>list_fighter_statline.html</code>,
            <code>fighter_card_content_inner.html</code>, <code>fighter_card_gear.html</code>
            and the pack preview card. This is the largest cluster by far.
        </li>
        <li>
            <strong>A fighter card header</strong> matching the state badge inside it —
            exactly one use, <code>fighter_card_content.html:26</code>, where dead is
            <code>bg-danger-subtle</code> and captured or sold is
            <code>bg-warning-subtle</code>.
        </li>
        <li>
            <strong>A bordered warning panel</strong> —
            <code>border border-warning rounded p-3 bg-warning-subtle</code> on the campaign
            copy pages, and the same pairing with <code>text-warning-emphasis</code> on the
            pack zero-cost warning. A subtle background wants an
            <code>-emphasis</code> text colour on top of it, not default body text;
            <code>text-warning-emphasis</code> has 7 uses and
            <code>text-danger-emphasis</code> 2. The other six emphasis colours have none.
        </li>
    </ul>
    <p class="text-secondary fs-7 mb-4">
        <code>bg-danger-subtle</code> has 3 uses — the dead card header, plus two on debug
        pages. <code>primary</code>, <code>success</code>, <code>light</code> and
        <code>dark</code> subtle have <strong>zero</strong> uses between them. Reach for one
        of those four and you are probably inventing a signal rather than reporting a state.
    </p>
    <h3 class="h6 caps-label mb-2">Text colours</h3>
    <div class="border rounded p-3 mb-2 vstack gap-2">
        <p class="mb-0">
            <span class="text-body">text-body (default)</span>
            ·
            <span class="text-secondary">text-secondary</span>
            ·
            <span class="text-body-secondary">text-body-secondary</span>
            ·
            <span class="text-body-tertiary">text-body-tertiary</span>
            ·
            <del class="text-secondary">text-muted</del>
        </p>
        <p class="mb-0">
            {% for name in semantic_colours %}
                <span class="text-{{ name }}">text-{{ name }}</span>
                {% if not forloop.last %}·{% endif %}
            {% endfor %}
        </p>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <code>text-secondary</code> is the de-emphasis class — 594 uses across app
        templates, and the one you want for metadata, captions and help text.
        <code>text-body-secondary</code> exists in Bootstrap but has a single use here (the
        page footer), and <code>text-body-tertiary</code> has none outside this page; prefer
        <code>text-secondary</code> unless you are matching adjacent markup.
        <code>text-muted</code> is <strong>deprecated</strong> and has four live uses left,
        all in <code>core/list/invitation_pack_setup.html</code>.
    </p>
    <h3 class="h6 caps-label mb-2">Light and dark</h3>
    <div class="border rounded p-3 mb-2">
        <div class="grid gap-3">
            <div class="g-col-12 g-col-md-6 border rounded p-3 bg-body text-body"
                 data-bs-theme="light">
                <div class="caps-label mb-2">data-bs-theme="light"</div>
                <div class="vstack gap-1">
                    <span class="text-secondary">text-secondary</span>
                    <a href="#colour" class="link-secondary">link-secondary</a>
                    <a href="#colour" class="linked-secondary">linked-secondary</a>
                    <span class="badge text-bg-secondary align-self-start">text-bg-secondary</span>
                </div>
            </div>
            <div class="g-col-12 g-col-md-6 border rounded p-3 bg-body text-body"
                 data-bs-theme="dark">
                <div class="caps-label mb-2">data-bs-theme="dark"</div>
                <div class="vstack gap-1">
                    <span class="text-secondary">text-secondary</span>
                    <a href="#colour" class="link-secondary">link-secondary</a>
                    <a href="#colour" class="linked-secondary">linked-secondary</a>
                    <span class="badge text-bg-secondary align-self-start">text-bg-secondary</span>
                </div>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-2">
        Both panels are on this page at once because <code>data-bs-theme</code> scopes a
        colour mode to a subtree — the same trick the navbar uses
        (<code>&lt;nav class="navbar bg-dark" data-bs-theme="dark"&gt;</code> in
        <code>core/layouts/base.html:6</code>). <code>bg-body</code> is what makes the panel
        pick up the scoped background; without it the panel would be transparent and the
        demo would silently show you the page's theme instead of the one it claims.
        <code>link-secondary</code> appears here because the dark override targets it by
        name, not as a recommendation — <code>linked-secondary</code> is the current form
        (see <a href="#links" class="linked-secondary">Links, back and cancel</a>).
    </p>
    <p class="text-secondary fs-7 mb-2">
        Secondary is lightened in dark mode by <strong>two different mechanisms</strong>,
        and the distinction matters when you are debugging a colour that will not change:
    </p>
    <div class="table-responsive mb-2">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Class</th>
                    <th scope="col">How it changes</th>
                    <th scope="col">Where</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <td>
                        <code>text-secondary</code>, <code>link-secondary</code>
                    </td>
                    <td>
                        Direct <code>color: … !important</code> override inside the
                        <code>[data-bs-theme="dark"]</code> block
                    </td>
                    <td>
                        <code>styles.scss:150–153</code>
                    </td>
                </tr>
                <tr>
                    <td>
                        <code>linked-secondary</code>
                    </td>
                    <td>
                        Reads <code>var(--bs-secondary-color)</code>, which is redefined per
                        theme — lightened 15% in light, 10% in dark
                    </td>
                    <td>
                        <code>styles.scss:142–148</code>, <code>:247–258</code>
                    </td>
                </tr>
                <tr>
                    <td>
                        <code>bg-secondary</code>, <code>text-bg-secondary</code>
                    </td>
                    <td>Unaffected by either. A secondary badge is the same colour in both themes.</td>
                    <td>—</td>
                </tr>
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-4">
        Check any demo on this page in the other palette by appending
        <code>?theme=dark</code> or <code>?theme=light</code> to the URL.
        <code>core/js/index.js</code> resolves the palette in that order — query parameter,
        then the <code>theme</code> cookie, then <code>prefers-color-scheme</code> — and
        writes the result to the <code>theme_active</code> cookie, which
        <code>core/layouts/foundation.html:4</code> reads to set <code>data-bs-theme</code>
        server-side. The query parameter is applied by JavaScript after first paint, so the
        very first render still uses the cookie.
    </p>
    <h3 class="h6 caps-label mb-2">What each colour is allowed to mean</h3>
    <div class="table-responsive mb-2">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Colour</th>
                    <th scope="col">Means</th>
                    <th scope="col">Canonical use</th>
                    <th scope="col">Never</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                {% for name, means, canonical, never in ds_colour_rules %}
                    <tr>
                        <td class="text-nowrap">
                            <span class="badge text-bg-{{ name }}">{{ name }}</span>
                        </td>
                        <td>{{ means }}</td>
                        <td>{{ canonical }}</td>
                        <td class="text-secondary">{{ never }}</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-4">
        The live source of truth for the state half of this table is the
        <code>state_variants</code> map in <code>gyrinx/templates/cotton/badge.html</code>.
        <code>core/static/core/scss/_tokens.scss</code> also declares
        <code>$gy-state-active/-injured/-captured/-dead</code>, but those aliases currently
        have <strong>no consumers</strong> in the SCSS — they are documentation, not
        mechanism, so do not assume changing one changes a colour. The full state-to-badge
        table, including the campaign statuses and the capture pseudo-states, belongs to
        <a href="#badges" class="linked-secondary">Badge and state</a> — it is not repeated
        here.
    </p>
    <h3 class="h6 caps-label mb-2">Writing a colour</h3>
    <div class="table-responsive mb-4">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">What</th>
                    <th scope="col">Use</th>
                    <th scope="col">Don't use</th>
                </tr>
            </thead>
            <tbody class="table-group-divider">
                <tr>
                    <td>De-emphasised text</td>
                    <td>
                        <code>text-secondary</code>
                    </td>
                    <td>
                        <del class="text-secondary">text-muted</del> (deprecated)
                    </td>
                </tr>
                <tr>
                    <td>Badges</td>
                    <td>
                        <code>text-bg-primary</code>, <code>text-bg-secondary</code>, …
                    </td>
                    <td>
                        <del class="text-secondary">badge bg-primary</del> (deprecated),
                        and never both forms together
                    </td>
                </tr>
                <tr>
                    <td>Region tint behind a state badge</td>
                    <td>
                        <code>bg-warning-subtle</code> with
                        <code>text-warning-emphasis</code>
                    </td>
                    <td>
                        <code>bg-warning</code> — a full-strength fill on a card header
                        shouts over its own contents
                    </td>
                </tr>
                <tr>
                    <td>A specific hue</td>
                    <td colspan="2">
                        Never a literal hex. Use a Bootstrap class, or a SCSS variable if
                        you are writing SCSS. Two sanctioned exceptions: a user-chosen
                        colour stored in the database (campaign attribute dots, gang
                        colours), which arrives as an inline
                        <code>background-color</code> because only the row knows it; and the
                        swatch grids at the top of this section, which document the palette
                        rather than use it.
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    <h3 class="h6 caps-label mb-2">Where we don't follow this yet</h3>
    <div class="border rounded p-3 mb-0">
        <p class="fs-7 mb-2">
            <strong>Colour is not yet used only for state.</strong> The rules above are the
            target, not a description of the estate. Six divergences worth knowing about
            before you copy markup out of the app:
        </p>
        <ul class="fs-7 text-secondary mb-0">
            <li>
                <code>text-bg-secondary</code> is the most-used badge colour (37 uses in app
                templates) and much of that is decorative — a cost, an XP total, a dice
                result put in a chip for emphasis. Those carry no state, so by this
                section's own rule they should be plain text.
            </li>
            <li>
                A dead fighter is <code>text-bg-danger</code> on the fighter card
                (<code>fighter_card_content.html:43</code>) and <code>text-bg-dark</code> in
                the post-battle editor
                (<code>list_post_battle_updates.html:150</code>) — the only
                <code>text-bg-dark</code> in the app. Injury states are <code>warning</code>
                on the card and <code>secondary</code> in that same editor (<code>:156</code>).
                <code>&lt;c-badge state="…"&gt;</code> is the fix.
            </li>
            <li>
                <code>core/includes/fighter_card_cost.html</code> emits
                <code>text-bg-secondary bg-secondary</code> on line 5 and
                <code>text-bg-warning bg-warning</code> on line 6 — the current and the
                deprecated form together, on both branches. Fixing one and not the other
                leaves the defect.
            </li>
            <li>
                The card-header tint and the badge disagree for one state: <em>Sold to
                Guilders</em> tints <code>bg-warning-subtle</code>
                (<code>fighter_card_content.html:26</code>) but badges
                <code>secondary</code> (<code>:62</code>). One of the two is wrong; the
                badge matches the rule.
            </li>
            <li>
                <code>core/includes/list.html:97</code> is
                <code>btn btn-info text-bg-info btn-sm</code> — a badge colour class on a
                button, and <code>info</code> used for an action when the table above says
                it is explanatory only.
            </li>
            <li>
                The modified-stat highlight (<code>stat.highlight</code> →
                <code>bg-warning-subtle</code>) is <strong>colour alone</strong>: no icon,
                no text, no <code>title</code>. It disappears in greyscale print and is
                invisible to a colourblind reader. It needs a non-colour signal as well.
            </li>
        </ul>
    </div>
</section>
```

**Rules established.** Colour is chosen by naming the state it reports; if no state can be named,
use no colour. Each of the eight semantic colours has exactly one permitted meaning, one canonical
use and one named prohibition — held as data in `ds_colour_rules`, not prose, so the table cannot
drift from the swatches above it. The abstract colour-meaning table lives in `#colour`; the
concrete domain state-to-badge table lives in `#badges`; neither repeats the other. **Only one
home for the state mapping is live** — `state_variants` in `cotton/badge.html`; `$gy-state-*` in
`_tokens.scss` has zero SCSS consumers. A subtle background is paired with the matching
`text-*-emphasis`. Hex literals are banned with exactly two named exceptions. A theme demo scopes
with `data-bs-theme` on the container and paints with `bg-body`. A demo may show a legacy class
when the mechanism targets it by name, but the caption must say so.

**Divergences for the migration to normalise.** All six in the "Where we don't follow this yet"
panel are verified and live. The `fighter_card_cost.html` double-class defect appears on *both*
branches (lines 5 and 6) — fixing one leaves the bug.

**Source files.** `gyrinx/core/static/core/scss/styles.scss`; `_tokens.scss`;
`gyrinx/core/static/core/js/index.js`; `gyrinx/templates/cotton/badge.html`; `callout.html`;
`badge/chip.html`; `core/includes/fighter_card_content.html`; `fighter_card_cost.html`;
`list_fighter_statline.html`; `list_common_header.html`; `list.html`;
`core/campaign/includes/status.html`; `campaign_attributes.html`;
`core/list_post_battle_updates.html`; `core/pack/includes/fighter_preview_card.html`;
`core/layouts/base.html`; `foundation.html`; `core/list/invitation_pack_setup.html`.

**New context variables.** `ds_colour_rules` (see §5). `theme_colours` and `semantic_colours` are
unchanged.

**Cotton targets.** `c-badge` — the nine raw `badge text-bg-*` spans become
`<c-badge variant="{{ name }}">`. Note `cotton/badge.html`'s docstring declares itself "the ONLY
file in the codebase permitted to write a `text-bg-*` class"; **this section is the one legitimate
exception** (it documents the raw class rather than consuming it) and that exception should be
written into the component's docstring rather than silently violated. `c-box` — the five framed
blocks. `c-callout` is deliberately **not** used for the divergence panel: `callout.html`'s own
docstring says callouts are feedback only, and grouped content wants `c-box`.

### 4.5 `layout` — Layout and spacing (Group B)

**Purpose.** Explain the wrappers every other demo on this page silently uses. **This section
supersedes the existing "4. SPACING" section (`design_system.html:501-545`) entirely — delete that
section when merging; shipping both puts two different gap tables on the same page.**

**Partial:** `core/debug/design_system/sections/layout.html`

```html
<!-- ============================================================ -->
<!-- LAYOUT AND SPACING -->
<!-- (supersedes the existing "4. SPACING" section — delete that -->
<!--  section when merging, do not ship both) -->
<!-- ============================================================ -->
<section id="layout">
    <h2 class="h4 mb-1">
        Layout and spacing
        <a class="linked-secondary fs-7"
           href="#layout"
           aria-label="Permalink to Layout and spacing">#</a>
    </h2>
    <p class="text-secondary fs-7 mb-3">
        The wrappers every other demo on this page silently uses. Reach for a <strong>stack</strong>
        (<code>vstack</code>/<code>hstack</code>) to lay content out in one direction, and Bootstrap's
        <strong>CSS grid</strong> (<code>grid</code> + <code>g-col-*</code>) for card layouts that reflow by
        breakpoint. Use <code>row</code>/<code>col-*</code> only when you actually need offsets, ordering or
        auto-width columns. Do <strong>not</strong> use any of these to build a page shell &mdash; pick one of
        the three documented shells first, then stack inside it.
    </p>
    <h3 class="h6 caps-label mb-2">Bootstrap spacing scale</h3>
    <p class="text-secondary fs-7 mb-2">
        Bootstrap default spacing: 0.25rem increments. 1rem = 16px at default browser settings. Every
        <code>m-*</code>, <code>p-*</code> and <code>gap-*</code> utility uses this scale.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap align-items-end gap-2">
            {% for level, rem in spacing_scale %}
                <div class="text-center">
                    <div class="bg-primary rounded" style="width:2rem;height:{{ rem }}rem"></div>
                    <code class="fs-7">{{ level }}</code>
                    <div class="fs-7 text-secondary">{{ rem }}rem</div>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        Note the jump: level 5 is 3rem, not 2rem. There is no built-in step between 1.5rem and 3rem &mdash; if
        you need one, you want <code>gap-4</code> plus margin on the child, not a new utility.
    </p>
    <h3 class="h6 caps-label mb-2">Page-level gap conventions</h3>
    <p class="text-secondary fs-7 mb-2">
        The gap on the page's own wrapper sets the rhythm for everything inside it. Pick from this table; do
        not invent a value.
    </p>
    <table class="table table-sm table-borderless mb-4 fs-7">
        <thead>
            <tr>
                <th>Where</th>
                <th>Gap</th>
                <th>Examples</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Form / edit page</td>
                <td>
                    <code>gap-3</code> (1rem)
                </td>
                <td>fighter-edit, list-edit</td>
            </tr>
            <tr>
                <td>Index / listing / detail page</td>
                <td>
                    <code>gap-4</code> (1.5rem)
                </td>
                <td>lists, campaigns, list detail, campaign detail, pack detail</td>
            </tr>
            <tr>
                <td>Between top-level documentation sections</td>
                <td>
                    <code>gap-5</code> (3rem)
                </td>
                <td>This page's own wrapper &mdash; the only <code>gap-5</code> in the codebase</td>
            </tr>
            <tr>
                <td>Inside a group box or card body</td>
                <td>
                    <code>gap-2</code> (0.5rem)
                </td>
                <td>fighter card body, alert stacks, metadata blocks</td>
            </tr>
            <tr>
                <td>Between metadata chips on one row</td>
                <td>
                    <code>column-gap-2 row-gap-1</code>
                </td>
                <td>list rows, pack rows &mdash; see the metadata row below</td>
            </tr>
        </tbody>
    </table>
    <h3 class="h6 caps-label mb-2">vstack &mdash; vertical stack</h3>
    <p class="text-secondary fs-7 mb-2">
        <code>vstack</code> is <code>display:flex; flex-direction:column</code> plus
        <code>flex:1 1 auto</code> and <code>align-self:stretch</code>. It is the default way to stack anything
        with even spacing &mdash; roughly 440 uses across the app, 16 of them on this page.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="vstack gap-2">
            <div class="border rounded p-2 fs-7">First</div>
            <div class="border rounded p-2 fs-7">Second</div>
            <div class="border rounded p-2 fs-7">Third</div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-2">
        <code>vstack gap-2</code>. Children are full width by default because of
        <code>align-self:stretch</code>; you never need <code>w-100</code> on them.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="hstack gap-2 align-items-start">
            <div class="vstack gap-1 border rounded p-2 fs-7">
                <div>
                    <code>vstack</code> child
                </div>
                <div class="text-secondary">Grows to fill the row, and stretches to full height</div>
            </div>
            <div class="d-flex flex-column gap-1 border rounded p-2 fs-7">
                <div>
                    <code>d-flex flex-column</code> child
                </div>
                <div class="text-secondary">Sizes to its content</div>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <strong>The gotcha.</strong> Because <code>vstack</code> sets <code>flex:1 1 auto</code>, a
        <code>vstack</code> placed inside an <code>hstack</code> expands to fill the row &mdash; and because it
        also sets <code>align-self:stretch</code>, it ignores the row's <code>align-items-start</code> and
        stretches to full height too. When you want the column to size to its content, write
        <code>d-flex flex-column gap-*</code> instead &mdash; which is exactly what
        <code>core/includes/list_row.html:5</code> does.
    </p>
    <h3 class="h6 caps-label mb-2">hstack &mdash; horizontal stack</h3>
    <p class="text-secondary fs-7 mb-2">
        <code>hstack</code> is <code>display:flex; flex-direction:row; align-items:center</code> plus
        <code>align-self:stretch</code> &mdash; but, unlike <code>vstack</code>, no <code>flex</code> shorthand,
        so it does not grow inside another flex container. Roughly 165 uses. Use <code>ms-auto</code> on a child
        to push it (and everything after it) to the far end &mdash; that is the standard way to right-align an
        action.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="hstack gap-2">
            <div class="border rounded p-2 fs-7">Label</div>
            <div class="border rounded p-2 fs-7">Value</div>
            <div class="ms-auto border rounded p-2 fs-7">
                Pushed with <code>ms-auto</code>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-2">
        <code>hstack gap-2</code> with <code>ms-auto</code> on the last child.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="hstack gap-2 flex-wrap mb-3">
            <div class="border rounded p-2 fs-7">Wraps</div>
            <div class="border rounded p-2 fs-7">at 375px</div>
            <div class="border rounded p-2 fs-7">because</div>
            <div class="border rounded p-2 fs-7">flex-wrap</div>
            <div class="border rounded p-2 fs-7">is present</div>
        </div>
        <div class="hstack gap-2 flex-wrap align-items-baseline">
            <div class="h5 mb-0">Cawdor Facts</div>
            <div class="fs-7 text-secondary">
                baselines aligned with <code>align-items-baseline</code>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <strong>Two rules.</strong> <code>hstack</code> does not wrap &mdash; add <code>flex-wrap</code> to
        anything that could overflow at 375px, or it will force a horizontal scrollbar on mobile. And when a
        row mixes type sizes (a heading beside body text), override the default centring with
        <code>align-items-baseline</code> so the text sits on one line.
    </p>
    <h3 class="h6 caps-label mb-2">The metadata row</h3>
    <p class="text-secondary fs-7 mb-2">
        The single most-repeated layout idiom in the app: a wrapping row of small facts under a title. Used in
        7 files &mdash; list rows, gang rows, campaign rows, pack rows.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-column gap-1">
            <div class="hstack column-gap-2 row-gap-1 flex-wrap align-items-baseline">
                <h3 class="mb-0 h5">
                    <a href="#" class="linked">Cawdor Facts</a>
                </h3>
                <div>
                    <i class="bi-person"></i> <a href="#" class="linked">underhive-boss</a>
                </div>
            </div>
            <div class="hstack column-gap-2 row-gap-1 flex-wrap">
                <div>House Cawdor{{ ds_house_icon_svg }}</div>
                <div class="badge text-bg-primary">1250&cent;</div>
                <div class="badge text-bg-secondary">
                    <i class="bi-list-ul"></i> List
                </div>
            </div>
            <div class="hstack column-gap-2 row-gap-1 flex-wrap">
                <div class="text-secondary fs-7">Last edit: 2 days ago</div>
                <div class="text-secondary fs-7" title="Stars">
                    <i class="bi-star-fill text-warning"></i> 4
                </div>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <code>hstack column-gap-2 row-gap-1 flex-wrap align-items-baseline</code>, stacked inside a
        <code>d-flex flex-column gap-1</code>. The gaps are split deliberately: a uniform <code>gap-2</code>
        leaves too much vertical air once the row wraps at 375px. <code>align-items-baseline</code> goes only on
        the row that mixes a heading with body text. The star count carries a <code>title</code> because the
        icon is the only thing naming it. Canonical source: <code>core/includes/list_row.html</code> &mdash; the
        real row also has an outer <code>hstack gap-3 position-relative</code> and a mobile-only
        <code>stretched-link</code> chevron, omitted here.
    </p>
    <h3 class="h6 caps-label mb-2">CSS grid &mdash; grid + g-col-*</h3>
    <p class="text-secondary fs-7 mb-2">
        Bootstrap's CSS Grid layout is enabled (<code>$enable-cssgrid: true</code>,
        <code>styles.scss:4</code>) and is what we use for card layouts &mdash; roughly 130
        <code>g-col-*</code> uses. <code>grid</code> is a 12-column CSS grid with a default
        <code>1.5rem</code> gap (<code>$grid-gutter-width</code>, not overridden); children declare their span
        with <code>g-col-{n}</code>, breakpoint-scoped as <code>g-col-{bp}-{n}</code>. Mobile-first: always
        start at <code>g-col-12</code>.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="grid">
            <div class="g-col-12 g-col-md-6 g-col-xl-4 border rounded p-2 fs-7 text-center bg-body-tertiary">1</div>
            <div class="g-col-12 g-col-md-6 g-col-xl-4 border rounded p-2 fs-7 text-center bg-body-tertiary">2</div>
            <div class="g-col-12 g-col-md-6 g-col-xl-4 border rounded p-2 fs-7 text-center bg-body-tertiary">3</div>
            <div class="g-col-12 g-col-md-6 g-col-xl-4 border rounded p-2 fs-7 text-center bg-body-tertiary">4</div>
            <div class="g-col-12 g-col-md-6 g-col-xl-4 border rounded p-2 fs-7 text-center bg-body-tertiary">5</div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        <code>g-col-12 g-col-md-6 g-col-xl-4</code> &mdash; the fighter-card grid. One column on mobile, two
        from <code>md</code>, three from <code>xl</code>.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="grid auto-flow-dense">
            <div class="g-col-12 g-col-md-8 border rounded p-2 fs-7 text-center bg-body-tertiary">
                1 &mdash; <code>g-col-md-8</code>
            </div>
            <div class="g-col-12 g-col-md-6 border rounded p-2 fs-7 text-center bg-body-tertiary">
                2 &mdash; <code>g-col-md-6</code>, will not fit beside 1
            </div>
            <div class="g-col-12 g-col-md-4 border rounded p-2 fs-7 text-center bg-body-tertiary">
                3 &mdash; <code>g-col-md-4</code>, back-filled beside 1
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        <code>grid auto-flow-dense</code> sets <code>grid-auto-flow: row dense</code>
        (<code>styles.scss:741</code>), letting a later short item back-fill a hole an earlier wide one left
        behind. Widen the window past <code>md</code> to see it: item 2 is too wide for the four columns left
        beside item 1, so it drops to row two &mdash; and item 3 is then pulled <em>back up</em> into the gap.
        Without <code>auto-flow-dense</code> item 3 would sit next to item 2 and the hole would stay open. Used
        on the list detail card grid (<code>core/includes/list.html:290</code>) and the lore/notes grids, where
        cards have wildly different heights.
    </p>
    <h3 class="h6 caps-label mb-2">When grid, when row/col</h3>
    <table class="table table-sm table-borderless mb-4 fs-7">
        <thead>
            <tr>
                <th>Use</th>
                <th>For</th>
                <th>Because</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>
                    <code>grid</code> + <code>g-col-*</code>
                </td>
                <td>Card grids, tile layouts, anything that reflows by breakpoint</td>
                <td>Real CSS grid: equal-height rows for free, <code>auto-flow-dense</code> available, no gutter padding to undo</td>
            </tr>
            <tr>
                <td>
                    <code>row</code> + <code>col-*</code>
                </td>
                <td>Offsets, explicit ordering, auto-width columns, form field rows</td>
                <td>Only flexbox columns support <code>offset-*</code>, <code>order-*</code> and <code>col-auto</code></td>
            </tr>
            <tr>
                <td>
                    <code>vstack</code> / <code>hstack</code>
                </td>
                <td>One-directional flows with even spacing</td>
                <td>Cheaper than a grid, and the child does not need a span class</td>
            </tr>
        </tbody>
    </table>
    <h3 class="h6 caps-label mb-2">Butt-joining adjacent cards</h3>
    <p class="text-secondary fs-7 mb-2">
        Custom responsive utilities (<code>styles.scss:604-663</code>) that remove a border or a corner radius
        <em>from a breakpoint up</em>: <code>border-{bp}-0</code>, <code>border-{side}-{bp}-0</code>,
        <code>rounded-{bp}-0</code>, <code>rounded-{side}-{bp}-0</code>, plus the inverse
        <code>border-{bp}</code> / <code>border-{side}-{bp}</code> which add one. (There is no inverse
        <code>rounded-{bp}</code> &mdash; radii can only be removed.) They exist for one job: making two cards
        that belong together read as a single unit on wide screens while still stacking as separate cards on
        mobile.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="grid">
            <div class="g-col-12 g-col-xl-8 break-inside-avoid">
                <div class="grid h-100 gap-2 gap-md-0 border rounded p-2 bg-secondary-subtle">
                    <div class="card g-col-12 g-col-md-6 border-end-md-0 rounded-end-md-0 break-inside-avoid">
                        <div class="card-header p-2 fs-7 fw-semibold">Ridge Runner</div>
                        <div class="card-body p-2 fs-7 text-secondary">Vehicle</div>
                    </div>
                    <div class="card g-col-12 g-col-md-6 border-start-md-0 rounded-start-md-0 break-inside-avoid">
                        <div class="card-header p-2 fs-7 fw-semibold">Grot Mekboy</div>
                        <div class="card-body p-2 fs-7 text-secondary">Crew</div>
                    </div>
                </div>
            </div>
        </div>
    </div>
    <pre class="border rounded p-2 fs-7 mb-3"><code>&lt;div class="g-col-12 g-col-xl-8 break-inside-avoid"&gt;
  &lt;div class="grid h-100 gap-2 gap-md-0 border rounded p-2 bg-secondary-subtle"&gt;
    &lt;div class="card g-col-12 g-col-md-6 border-end-md-0   rounded-end-md-0   break-inside-avoid"&gt;…&lt;/div&gt;
    &lt;div class="card g-col-12 g-col-md-6 border-start-md-0 rounded-start-md-0 break-inside-avoid"&gt;…&lt;/div&gt;
  &lt;/div&gt;
&lt;/div&gt;</code></pre>
    <p class="text-secondary fs-7 mb-4">
        Three levels, and all three matter. The <strong>outer</strong> div is the grid child that positions the
        pair in the page grid and carries <code>break-inside-avoid</code>; the <strong>middle</strong> div is a
        nested grid whose <code>h-100</code> makes the joined pair fill that child so both halves finish level;
        the <strong>cards</strong> drop the facing border <em>and</em> the facing radius. All the breakpoint
        suffixes have to agree: the wrapper closes its gap (<code>gap-2 gap-md-0</code>) at the same breakpoint
        the borders and radii disappear. A middle card in a three-way group drops both sides. Below
        <code>md</code> everything reverts and the cards stack as normal rounded cards. This is one of only two
        places <code>card</code> is legitimate &mdash; do not copy the <code>card</code> class out of this demo
        for anything that is not a fighter grid or an equipment category. Canonical source:
        <code>core/includes/list.html:323-337</code> and <code>core/includes/blank_vehicle_card.html</code>
        (card internals abbreviated above).
    </p>
    <h3 class="h6 caps-label mb-2">Sizing scales</h3>
    <p class="text-secondary fs-7 mb-2">
        Three SCSS-generated scales sized in <code>em</code>, so they scale with the surrounding font size
        instead of freezing a pixel value. Never hand-write a width in a template &mdash; use one of these.
    </p>
    <p class="text-secondary fs-7 mb-2">
        <code>w-em-{n}</code> &mdash; width only. Used to pin table column widths and the form controls inside
        them (cost inputs on the pack equipment-list screens, label and value columns on the campaign asset
        tables). Responsive variants exist: <code>w-em-{bp}-{n}</code>.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="vstack gap-1">
            {% for n, value in w_em_scale %}
                <div class="d-flex flex-wrap align-items-center gap-2">
                    <div class="w-em-{{ n }} bg-primary rounded py-2"></div>
                    <code class="fs-7">w-em-{{ n }}</code>
                    <span class="fs-7 text-secondary">{{ value }}</span>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        <code>styles.scss:576-600</code>. Note the scale is not contiguous &mdash; 3, 4, 5, 6, 8, 10, 12 only.
    </p>
    <p class="text-secondary fs-7 mb-2">
        <code>size-em-{n}</code> &mdash; square (width and height). The scale
        <strong>doubles</strong>, it does not increment. Used for image thumbnails. Responsive variants:
        <code>size-em-{bp}-{n}</code>.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap align-items-end gap-3">
            {% for n, value in size_em_scale %}
                <div class="text-center">
                    <div class="size-em-{{ n }} bg-primary-subtle border rounded"></div>
                    <code class="fs-7">size-em-{{ n }}</code>
                    <div class="fs-7 text-secondary">{{ value }}</div>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        <code>styles.scss:549-573</code>. Canonical use:
        <code>core/includes/list_about.html:61</code> (<code>img-fluid rounded size-em-5</code>) and
        <code>list_fighter_narrative_edit.html:23</code> (<code>size-em-4 size-em-md-5</code>).
    </p>
    <p class="text-secondary fs-7 mb-2">
        <code>sq-{n}</code> &mdash; square, linear, 1&ndash;6em. A separate scale from
        <code>size-em-*</code> because it increments rather than doubles; use it when you need a size the
        doubling scale skips over.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap align-items-end gap-3">
            {% for n, value in sq_scale %}
                <div class="text-center">
                    <div class="sq-{{ n }} bg-primary-subtle border rounded"></div>
                    <code class="fs-7">sq-{{ n }}</code>
                    <div class="fs-7 text-secondary">{{ value }}</div>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <code>styles.scss:753-758</code>. One use in the app: the share QR code at
        <code>core/includes/list.html:283</code>. There are no responsive variants.
    </p>
    <h3 class="h6 caps-label mb-2">Print</h3>
    <p class="text-secondary fs-7 mb-4">
        <code>break-inside-avoid</code> (<code>styles.scss:747</code>) sets
        <code>break-inside: avoid</code>, keeping a block off a print page boundary. Put it on every card that
        can appear in a printed roster &mdash; fighter cards, stash cards, blank cards, card-pair wrappers, the
        list header (8 uses across 6 files). It has no effect on screen, so there is nothing to preview; the
        rule is simply that a new card type in a printable grid must carry it.
    </p>
    <h3 class="h6 caps-label mb-2">Rules</h3>
    <table class="table table-sm table-borderless mb-0 fs-7">
        <thead>
            <tr>
                <th>Rule</th>
                <th>Why</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td>Pick the page shell first, then stack inside it</td>
                <td>The shell owns the outer gap; stacking a second wrapper around it double-spaces the page</td>
            </tr>
            <tr>
                <td>
                    <code>d-flex flex-column</code>, not <code>vstack</code>, when the column must size to its content
                </td>
                <td>
                    <code>vstack</code> sets <code>flex:1 1 auto</code> and stretches inside a flex row
                </td>
            </tr>
            <tr>
                <td>
                    Always add <code>flex-wrap</code> to an <code>hstack</code> that can overflow
                </td>
                <td>
                    <code>hstack</code> does not wrap; at 375px it forces a horizontal scrollbar
                </td>
            </tr>
            <tr>
                <td>
                    Start every grid child at <code>g-col-12</code>
                </td>
                <td>Mobile-first: one column at 375px, widen at <code>md</code>/<code>xl</code></td>
            </tr>
            <tr>
                <td>
                    Pair <code>border-{side}-{bp}-0</code> with <code>rounded-{side}-{bp}-0</code>, and close the wrapper gap at the same breakpoint
                </td>
                <td>Dropping the border without the radius leaves a visible notch between the joined cards</td>
            </tr>
            <tr>
                <td>Use a sizing scale rather than a literal width</td>
                <td>
                    <code>em</code> sizing follows the surrounding font size and survives the <code>fs-7</code> contexts
                </td>
            </tr>
            <tr>
                <td>
                    <code>break-inside-avoid</code> on every printable card
                </td>
                <td>Printed rosters split cards across pages otherwise</td>
            </tr>
        </tbody>
    </table>
</section>
```

**Rules established.** Pick the page shell first. `d-flex flex-column` not `vstack` when a column
must size to its content — `vstack` sets `flex: 1 1 auto` (which `hstack` does *not*) and its
`align-self: stretch` overrides the row's `align-items-*`; `list_row.html:5` hand-writes the long
form deliberately. `flex-wrap` on any `hstack` that can overflow. `align-items-baseline` only on
rows mixing type sizes. The metadata row uses split gaps, not a uniform `gap-2`. Every grid child
starts at `g-col-12`. **`auto-flow-dense` only has an effect when spans leave an actual hole** —
8/4/4 tiles exactly and demonstrates nothing; 8/6/4 does. Butt-joins are three levels and every
breakpoint suffix must agree. Never hand-write a pixel width. `break-inside-avoid` on every
printable card. `gap-5` is not an app convention — it appears once, as this page's own wrapper.
A chip that is an icon plus a bare number needs a `title`. Quote counts approximately in a
document that is itself part of the counted corpus.

**Source files.** `gyrinx/core/static/core/scss/styles.scss`; `core/includes/list_row.html`;
`list.html`; `blank_vehicle_card.html`; `list_about.html`; `list_notes.html`;
`core/list_fighter_narrative_edit.html`; `core/campaign/campaign_assets.html`;
`campaign_asset_detail.html`; `gyrinx/core/templatetags/custom_tags.py`; `gyrinx/models.py`;
`node_modules/bootstrap/scss/helpers/_stacks.scss`; `node_modules/bootstrap/scss/_grid.scss`.

**New context variables.** `w_em_scale`, `size_em_scale`, `sq_scale` (see §5). `spacing_scale` and
`ds_house_icon_svg` are unchanged.

**Cotton targets.** `c-badge` (the two metadata-row chips), `c-box` (every framed demo and tile),
`c-icon` (`bi-person`, `bi-star-fill`, `bi-list-ul` — **the star's `title` must survive the
migration**; a `c-icon` that swallows accessible names would silently regress `list_row.html`).
Two new candidates: **`c-layout.metadata-row`** (identical class strings in 7 files, the strongest
unification case here) and **`c-card-pair`** (three coordinated levels and six breakpoint-scoped
classes that must agree, hand-written in two places — the highest-risk copy-paste in the app).

### 4.6 `typography` — Typography and semantics (Group B)

**Purpose.** Show the type scale and the heading rules, including how to fake a heading in a demo
without wrecking the document outline. Absorbs the heading-semantics rules currently stated in
Principles and violated nine times over on the same page.

**Partial:** `core/debug/design_system/sections/typography.html`

```html
<!-- ============================================================ -->
<!-- TYPOGRAPHY AND SEMANTICS -->
<!-- ============================================================ -->
<section id="typography">
    <h2 class="h4 mb-3">
        Typography and semantics
        <a class="linked-secondary fs-7"
           href="#typography"
           aria-label="Permalink to Typography and semantics"><span aria-hidden="true">#</span></a>
    </h2>
    <p class="text-secondary fs-7 mb-3">
        Pick the heading <strong>level</strong> from the document outline, then the <strong>size</strong> from the
        type scale — two separate decisions that happen to be spelled with the same letters.
        Read this before starting a page or adding a section heading.
        Don't read it to size body text: body is the default and <code>fs-7</code> is the only step down.
    </p>
    <h3 class="h6 caps-label mb-2">Type scale (canonical)</h3>
    <p class="text-secondary fs-7 mb-2">
        Sizes are computed by Bootstrap from <code>$font-size-base</code>, not authored by hand.
        Site counts are from <code>gyrinx/core/templates</code>, 2026-07 — they are here so a row that
        nobody uses is visible as such.
    </p>
    <div class="table-responsive mb-2">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Name</th>
                    <th scope="col">Size</th>
                    <th scope="col">Derivation</th>
                    <th scope="col">Class</th>
                    <th scope="col">Use for</th>
                    <th class="text-end" scope="col">Sites</th>
                </tr>
            </thead>
            <tbody>
                {% for name, size, derivation, cls, use, sites in ds_type_scale %}
                    <tr>
                        <td>{{ name }}</td>
                        <td>{{ size }}</td>
                        <td class="text-secondary">{{ derivation }}</td>
                        <td>
                            {% if cls %}
                                <code>{{ cls }}</code>
                            {% else %}
                                <span class="text-secondary">(default)</span>
                            {% endif %}
                        </td>
                        <td>{{ use }}</td>
                        <td class="text-end">{{ sites }}</td>
                    </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <strong>Three sources, three answers — this table is the one that wins,</strong> because the
        measured tables below check it against the browser.
        <code>docs/DESIGN-SYSTEM.md</code> lists five rows and no <code>h1.h2</code>, but eight pages ship it;
        the spec is fixed in the same PR as this page.
        Both the spec and the old version of this table gave the Section row as 1rem — it is
        <strong>1.09rem</strong>; no <code>$h5-font-size</code> override exists in any SCSS entry point, so
        Bootstrap's <code>base * 1.25</code> applies.
        The reference comment in <code>_tokens.scss</code> gives <code>h1</code> as 2rem,
        <code>h1.h3</code> as 1.25rem and <code>caps-label</code> as 0.75rem — all three wrong, because
        Bootstrap derives them from a 0.875rem base, not 16px; that comment is fixed too.
        The <code>Sites</code> column counts <code>h1</code> with no size class as 8, not 11: three of the
        eleven were demo headings on this page, and this revision replaces them with <code>&lt;div&gt;</code>s.
        Of the remaining eight, four are debug/admin templates and four are real index pages.
        Still unresolved: <code>h2.h4</code> (1.31rem) is not in the scale at all, yet it is the section heading
        on this page (26 sites, 21 of them here). Either the scale gains a row or this page moves to
        <code>h2.h5</code>.
    </p>
    <h3 class="h6 caps-label mb-2">Page roles (live)</h3>
    <p class="text-secondary fs-7 mb-2">
        What each scale step looks like, and the markup that produces it. The previews below use size
        <em>classes</em> on <code>&lt;div&gt;</code>s, not real heading elements — see the demo rule further down.
    </p>
    <div class="border rounded p-3 vstack gap-2 mb-4">
        <div>
            <div class="h1 mb-0" style="line-height:1.2">Top-level index</div>
            <code class="fs-7 text-secondary">&lt;h1&gt; — Lists &amp; Gangs, Campaigns, Customisation</code>
        </div>
        <hr class="my-1">
        <div>
            <div class="h2 mb-0">Entity detail</div>
            <code class="fs-7 text-secondary">&lt;h1 class="h2"&gt; — Campaign, Pack, Battle, List detail</code>
        </div>
        <hr class="my-1">
        <div>
            <div class="h3 mb-0">Sub-page</div>
            <code class="fs-7 text-secondary">&lt;h1 class="h3"&gt; — Edit forms, settings, campaign sub-pages</code>
        </div>
        <hr class="my-1">
        <div>
            <div class="h5 mb-0">Section heading</div>
            <code class="fs-7 text-secondary">&lt;h2 class="h5 mb-0"&gt;</code>
        </div>
        <hr class="my-1">
        <div>
            <div class="h5 mb-0">Card header</div>
            <code class="fs-7 text-secondary">&lt;h3 class="h5 mb-0"&gt; — same size, one level deeper</code>
        </div>
        <hr class="my-1">
        <div>
            <span class="caps-label">Metadata label</span>
            <code class="fs-7 text-secondary d-block">&lt;div class="caps-label"&gt;</code>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <code>mb-0</code> on a heading is not decoration: a heading sitting inside a section header bar or a card
        header takes its spacing from the bar's padding. A standalone heading takes <code>mb-2</code>.
    </p>
    <h3 class="h6 caps-label mb-2">Heading sizes (measured)</h3>
    <p class="text-secondary fs-7 mb-2">
        <code>bootstrap/scss/_type.scss</code> declares <code>.h1 { @extend h1; }</code> — the size itself lives
        on the element in <code>_reboot.scss</code> — so the class and the element compile into one selector list
        and are identical by construction. That is what makes it safe for a demo to preview the class and leave
        the document outline alone.
        Computed values are read live from the rendered page, so they are the truth, not a claim; with
        JavaScript off the column stays as em dashes.
    </p>
    <div class="table-responsive mb-4">
        <table class="table table-sm table-borderless mb-0" id="headings-table">
            <thead>
                <tr>
                    <th scope="col">Element</th>
                    <th scope="col">Size class</th>
                    <th scope="col">SCSS</th>
                    <th scope="col">Computed</th>
                    <th scope="col">Preview</th>
                </tr>
            </thead>
            <tbody>
                <tr class="align-middle">
                    <td>
                        <code>&lt;h1&gt;</code>
                    </td>
                    <td>
                        <code>.h1</code>
                    </td>
                    <td>base * 2.5</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <div class="h1 mb-0" data-measure-target>Heading 1</div>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>&lt;h2&gt;</code>
                    </td>
                    <td>
                        <code>.h2</code>
                    </td>
                    <td>base * 2</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <div class="h2 mb-0" data-measure-target>Heading 2</div>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>&lt;h3&gt;</code>
                    </td>
                    <td>
                        <code>.h3</code>
                    </td>
                    <td>base * 1.75</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <div class="h3 mb-0" data-measure-target>Heading 3</div>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>&lt;h4&gt;</code>
                    </td>
                    <td>
                        <code>.h4</code>
                    </td>
                    <td>base * 1.5</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <div class="h4 mb-0" data-measure-target>Heading 4</div>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>&lt;h5&gt;</code>
                    </td>
                    <td>
                        <code>.h5</code>
                    </td>
                    <td>base * 1.25</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <div class="h5 mb-0" data-measure-target>Heading 5</div>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>&lt;h6&gt;</code>
                    </td>
                    <td>
                        <code>.h6</code>
                    </td>
                    <td>base * 1</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <div class="h6 mb-0" data-measure-target>Heading 6</div>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <code>.h6</code> is worth knowing about: <code>$h6-font-size</code> is <code>$font-size-base</code>
        unmodified, so it computes to body size exactly — it changes weight and margin but not size.
        The sub-headings on this page are <code>&lt;h3 class="h6 caps-label"&gt;</code> and take their size from
        <code>caps-label</code>, not from <code>h6</code>.
    </p>
    <h3 class="h6 caps-label mb-2">Font sizes</h3>
    <p class="text-secondary fs-7 mb-2">
        <code>.fs-1</code>–<code>.fs-6</code> come straight from Bootstrap's <code>$font-sizes</code> map, which
        is keyed to <code>$h1-font-size</code>…<code>$h6-font-size</code>. That makes <code>.fs-6</code> equal to
        body, not to 1rem — a distinction the old version of this table got wrong.
        <code>.fs-7</code> is ours, merged into the map in <code>styles.scss</code>.
    </p>
    <div class="table-responsive mb-2">
        <table class="table table-sm table-borderless mb-0" id="font-sizes-table">
            <thead>
                <tr>
                    <th scope="col">Class</th>
                    <th scope="col">Size</th>
                    <th scope="col">Computed</th>
                    <th scope="col">Preview</th>
                </tr>
            </thead>
            <tbody>
                <tr class="align-middle">
                    <td>
                        <code>.fs-1</code>
                    </td>
                    <td>base * 2.5</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-1" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.fs-2</code>
                    </td>
                    <td>base * 2</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-2" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.fs-3</code>
                    </td>
                    <td>base * 1.75</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-3" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.fs-4</code>
                    </td>
                    <td>base * 1.5</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-4" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.fs-5</code>
                    </td>
                    <td>base * 1.25</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-5" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.fs-6</code>
                    </td>
                    <td>base (0.875rem)</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-6" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.fs-7</code>
                    </td>
                    <td>base * 0.9 (custom)</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="fs-7" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle">
                    <td>
                        <code>.caps-label</code>
                    </td>
                    <td>0.875em of parent</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="caps-label" data-measure-target>The quick brown fox</span>
                    </td>
                </tr>
                <tr class="align-middle text-secondary">
                    <td>
                        <del><code>.small</code></del>
                    </td>
                    <td>0.875em of parent</td>
                    <td>
                        <code data-measure>—</code>
                    </td>
                    <td>
                        <span class="small" data-measure-target>The quick brown fox</span>
                        <span class="fs-7">— deprecated, use <code>.fs-7</code></span>
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-2">
        <code>.fs-7</code> is the only step down from body and is used 750 times.
        Both <code>.caps-label</code> and <code>.small</code> are sized in <code>em</code>, not <code>rem</code>,
        so they scale with whatever they sit in: <code>caps-label</code> measures ~0.77rem in a body-size
        container and ~0.69rem inside an <code>fs-7</code> one. The Type scale table above quotes the body-size
        figure.
    </p>
    <p class="text-secondary fs-7 mb-2">
        <strong>The <code>.small</code> class is deprecated but not gone.</strong> Six uses remain in
        <code>core/templates</code>: the struck-through demo row above, and five in
        <code>core/list/invitation_pack_setup.html</code> — which is also the only file still using the
        deprecated <code>text-muted</code> (all five of its remaining uses). One file, one cleanup; do it before
        citing either deprecation as complete.
    </p>
    <p class="text-secondary fs-7 mb-4">
        <strong>The <code>&lt;small&gt;</code> element is a different question and is not settled.</strong>
        It renders at the same 0.875em the deprecated class does, and 22 sites use it — the activity-timeline
        row (<code>core/includes/campaign_action_item.html</code>) is the main one.
        Either it means "de-emphasised metadata" and should stay, or it is <code>fs-7</code> spelled differently
        and should go. Normalise it when the timeline becomes a component; don't add new ones meanwhile.
    </p>
    <h3 class="h6 caps-label mb-2">Font weights</h3>
    <div class="vstack gap-1 mb-2">
        <p class="fw-light mb-0">
            <code>.fw-light (300)</code> – The quick brown fox jumps over the lazy dog
        </p>
        <p class="fw-normal mb-0">
            <code>.fw-normal (400)</code> – The quick brown fox jumps over the lazy dog
        </p>
        <p class="fw-medium mb-0">
            <code>.fw-medium (500)</code> – The quick brown fox jumps over the lazy dog
        </p>
        <p class="fw-semibold mb-0">
            <code>.fw-semibold (600)</code> – The quick brown fox jumps over the lazy dog
        </p>
        <p class="fw-bold mb-0">
            <code>.fw-bold (700)</code> – The quick brown fox jumps over the lazy dog
        </p>
    </div>
    <p class="text-secondary fs-7 mb-4">
        In practice only two of the five matter: <code>fw-semibold</code> for a label or a name that must stand
        out inside a dense row, and the default for everything else. Reach for weight before you reach for size —
        the type scale has one step below body and no steps in between.
        Bootstrap also emits <code>.fw-lighter</code> and <code>.fw-bolder</code>; neither has a use here.
    </p>
    <h3 class="h6 caps-label mb-2">caps-label</h3>
    <div class="border rounded p-3 mb-2">
        <span class="caps-label">Section label</span>
        <span class="text-secondary fs-7 ms-2">– <code>.caps-label</code>: small, uppercase, semibold, tracked
        (<code>letter-spacing: 0.03em</code>). For section sub-headers and metadata labels. Never compose it by
        hand out of <code>text-uppercase</code> plus a colour and a weight.</span>
    </div>
    <p class="text-secondary fs-7 mb-4">
        144 sites — the metadata-label vocabulary for campaign info columns, stat rows and the sub-headings on
        this page. Listed again in the
        <a class="linked-secondary" href="#custom-css">Custom CSS reference</a> as a cross-reference; this is the
        demo, that is the index.
        <strong>Two honest notes.</strong> Its SCSS <code>@extend</code>s <code>.small</code> and
        <code>.text-muted</code>, both of which this page marks deprecated — enforced at call sites, not inside
        <code>styles.scss</code>; harmless today, worth cleaning when the file is next touched.
        And nine sites still hand-roll it anyway, in two different recipes
        (<code>text-uppercase fs-7 fw-light text-secondary</code> in the notes and fighter-card includes,
        <code>text-uppercase fs-7 fw-semibold text-secondary</code> in the pack templates) — so the rule below is
        aspirational, not a description of the codebase.
    </p>
    <h3 class="h6 caps-label mb-2">Heading semantics</h3>
    <p class="text-secondary fs-7 mb-2">
        Level is structure and belongs to the document. Size is presentation and belongs to a class.
        Every rule below exists because those two get conflated.
    </p>
    <div class="table-responsive mb-2">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Rule</th>
                    <th scope="col">Do</th>
                    <th scope="col">Don't</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>One <code>&lt;h1&gt;</code> per page</td>
                    <td>
                        <code>&lt;h1 class="h3"&gt;Edit fighter&lt;/h1&gt;</code>, once, in the page shell
                    </td>
                    <td>a second <code>&lt;h1&gt;</code> inside a card, a panel or an include</td>
                </tr>
                <tr>
                    <td>Never skip a level</td>
                    <td>
                        <code>h1</code> → <code>h2</code> → <code>h3</code>
                    </td>
                    <td>
                        <code>h1</code> → <code>h3</code> because <code>h2</code> looked too big
                    </td>
                </tr>
                <tr>
                    <td>Change the size, not the level</td>
                    <td>
                        <code>&lt;h2 class="h5"&gt;</code>
                    </td>
                    <td>
                        <code>&lt;h5&gt;</code> used as a section heading under an <code>h1</code>
                    </td>
                </tr>
                <tr>
                    <td>Headings inside a demo</td>
                    <td>
                        <code>&lt;div class="h2"&gt;</code> — same size, no outline entry
                    </td>
                    <td>a real <code>&lt;h1&gt;</code>/<code>&lt;h2&gt;</code> element in sample markup</td>
                </tr>
                <tr>
                    <td>Heading inside a bar or card header</td>
                    <td>
                        <code>mb-0</code> — the container's padding is the spacing
                    </td>
                    <td>
                        <code>mb-3</code>, which double-spaces the bar
                    </td>
                </tr>
                <tr>
                    <td>Non-visible page title</td>
                    <td>
                        <code>&lt;h1 class="visually-hidden"&gt;</code> — as on the dice roller
                    </td>
                    <td>omitting the <code>&lt;h1&gt;</code> because the design has no room for it</td>
                </tr>
            </tbody>
        </table>
    </div>
    <p class="text-secondary fs-7 mb-4">
        <strong>Why every demo in this section previews a class and not an element.</strong>
        A design-system page is one page with dozens of headings in its samples. Render them as real elements and
        the page has a screen-reader outline that is pure noise — while telling the reader to have one
        <code>&lt;h1&gt;</code>. Rendering <code>&lt;div class="h2"&gt;</code> gives a pixel-identical preview and
        a clean outline, and the escaped code beside it carries the element the reader should actually write.
        This section is where you would expect the exception, because the heading level is the subject; it does
        not need one.
        <strong>Not yet true of the whole page:</strong> the Containers, Supporter badges and Page patterns
        sections still render real <code>&lt;h1&gt;</code>/<code>&lt;h2&gt;</code> elements in their samples.
        Converting them is a mechanical follow-up.
    </p>
    <h3 class="h6 caps-label mb-2">Base size, print and breakpoints</h3>
    <div class="table-responsive mb-0">
        <table class="table table-sm table-borderless mb-0 fs-7">
            <thead>
                <tr>
                    <th scope="col">Context</th>
                    <th scope="col">Base</th>
                    <th scope="col">Set in</th>
                    <th scope="col">Consequence</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>Screen</td>
                    <td>0.875rem</td>
                    <td>
                        <code>screen.scss</code>
                    </td>
                    <td>14px at browser defaults; every size above is derived from it</td>
                </tr>
                <tr>
                    <td>Print</td>
                    <td>1rem</td>
                    <td>
                        <code>print.scss</code>
                    </td>
                    <td>
                        the scale is ~14% larger than screen, but the same file sets
                        <code>body { zoom: 50% }</code>, so rendered text ends up smaller — check the print view,
                        don't reason from the base alone
                    </td>
                </tr>
                <tr>
                    <td>Print (classic cards)</td>
                    <td>1rem</td>
                    <td>
                        <code>print_classic.scss</code>
                    </td>
                    <td>no zoom here, so the whole scale really does grow ~14% on paper</td>
                </tr>
                <tr>
                    <td>Responsive step-up</td>
                    <td>—</td>
                    <td>
                        <code>styles.scss</code>
                    </td>
                    <td>
                        a custom <code>@each</code> over <code>$grid-breakpoints</code> emits
                        <code>.fs-{bp}-normal</code> for every breakpoint; zero uses — treat as dead until
                        something needs it
                    </td>
                </tr>
            </tbody>
        </table>
    </div>
</section>
```

**Rules established.** Level is structure, size is presentation. One `<h1>` per page — use
`<h1 class="visually-hidden">` (as `core/dice.html:17` does) rather than omitting it. Never skip
levels. Demo markup previews a size class on a `<div>`, never a real heading element, and this
section takes no exception for itself. `mb-0` on a heading inside a bar or card header. `fs-7` is
the only step down. `em`-sized classes scale with their container — quote them as a ratio and only
give a rem figure alongside the container it was measured in. `.fs-6` equals body, not 1rem. Type
sizes are never authored as literals. **Where the page, the spec and the `_tokens.scss` comment
disagree, the measured table wins.** JS-populated cells ship a visible em-dash placeholder.

**Corrections this section lands.** Section row is **1.09rem**, not the 1rem in
`docs/DESIGN-SYSTEM.md` (no `$h5-font-size` override exists). `_tokens.scss`'s reference comment
gives `h1` 2rem, `h1.h3` 1.25rem and `caps-label` 0.75rem — all three wrong, because Bootstrap
derives from a 0.875rem base. `print.scss` sets a 1rem base *and* `body { zoom: 50% }`, so print
text is smaller than screen, not 14% larger.

**Divergences for the migration to normalise.** `core/list/invitation_pack_setup.html` holds five
of the six surviving `.small` uses **and** all five surviving `text-muted` uses in
`core/templates` — one file, and both deprecations become genuinely complete. Nine templates
hand-roll `caps-label` in two incompatible recipes (`fw-light` in `list_notes.html:59` and
`fighter_card_content.html:353`; `fw-semibold` in `pack.html` ×3 and `pack_archived.html:18`; a
bare `<strong>` in `campaign_lists.html:30`). `.caps-label`'s SCSS `@extend`s `.small` and
`.text-muted`, both deprecated by this page.

**Source files.** `gyrinx/core/static/core/scss/styles.scss`; `_tokens.scss`; `screen.scss`;
`print.scss`; `print_classic.scss`; `docs/DESIGN-SYSTEM.md`;
`core/includes/campaign_action_item.html`; `core/list/invitation_pack_setup.html`;
`core/pack/packs.html`; `core/includes/list_notes.html`; `fighter_card_content.html`;
`node_modules/bootstrap/scss/_variables.scss`, `_type.scss`, `_reboot.scss`.

**New context variables.** `ds_type_scale` (see §5).

**Cotton targets.** **`c-heading`** — the component that makes the level/size split unforgeable:
`<c-heading level="2" size="h5">` renders `<h2 class="h5">`; a `demo` prop renders
`<div class="h2">` so sample markup never enters the outline, enforcing the demo rule in one place
instead of restating it in every section. **`c-caps-label`** — 144 hand-written sites plus 9
hand-rolled near-misses in two recipes; the wrapper collapses both, and is where the `.small` /
`.text-muted` `@extend` cleanup can happen without touching call sites. **`c-page-title`** (owned
by `#page-headers`) should take the page *role* — index / entity / sub-page — rather than a size
class, so the scale is chosen by meaning.

### 4.7 `icons` — Icons (Group B, kind: cotton)

**Purpose.** Give the canonical icon for each recurring action so two engineers independently pick
the same one, and document the component that now owns the naming rule.

**Partial:** `core/debug/design_system/sections/icons.html`

```html
<section id="icons">
    <h2 class="h4 mb-3">Icons</h2>
    <p class="text-secondary fs-7 mb-3">
        Bootstrap Icons, always in the <strong>hyphenated single-class form</strong>:
        <code>bi-pencil</code>, never <code>bi bi-pencil</code>. Reach for the
        <em>semantic name</em> below before picking a glyph — the point of the map is that two
        people who both need &ldquo;the delete icon&rdquo; land on the same one without
        conferring. Icons are decoration: they repeat a label, they never replace it. If you are
        about to ship an icon with no adjacent text and no accessible name on the control, stop —
        that is a bug, not a style.
    </p>
    <h3 class="h6 caps-label mb-2">Semantic names</h3>
    <p class="text-secondary fs-7 mb-2">
        The canonical set. <code>confirm</code> and <code>save</code> deliberately resolve to the
        same glyph — they are different intents that read identically, and forcing a distinction
        would invent one.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="table-responsive">
            <table class="table table-sm table-borderless mb-0 fs-7">
                <thead>
                    <tr>
                        <th scope="col" class="text-center">Icon</th>
                        <th scope="col">Semantic name</th>
                        <th scope="col">Class</th>
                        <th scope="col">Use it for</th>
                    </tr>
                </thead>
                <tbody class="table-group-divider">
                    {% for name, icon_class, meaning in icon_semantic_map %}
                        <tr>
                            <td class="text-center fs-4 lh-1 py-1">
                                <i class="{{ icon_class }}" aria-hidden="true"></i>
                            </td>
                            <td>
                                <code>{{ name }}</code>
                            </td>
                            <td>
                                <code>{{ icon_class }}</code>
                            </td>
                            <td>{{ meaning }}</td>
                        </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Written as <code>&lt;c-icon name="edit" /&gt;</code>, which emits exactly
        <code>&lt;i class="bi-pencil" aria-hidden="true"&gt;&lt;/i&gt;</code> — the same markup
        shown in every preview on this page.
    </p>
    <h3 class="h6 caps-label mb-2">Secondary icons</h3>
    <p class="text-secondary fs-7 mb-2">
        Recurring glyphs that carry a settled meaning but are not in the semantic map. Use the raw
        Bootstrap name; if one of these starts appearing in a third context, promote it.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap gap-3 fs-4">
            {% for icon_class, label in extra_icons %}
                <div class="text-center">
                    <div>
                        <i class="{{ icon_class }}" aria-hidden="true"></i>
                    </div>
                    <code class="fs-7 text-secondary">{{ icon_class }}</code>
                    <div class="fs-7 text-secondary">{{ label }}</div>
                </div>
            {% endfor %}
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        The twelve most-used icons outside the semantic map, counted across the template estate on
        21 July 2026 — not a wishlist. The count is a hand-taken snapshot and will drift; treat the
        ordering as indicative and the meanings as binding.
    </p>
    <h3 class="h6 caps-label mb-2">Raw and dynamic names</h3>
    <p class="text-secondary fs-7 mb-2">
        Anything from the Bootstrap Icons set works. A leading <code>bi-</code> is tolerated and
        stripped, so <code>name="heartbreak"</code> and <code>name="bi-heartbreak"</code> are the
        same icon — prefer the short form. Names may be computed: a die face is
        <code>{% verbatim %}bi-dice-{{ n }}{% endverbatim %}</code> at every value.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap gap-3 fs-4">
            <div class="text-center">
                <div>
                    <i class="bi-heartbreak" aria-hidden="true"></i>
                </div>
                <code class="fs-7 text-secondary">heartbreak</code>
                <div class="fs-7 text-secondary">Kill a fighter</div>
            </div>
            <div class="text-center">
                <div>
                    <i class="bi-truck" aria-hidden="true"></i>
                </div>
                <code class="fs-7 text-secondary">truck</code>
                <div class="fs-7 text-secondary">Vehicle</div>
            </div>
            <div class="text-center">
                <div>
                    <i class="bi-person-bounding-box" aria-hidden="true"></i>
                </div>
                <code class="fs-7 text-secondary">person-bounding-box</code>
                <div class="fs-7 text-secondary">Crew</div>
            </div>
            <div class="text-center">
                <div>
                    <i class="bi-dice-1" aria-hidden="true"></i>
                    <i class="bi-dice-3" aria-hidden="true"></i>
                    <i class="bi-dice-6" aria-hidden="true"></i>
                </div>
                <code class="fs-7 text-secondary">{% verbatim %}dice-{{ n }}{% endverbatim %}</code>
                <div class="fs-7 text-secondary">Computed name</div>
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        A one-off glyph does not earn a semantic name. Add one only when the same intent recurs in
        an unrelated part of the app.
    </p>
    <h3 class="h6 caps-label mb-2">Icons in controls</h3>
    <p class="text-secondary fs-7 mb-2">
        The icon never carries the accessible name — the button or link does. A labelled control
        needs nothing extra. An icon-only control needs a name of its own, and there are two
        shapes in use: <code>aria-label</code> on the control (the common one), or
        <code>visually-hidden</code> text plus a <code>title</code> for sighted users. Either is
        fine; pick whichever the surrounding component already uses.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-wrap align-items-center gap-2">
            <button type="button" class="btn btn-primary btn-sm">
                <i class="bi-plus-lg" aria-hidden="true"></i> Add fighter
            </button>
            <button type="button" class="btn btn-success btn-sm">
                <i class="bi-check-lg" aria-hidden="true"></i> Save
            </button>
            <div class="btn-group">
                <a href="#icons" class="btn btn-outline-secondary btn-sm">
                    <i class="bi-pencil" aria-hidden="true"></i> Edit
                </a>
                <button type="button"
                        class="btn btn-outline-secondary btn-sm dropdown-toggle dropdown-toggle-split"
                        data-bs-toggle="dropdown"
                        aria-expanded="false">
                    <i class="bi-three-dots-vertical" aria-hidden="true"></i>
                    <span class="visually-hidden">Toggle Dropdown</span>
                </button>
                <ul class="dropdown-menu">
                    <li>
                        <span class="dropdown-item-text text-secondary fs-7">Nothing here — demo only</span>
                    </li>
                </ul>
            </div>
            <a href="#icons" class="btn btn-secondary btn-sm" title="Print">
                <i class="bi-printer" aria-hidden="true"></i>
                <span class="visually-hidden">Print</span>
            </a>
            <div class="btn-group">
                <button type="button"
                        class="btn btn-outline-secondary btn-sm px-2"
                        aria-label="Decrease XP">
                    <i class="bi-dash-lg" aria-hidden="true"></i>
                </button>
                <button type="button"
                        class="btn btn-outline-secondary btn-sm px-2"
                        aria-label="Increase XP">
                    <i class="bi-plus-lg" aria-hidden="true"></i>
                </button>
            </div>
            <a href="#icons" class="icon-link linked">
                <i class="bi-box-seam" aria-hidden="true"></i> Content pack
            </a>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        The split-button toggle and the print control name themselves with
        <code>visually-hidden</code> text (<code>core/includes/fighter_card_content.html</code>,
        <code>core/includes/list.html</code> — where print is a link to the print-config page and
        is hidden below <code>sm</code>). The stepper pair uses <code>aria-label</code>
        (<code>core/includes/number_stepper.html</code>), which is the more common form: of the 39
        icon-only controls in the app, 22 are named and most of those use
        <code>aria-label</code>. A <code>title</code> on its own is a fallback, not a name — it is
        unreliable for screen readers and invisible on touch.
    </p>
    <h3 class="h6 caps-label mb-2">Size and colour</h3>
    <p class="text-secondary fs-7 mb-2">
        Icons are text. They inherit <code>font-size</code> and <code>currentColor</code> from
        their parent — never set a pixel size, and never put a colour class on the icon that is
        not already true of the thing beside it.
    </p>
    <div class="border rounded p-3 mb-2 vstack gap-3">
        <div class="d-flex flex-wrap align-items-baseline gap-3">
            <span class="fs-7"><i class="bi-crosshair" aria-hidden="true"></i> fs-7 — table cells, metadata rows</span>
            <span><i class="bi-crosshair" aria-hidden="true"></i> body — buttons, links, nav</span>
            <span class="fs-4"><i class="bi-crosshair" aria-hidden="true"></i> fs-4 — icon galleries, empty states</span>
        </div>
        <div class="d-flex flex-wrap gap-3">
            <span><i class="bi-exclamation-triangle text-warning" aria-hidden="true"></i> Injured</span>
            <span><i class="bi-heartbreak text-danger" aria-hidden="true"></i> Dead</span>
            <span><i class="bi-check-lg text-success" aria-hidden="true"></i> Active</span>
            <span class="text-secondary"><i class="bi-dot" aria-hidden="true"></i> Neutral (inherits)</span>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Colour on an icon signals the same state as the badge or alert it sits with — warning for
        injured or captured, danger for dead, success for active. It always repeats a state that
        is already in the text, never replaces it. A coloured icon with no state behind it is
        decoration, and decoration does not get colour.
    </p>
    <h3 class="h6 caps-label mb-2">Spacing</h3>
    <div class="border rounded p-3 mb-2 vstack gap-2">
        <div>
            <button type="button" class="btn btn-primary btn-sm">
                <i class="bi-plus-lg" aria-hidden="true"></i> Add
            </button>
            <span class="fs-7 text-secondary ms-2">Inside a button or link: a plain space.</span>
        </div>
        <div>
            <a href="#icons" class="icon-link linked"><i class="bi-arrow-clockwise" aria-hidden="true"></i> Retry</a>
            <span class="fs-7 text-secondary ms-2">
                <code>icon-link</code> supplies the gap itself.
            </span>
        </div>
        <div>
            <a href="#icons" class="nav-link p-0 d-inline"><i class="bi-house me-2" aria-hidden="true"></i>Overview</a>
            <span class="fs-7 text-secondary ms-2">Sidebar nav rows: <code>me-2</code>, no space.</span>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        Three idioms, one rule: pick whichever the surrounding component already uses and do not
        mix them in the same row. The sidebar form is
        <code>core/includes/account_sidebar.html</code>.
    </p>
    <h3 class="h6 caps-label mb-2">House icons</h3>
    <p class="text-secondary fs-7 mb-2">
        Not a Bootstrap Icon — an inline SVG badge rendered next to a house's name (gang rows,
        list headers, house filters). Emit it with the
        <code>{% templatetag openblock %} house_icon house {% templatetag closeblock %}</code>
        template tag; it inherits the surrounding text colour and sits comfortably alongside the
        name. Currently gated to the <strong>House Icons Alpha</strong> group. The examples below
        show the badge at body and compact (<code>fs-7</code>) sizes.
    </p>
    <div class="border rounded p-3 mb-2">
        <div class="d-flex flex-column gap-2">
            <div>Squat Prospectors{{ ds_house_icon_svg }}</div>
            <div class="text-secondary fs-7">
                House name at <code>fs-7</code>{{ ds_house_icon_svg }}
            </div>
        </div>
    </div>
    <p class="text-secondary fs-7 mb-3">
        See <code>.house-icon</code> in the Custom CSS reference for the scaling rule that keeps
        it on the text baseline.
    </p>
    <h3 class="h6 caps-label mb-2">Rules</h3>
    <div class="border rounded p-3 mb-3">
        <div class="table-responsive">
            <table class="table table-sm table-borderless mb-0 fs-7">
                <thead>
                    <tr>
                        <th scope="col">Rule</th>
                        <th scope="col">Do</th>
                        <th scope="col">Not</th>
                    </tr>
                </thead>
                <tbody class="table-group-divider">
                    <tr>
                        <td>Class form</td>
                        <td>
                            <code>&lt;i class="bi-pencil"&gt;</code>
                        </td>
                        <td>
                            <code>&lt;i class="bi bi-pencil"&gt;</code>
                        </td>
                    </tr>
                    <tr>
                        <td>Naming</td>
                        <td>
                            Semantic name (<code>name="delete"</code>)
                        </td>
                        <td>A different glyph per page for the same intent</td>
                    </tr>
                    <tr>
                        <td>Accessibility</td>
                        <td>
                            Always <code>aria-hidden="true"</code>; the control carries the name
                        </td>
                        <td>
                            <code>aria-label</code> on the <code>&lt;i&gt;</code> itself
                        </td>
                    </tr>
                    <tr>
                        <td>Icon-only control</td>
                        <td>
                            <code>aria-label</code> on the control, or <code>visually-hidden</code>
                            text plus <code>title</code>
                        </td>
                        <td>
                            A bare glyph, or <code>title</code> alone
                        </td>
                    </tr>
                    <tr>
                        <td>Size</td>
                        <td>
                            Inherit; <code>fs-7</code> compact, <code>fs-4</code> featured
                        </td>
                        <td>
                            Pixel sizes, <code>width</code>/<code>height</code>
                        </td>
                    </tr>
                    <tr>
                        <td>Colour</td>
                        <td>Inherit, or match the state beside it</td>
                        <td>Colour for emphasis or variety</td>
                    </tr>
                    <tr>
                        <td>Meaning</td>
                        <td>Icon repeats the label</td>
                        <td>Icon replaces the label</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>
    <h3 class="h6 caps-label mb-2">On the record</h3>
    <div class="border rounded p-3">
        <ul class="fs-7 mb-0">
            <li>
                <strong><code>bi-person-add</code> is not a Bootstrap Icons name.</strong> Three
                sites render an empty box today: <code>core/includes/list.html</code> (lines 106
                and 358) and this page's own list/detail header demo. The fix is not
                <code>bi-person-plus</code> — the semantic map already owns
                <code>add</code> as <code>bi-plus-lg</code>, and adding a fighter is an add.
            </li>
            <li>
                <strong>Same intent, two glyphs — the drift the map exists to end.</strong>
                <code>bi-plus</code> (16 uses) against <code>bi-plus-lg</code> (61);
                <code>bi-dash</code> (27) against <code>bi-dash-lg</code> (5);
                <code>bi-check2</code> (4) against <code>bi-check-lg</code> (24);
                <code>bi-three-dots</code> (4) against <code>bi-three-dots-vertical</code> (7);
                <code>bi-x</code>, <code>bi-x-lg</code> and <code>bi-x-circle</code> all in play.
                Note <code>bi-dash</code> earns its place in the secondary list on meaning, not on
                being a smaller dash: it marks a secondary weapon profile.
            </li>
            <li>
                <strong>17 icon-only controls have no accessible name at all</strong> — out of 39
                in the app. Two of them are on this page (the action-menu demos in
                <em>Inline action menus</em> and <em>Page patterns</em>), so this section is not
                pointing at somebody else's code. The chevron in the home-page and pack-listing
                row links is the most-repeated instance.
            </li>
            <li>
                <strong>27 of 627 icon elements carry <code>aria-hidden</code>.</strong> The rest
                are decorative and should have it. The component supplies it unconditionally, so
                this corrects itself as sites migrate — nothing needs a sweep.
            </li>
            <li>
                <strong>Two icons in the app are content, not decoration.</strong>
                <code>core/dice.html</code> labels its rolled die with <code>aria-label</code> but
                omits <code>role="img"</code>, which its own not-yet-rolled sibling two lines
                below does set; <code>core/templates/core/list_fighter_equipment_sell.html</code>
                renders the same die with no name whatsoever. There is deliberately no opt-out
                from <code>aria-hidden</code>, so both should name a wrapping element rather than
                the glyph. Two dice are not a case for an <code>alt</code> prop.
            </li>
        </ul>
    </div>
</section>
```

**Rules established.** Hyphenated single class always. Prefer a semantic name; add one only when
the intent recurs in an unrelated part of the app. Icons are always `aria-hidden="true"` with no
opt-out; the control carries the name. An icon-only control needs `aria-label` **or**
`visually-hidden` + `title` — `title` alone is a fallback, not a name. An icon repeats the label,
never replaces it. Icons inherit size and colour; never set pixel sizes. Colour repeats a state
already in the text. Three spacing idioms (plain space in a button, `icon-link` for links, `me-2`
in sidebar nav rows) — never mixed in one row. Names may be computed. A leading `bi-` is stripped.
`confirm` and `save` intentionally share a glyph. **Cotton tags shown as sample text must be
HTML-escaped** (`&lt;c-icon …&gt;`) because cotton compiles literal `<c-…>` even inside `<code>`.
**Django variable syntax shown as sample text must be `{% verbatim %}`-wrapped** or it silently
renders as the empty string. Non-interactive text in a `dropdown-menu` uses `dropdown-item-text`.
Usage counts printed on the page carry the date they were taken.

**Divergences for the migration to normalise.** All five "On the record" bullets are verified. The
`bi-person-add` bug is live in `core/includes/list.html:106,358`. The 17 nameless icon-only
controls do **not** self-correct on migration to `c-icon`, because the missing name lives on the
button — the two on this page (`design_system.html:1174`, `:1257`) should be fixed in the same PR
so the page is not self-refuting.

**Source files.** `gyrinx/templates/cotton/icon.html`; `core/includes/list.html`;
`fighter_card_content.html`; `account_sidebar.html`; `number_stepper.html`;
`fighter_card_stash.html`; `gear_assign_name.html`; `core/includes/home/list_row.html`;
`core/dice.html`; `core/list_fighter_equipment_sell.html`; `core/list_fighter_weapon_edit.html`;
`gyrinx/core/templatetags/custom_tags.py`; `gyrinx/settings.py`.

**New context variables.** `icon_semantic_map` (**replaces** `common_icons`); `extra_icons`
(**revised** — see §5).

**Cotton targets.** `c-icon` (the whole section is its gallery; every preview already emits its
exact output, so conversion is mechanical); `c-btn` (the "Icons in controls" demo — note it must
express all **three** naming shapes, not just a `label` prop, or 22 existing call sites become
non-conformant); `c-box`; a table component would own the `table-responsive` wrapper.

---

### 4.8 `buttons` — Button (Group C, kind: cotton)

**Purpose.** Pick the right button colour and size for the context, every time — and use the
component that now encodes it. This is the first-class gallery for `c-btn`, with a generated props
table.

**Partial:** `core/debug/design_system/sections/buttons.html`

This section's markup was authored in the same pass as those above but is not reproduced here,
because the authoring output was truncated mid-block and this document does not carry partial
markup. Reconstruct it from the sub-block list and rules below, which are complete; every
sub-block's live source is cited so the markup can be lifted verbatim from the app.

**Sub-blocks, in order.**

1. **Element choice** — `href` present renders `<a class="btn">`, absent renders `<button>`. That
   is the only thing that decides the element; there is no `tag` prop. A control that changes
   server state is a `<button type="submit">` inside a POST form; a control that only navigates is
   an `<a>`, so it can be middle-clicked and bookmarked.
2. **Variant semantics** — a live row of the five variants plus a three-column table:
   `primary` = navigate/open (Add fighter, Add vehicle, Start, Reopen, Search); `success` =
   create/save/confirm (Save, Create, Accept, Add Packs & Gang); `secondary` = cancel/clear/neutral
   header action (Cancel, Clear, Edit, Print, Unarchive); `danger` = destructive or navigating to a
   destructive confirm (Delete, End Campaign); `link` = an inline action that must be a POST but
   read as a link (Mark read, Archive, Decline, Disable skill).
3. **Size** — **there is no implicit `btn-sm`.** Full size is the default and is correct for a form
   page's submit row; `btn-sm` is explicit and belongs in headers, table rows, card footers, inline
   add-rows and filter bars. Never mix sizes within one row.
4. **Page-header toolbar (`btn-sm`)** — `nav hstack gap-1 flex-wrap`, from
   `core/includes/list.html:92-165` and `core/campaign/campaign.html:62-95`.
5. **Form submit row (full size)** — Save first, cancel second as `btn-link`, from
   `core/campaign/campaign_end.html:36-39`.
6. **Destructive confirmation (full size)** — `btn-danger` on its own page, from
   `campaign_end.html:37`; constructive lifecycle submits use `btn-success`
   (`campaign_start.html:43`); a submit whose *result* is a warning state takes `btn-warning`
   (`core/list_fighter_mark_captured.html:41`).
7. **Dense inline submit (`btn-sm`)** — the one place `btn-success btn-sm` is right, from
   `core/pack/pack_lists.html:107`, `core/list/list_invitations.html:32,38`,
   `core/campaign/campaign_add_lists.html:43-48`.
8. **Inline action inside a POST form (`btn-link`)** — `btn btn-link btn-sm p-0 align-baseline`
   plus `link-secondary` / `link-danger`, each action its own one-field `<form>` with a `next`
   hidden input, separated by the `{% dot %}` tag which emits `&nbsp;·&nbsp;` (so the row needs no
   `gap`). From `core/includes/notification_list_item.html:30-58` and
   `core/list_fighter_skills_edit.html:24-37`.
9. **Icon-only button** — `title` plus `visually-hidden`, or `aria-label`; see `#icons`.
10. **Outline variants** — the one place they are correct is a segmented control, where outline
    means "selected", not "secondary".
11. **Disabled** — `<button>` gets the attribute; `<a>` gets `.disabled` + `aria-disabled="true"`.
12. **Loading** — a *composition*, not a prop: disabled + spinner + present-tense verb ("Saving…").
13. **Full colour palette** — the three further fills that exist in the estate, documented as the
    exception rather than spare weight.
14. **Context guide table** — resolving the `btn-success`-in-toolbars contradiction.

**Rules established.** Variant semantics as above. **Never `btn-success` in a page header** —
nothing there saves anything; every header control is a navigation. Two `btn-primary` buttons side
by side is normal; a `btn-success` that commits nothing is a bug. Icons go in the slot, not a prop.
Loading is a composition. **Security note from the component's own docstring: never pass
user-controlled data with the `:` prefix — cotton `mark_safe()`s `{{ attrs }}` without escaping.
Use `title="{{ fighter.name }}"`, which is autoescaped.** `<c-cancel>` takes `:url="return_url"`
explicitly — `return_url` is a *declared* prop and does not inherit from page context, so omitting
it silently falls back to the referer.

**Divergence for the migration to normalise.** The page says "never use `btn-success` in toolbars"
(`design_system.html:859-864`); `docs/DESIGN-SYSTEM.md:216` lists "Lifecycle action |
`btn btn-success btn-sm` | Start Campaign". Both are reconcilable — a *toolbar* action navigates, a
*lifecycle submit* commits — but they have never been reconciled in writing. This section does it,
and the spec is corrected in the same PR.

**Source files.** `gyrinx/templates/cotton/btn.html`; `cancel.html`; `core/includes/list.html`;
`core/campaign/campaign.html`; `campaign_end.html`; `campaign_start.html`;
`core/list_fighter_mark_captured.html`; `core/pack/pack_lists.html`;
`core/list/list_invitations.html`; `core/campaign/campaign_add_lists.html`;
`core/includes/notification_list_item.html`; `core/list_fighter_skills_edit.html`.

**New context variables.** None beyond the `COMPONENT_PROPS` registry entry for `btn` (§5).

**Cotton targets.** `c-btn` (this *is* its gallery), `c-cancel`, `c-icon`, `c-box`.

---

## 5. View changes

`gyrinx/core/views/debug.py`. **19 new context variables, 2 revised, 1 removed**, plus the
`DESIGN_SYSTEM` manifest and the `COMPONENT_PROPS` registry. Every value below is a Python literal
or a `SimpleNamespace` — **no database access, renders logged out**.

### 5.1 Removed

- **`common_icons`** — superseded by `icon_semantic_map`, which adds the semantic name as a third
  element so the map is greppable by intent.

### 5.2 Revised in place

- **`extra_icons`** — the current list contains three icons with **zero uses** in the estate
  (`bi-wrench`, `bi-lightning`, `bi-link-45deg`) and labels that mostly echo the class name. It
  also omits `bi-dash`, which at 27 uses is the most-used non-semantic icon in the app. Replace
  with (counts verified 2026-07-21, `*.html` excluding the design-system page):

  ```python
  extra_icons = [
      ("bi-dash", "Secondary weapon profile"),          # 27
      ("bi-arrow-clockwise", "Retry or refresh"),       # 16
      ("bi-arrow-right", "Forward or next step"),       # 15
      ("bi-star", "Stars on a gang or campaign"),       # 10
      ("bi-chevron-right", "Drill into a row"),         # 10
      ("bi-arrow-90deg-up", "Linked or default item"),  #  9
      ("bi-dot", "Content-pack marker"),                #  9
      ("bi-crosshair", "Weapon or weapon accessory"),   #  8
      ("bi-printer", "Print view"),                     #  5
      ("bi-list-ul", "A gang list"),                    #  5
      ("bi-eye-slash", "Unlisted"),                     #  5
      ("bi-flag", "Battle or mission"),                 #  4
  ]
  ```

  The template currently unpacks the label and throws it away (`design_system.html:566-573`); the
  new markup renders it.

- **`custom_classes`** — grows from 9 entries to cover the ~25 custom classes in `styles.scss`
  (currently undocumented: `.linked-danger`, `.link-sm`, `.dropdown-menu-mw`, `.fighter-switcher-btn`,
  `.fighter-switcher-menu`, `.stat-input-cell`, `.user-badge`, `.badge-icon`, `.badge-preview`,
  `.text-clamp-2`, `.auto-flow-dense`, `.break-inside-avoid`, `.home-row-meta`,
  `.img-link-transform`, `.errorlist`, `.nav-link-danger`, `.color-radio-*`, `.list-card-collapse`,
  `.dice-tray`, `.table-group-divider`, `.hero`). Each tuple gains a fourth element: a
  `mark_safe` preview snippet. **This deletes the `{% if cls == ".x" %}` ladder at
  `design_system.html:1632-1650`**, which silently renders an empty Preview cell whenever a row is
  added without a matching branch.

### 5.3 New — page shell and index

```python
ds_groups        # list[SimpleNamespace] with .slug .title .url .blurb .section_count
ds_all_url       # str — reverse("debug_design_system_all")
ds_index         # list[SimpleNamespace] with .name .url .section_title .kind .source .uses
ds_aliases       # list[SimpleNamespace] with .term .url .target_title .reason
```

All four are **derived from `DESIGN_SYSTEM`, not hand-written**. URLs must be built with
`reverse()`, never hardcoded; `section_count` must be `len(group.sections)`, never a literal.

`ds_groups` (group order, blurbs as shipped):

| slug | title | blurb | section_count |
|---|---|---|---|
| `""` | A. Start here | What this page is, the rules everything obeys, and the one rule people get wrong. | 3 |
| `foundations` | B. Foundations | Colour, layout and spacing, typography, icons, light and dark. | 5 |
| `components` | C. Components | The parts you compose pages from: buttons, badges, callouts, boxes, fields, tables, dropdowns, pagination. | 15 |
| `patterns` | D. Patterns | Composed blocks: page shells and headers, filter bars, tabs, confirm pages, stat rows, collections. | 11 |
| `reference` | E. Reference | Custom CSS, deprecated recipes, and what we deliberately do not build. | 5 |

`ds_index` — sorted case-insensitively by `.name`. `.url` is the owning group page path plus
`#<section-id>`. `.kind` is exactly `"cotton"`, `"include"` or `"markup"`. `.source` is a
repo-relative path or `None` (renders the italic "None"). `.uses` is an `int` or `None` (renders an
em dash). Representative rows:

```python
("Back link",      ".../components/#links",          "Links, back and cancel",          "cotton",  "gyrinx/templates/cotton/back.html",                     119)
("Badge",          ".../components/#badges",         "Badge and state",                 "cotton",  "gyrinx/templates/cotton/badge.html",                    124)
("Box",            ".../components/#boxes",          "Box, card and container",         "cotton",  "gyrinx/templates/cotton/box.html",                       46)
("Breadcrumb",     ".../patterns/#page-headers",     "Head a page or a section",        "include", "gyrinx/core/templates/core/includes/breadcrumb.html",     6)
("Button",         ".../components/#buttons",        "Button",                          "cotton",  "gyrinx/templates/cotton/btn.html",                     None)
("Callout",        ".../components/#callouts",       "Callout and messages",            "cotton",  "gyrinx/templates/cotton/callout.html",                 None)
("Card",           ".../components/#boxes",          "Box, card and container",         "markup",  None,                                                    142)
("Checkbox",       ".../components/#choices",        "Checkbox, radio and switch",      "markup",  None,                                                    174)
("Disclosure",     ".../components/#disclosure",     "Disclosure",                      "markup",  None,                                                   None)
("Dropdown",       ".../components/#dropdowns",      "Dropdown and button group",       "markup",  None,                                                     44)
("Empty state",    ".../components/#empty-states",   "Empty states",                    "markup",  None,                                                      9)
("Form field",     ".../components/#form-field",     "Form field",                      "cotton",  "gyrinx/templates/cotton/form/field.html",                36)
("Icon",           ".../foundations/#icons",         "Icons",                           "cotton",  "gyrinx/templates/cotton/icon.html",                    None)
("Number stepper", ".../components/#form-controls",  "Inputs, selects and steppers",    "include", "gyrinx/core/templates/core/includes/number_stepper.html", 4)
("Pagination",     ".../components/#pagination",     "Pagination",                      "include", "gyrinx/core/templates/core/includes/pagination.html",    11)
("Progress",       ".../patterns/#progress",         "Show progress through a flow",    "include", "gyrinx/core/templates/core/includes/step_progress.html",  6)
("Table",          ".../components/#tables",         "Table",                           "markup",  None,                                                   None)
("Tabs",           ".../patterns/#segmented-tabs",   "Let someone switch between views","markup",  None,                                                     13)
("Tooltip",        ".../components/#tooltips",       "Tooltip",                         "markup",  None,                                                     71)
```

`ds_aliases` — the fragment in parentheses is the section id the view resolves `.url` from:

```python
("modal",         → #confirm-pages, "Confirm a destructive action",   "The app has zero Bootstrap modals. A confirmation is a linkable, refreshable page.")
("accordion",     → #disclosure,    "Disclosure",                     "We use <details>. One-open-at-a-time is a section switch, and that belongs in the URL.")
("toast",         → #callouts,      "Callout and messages",           "Transient messages are server-rendered banners at the top of the page.")
("combobox",      → #pickers,       "Let someone pick from many things", "Searching a large set is a server-filtered picker page, not a client-side widget.")
("avatar",        → #collections,   "Show a list of things",          "There is no avatar data. Identity is username plus supporter badge plus house icon.")
("slider",        → #form-controls, "Inputs, selects and steppers",   "Quantities are small integers; a stepper beats a drag target on mobile.")
("datepicker",    → #form-controls, "Inputs, selects and steppers",   'Battle and campaign dates use the native <input type="date">.')
("theme builder", → #theme,         "Light, dark and auto",           "Tokens are documented, not editable. There is one brand.")
```

### 5.4 New — Foundations data

```python
ds_colour_rules = [
    ("primary",   "Navigation and the app's own accent. Not a state.",
                  "btn-primary, the wealth badge on a gang row, the XP chip, a section count badge",
                  "A fighter or campaign state"),
    ("secondary", "Neutral — no state, or a state that is deliberately unremarkable",
                  "text-secondary metadata, btn-secondary cancel, the Sold to Guilders badge",
                  "A default for chips that just hold a number"),
    ("success",   "Active, in progress, confirmed",
                  "Campaign In Progress, a locked crew, btn-success save and create",
                  "A generic 'good' accent, or a toolbar's default button"),
    ("warning",   "Needs attention but not lost — injured, convalescing, in repair, captured",
                  "Fighter state badge, the modified-stat cell in a statline, bg-warning-subtle card header, overridden-cost badge",
                  "Emphasis. A warning colour on something that is fine reads as a bug"),
    ("danger",    "Dead, destructive, or an error",
                  "Dead fighter badge and card tint, btn-danger, form errors, delete items",
                  "Anything reversible — archive is a link-danger link, not a red button"),
    ("info",      "Explanatory, not a state",
                  'c-callout variant="info", the .tooltipped underline, a pending-invitation count',
                  "Fighter or campaign status, or an action button"),
    ("light",     "A surface, never a signal",
                  "The attribute tag chip (badge fw-normal text-bg-light border)",
                  "State"),
    ("dark",      "A surface, never a signal",
                  'The navbar (bg-dark plus data-bs-theme="dark")',
                  "State — see the divergence note in this section"),
]

ds_type_scale = [
    ("Top-level index", "2.19rem",  "base * 2.5",      "h1",         "Index pages (Lists & Gangs, Campaigns, Customisation)", "8"),
    ("Entity detail",   "1.75rem",  "base * 2",        "h1.h2",      "Campaign, Pack, Battle, List detail",                   "8"),
    ("Sub-page",        "1.53rem",  "base * 1.75",     "h1.h3",      "Edit forms, settings, campaign sub-pages",              "164"),
    ("Section",         "1.09rem",  "base * 1.25",     "h2.h5",      "Section headings; card headers as h3.h5",               "92"),
    ("Body",            "0.875rem", "$font-size-base", "",           "Everything",                                            "—"),
    ("Compact",         "0.79rem",  "base * 0.9",      "fs-7",       "Stats, weapons, tabs, metadata",                        "750"),
    ("Label",           "0.77rem",  "0.875em of parent", "caps-label", "Section sub-headers, metadata labels",                "144"),
]

w_em_scale    = [("3","3em"),("4","4em"),("5","5em"),("6","6em"),("8","8em"),("10","10em"),("12","12em")]
size_em_scale = [("1","1em"),("2","2em"),("3","4em"),("4","8em"),("5","16em")]   # DOUBLES from n=2
sq_scale      = [("1","1em"),("2","2em"),("3","3em"),("4","4em"),("5","5em"),("6","6em")]

icon_semantic_map = [
    ("add",      "bi-plus-lg",              "Create or attach a new thing"),
    ("edit",     "bi-pencil",               "Edit an existing thing"),
    ("delete",   "bi-trash",                "Destroy irreversibly"),
    ("archive",  "bi-archive",              "Hide reversibly"),
    ("clone",    "bi-copy",                 "Duplicate"),
    ("save",     "bi-check-lg",             "Commit a form"),
    ("confirm",  "bi-check-lg",             "Agree to a destructive action"),
    ("back",     "bi-chevron-left",         "Return to the parent page"),
    ("search",   "bi-search",               "Search or filter input"),
    ("more",     "bi-three-dots-vertical",  "Open an action menu"),
    ("warning",  "bi-exclamation-triangle", "Warning and error callouts"),
    ("info",     "bi-info-circle",          "Neutral explanatory callouts"),
    ("pack",     "bi-box-seam",             "Content pack"),
    ("person",   "bi-person",               "A user, or attribution"),
    ("eye",      "bi-eye",                  "Visibility and public listing"),
    ("gear",     "bi-gear",                 "Settings"),
    ("dice",     "bi-dice-6",               "A roll, or a randomised outcome"),
]
```

`icon_semantic_map`'s names and glyphs are verified against the `<c-vars :icons>` dict in
`gyrinx/templates/cotton/icon.html`. **The dict values omit the `bi-` prefix** (`'add': 'plus-lg'`),
so the Class column is the *emitted* class, not a copy of the dict value — do not diff them
directly and conclude they have drifted.

### 5.5 New — live URL-state demo

```python
DS_VARIANT_ITEMS = {
    "melee":   [("Fighting knife", 10), ("Chainsword", 25), ("Power hammer", 45)],
    "ranged":  [("Autopistol", 10), ("Lasgun", 15), ("Boltgun", 55)],
    "wargear": [],   # deliberately empty — renders the {% empty %} branch live
}

ds_variant_options = [("melee", "Melee"), ("ranged", "Ranged"), ("wargear", "Wargear")]

ds_variant = request.GET.get("ds_variant", "melee")
if ds_variant not in dict(ds_variant_options):
    ds_variant = "melee"                    # normalising in the VIEW is part of what it teaches
ds_variant_items = DS_VARIANT_ITEMS[ds_variant]
ds_compact = request.GET.get("ds_compact") == "1"
```

### 5.6 New — sample data for the Patterns group

```python
ds_page_obj      # SimpleNamespace with .number, .has_previous, .has_next,
                 # .previous_page_number, .next_page_number,
                 # .paginator = SimpleNamespace(page_range=range(1, 6))
                 # Must satisfy core/includes/pagination.html so the include renders for real.
ds_fighters      # list[SimpleNamespace] for #collections and #boxes: .name .type .cost .state
                 # covering active / injured / captured / dead / sold_to_guilders
ds_actions       # list[SimpleNamespace] for #activity: .user .description .outcome .created
                 # (.created a naive datetime so |timesince works), plus .battle = None
ds_notifications # list[SimpleNamespace] for #callouts and #inline-actions: .level_tag .message .read
ds_task_rows     # list[tuple] for #task-status: (gang, state, retryable) over
                 # queued / running / complete / failed
```

### 5.7 New — component props registry

```python
COMPONENT_PROPS: dict[str, dict[str, str]]
# {"btn": {"variant": "Semantic role — see the variant table", "size": "…", …}, …}
```

Keyed by component path relative to `gyrinx/templates/cotton/` without the extension. `{% ds_props %}`
reads names and defaults from the component's `<c-vars>`; this dict supplies descriptions only. A
pytest asserts bijection in both directions.

### 5.8 Load line and template tags

The shell needs `{% load badge_tags custom_tags ds_tags %}` — the current page loads only
`badge_tags`, which is why `{% dot %}`, `{% qt %}`, `{% credits %}` and `{% house_icon %}` are
shown as literals or hand-rolled `mark_safe` today. `{% qt %}` and `{% credits %}` are required by
`#url-state`; `{% dot %}` by `#buttons` and `#inline-actions`.

---

## 6. Relationship to the component migration

### 6.1 Which sections become the live gallery

| Component | Gallery section | Also demonstrated in |
|---|---|---|
| `c-btn` (+ `c-cancel`) | **`#buttons`** — variants, sizes, element choice, icon slot, disabled, loading composition, generated props table | `#page-headers`, `#confirm-pages`, `#filter-bars`, `#segmented-tabs`, `#inline-actions` |
| `c-badge` (+ `badge/chip`, `badge/fighter_state`) | **`#badges`** — the four shapes, the state table, link-vs-span, count badge, tag chip, uncoloured variant | `#colour` (documents the raw class, deliberately), `#collections`, `#stat-rows`, `#tables`, `#page-headers` |
| `c-callout` (+ `c-messages`, `c-errors`) | **`#callouts`** — six variants, the fixed icon/body anatomy, dismissible vs not, the shared messages implementation | `#confirm-pages`, `#form-field` (the `non_field_errors` block) |
| `c-field` (+ `c-form`) | **`#form-field`** — anatomy, the three branches, the always-rendered errors, the `:field=` colon rule | `#choices`, `#form-controls`, `#filter-bars` |
| `c-icon` | `#icons` | everywhere |
| `c-box` | `#boxes` | every framed demo on every page |
| `c-back` | `#links` | `#page-shells`, `#confirm-pages` |

### 6.2 Conversion order once the components land

The order is chosen so that each step de-risks the next, and so that the first thing converted is
the thing most likely to expose a bad API.

1. **`c-icon` → `#icons`.** Smallest surface, highest fan-out, zero visual risk (every preview
   already emits its exact output). Converting it first proves `{% ds_demo %}` handles `<c-*>`
   source capture correctly before anything harder depends on that. It also settles the
   semantic-name map as the single source of truth.
2. **`c-box` → `#boxes`, then page-wide.** The `border rounded p-3` demo frame appears in every
   section; if `{% ds_demo %}` ends up owning the frame, `c-box` is *not* needed there and this
   step shrinks to just `#boxes`. Decide that first — it is the one ordering dependency in the
   list.
3. **`c-badge` → `#badges`.** The state table is the payload. Note the deliberate design decision:
   `c-badge` has **no** state prop, so the state-to-colour mapping has exactly one home
   (`badge/fighter_state`). `#colour` remains the one legitimate site that writes raw `text-bg-*`,
   and that exception should be written into `badge.html`'s docstring rather than silently
   violated.
4. **`c-btn` → `#buttons`.** Larger surface, and it needs the props table working, which is why it
   follows `c-badge` rather than leading. Its three icon-only naming shapes must all be
   expressible or 22 call sites become non-conformant.
5. **`c-callout` / `c-messages` → `#callouts`.** This one closes a live bug: the two hand-rolled
   message blocks in `core/layouts/base.html` and `allauth/layouts/base.html` had drifted, and the
   allauth copy keyed on `message.tags` rather than `level_tag`, so a message with `extra_tags`
   rendered blue regardless of level — including errors (#2001).
6. **`c-field` / `c-form` → `#form-field`, `#choices`, `#form-controls`.** Last, because it is the
   largest behaviour change and the one with the most divergence to absorb: **four competing error
   renderings in the wild** — `{{ f.errors }}` (118 sites), `{{ f.errors.0 }}` (24), a `{% for %}`
   loop, and `|first` (1) — plus ~26 hand-rolled `invalid-feedback d-block` sites and ~8
   near-verbatim `non_field_errors` blocks.
7. **`c-back` / `c-cancel` → `#links`.** Mechanical, 119 + 23 sites, no design questions left open.

### 6.3 What the gallery buys the migration

Each section's `kind` badge flips from `markup` to `cotton` as its component lands, and the A–Z
index's `Uses` column shows how far the design system is ahead of the codebase. That makes the
remaining backlog visible on the page itself rather than in a tracking issue — which is the
cheapest available mechanism for keeping the gallery and the library from drifting apart.

---

## 7. Open questions and decisions for the maintainer

**1. Which cotton namespace survives?** `gyrinx/templates/cotton/` currently contains the canonical
set *plus* `c3/` and `zb/` directories that look like competing parallel drafts, and `act/`,
`btn/`, `menu/` are empty directories. Nothing can render a live `<c-*>` tag until this is settled.
**Recommendation:** the parallel-components workflow declares one surviving namespace and deletes
the others before this page is built; the props-registry bijection test then enforces it. Until
then every section stays `markup`/plain Bootstrap, exactly as authored.

**2. `<c-icon>` will raise `TemplateSyntaxError` on first render.** `gyrinx/templates/cotton/icon.html`
uses the `|get_item` filter (`custom_tags.py:86`) with no `{% load custom_tags %}`, and
`settings.py`'s `TEMPLATES["OPTIONS"]` has no `builtins` key. **Recommendation:** add
`custom_tags` to template `builtins` — it is used by nearly every component and the alternative is
a `{% load %}` line in each. Must be fixed before step 1 of §6.2.

**3. Does `h2.h4` join the type scale, or does the page move to `h2.h5`?** 26 sites, 21 of them on
this page. **Recommendation:** move the page to `h2.h5`. Twenty-one of the twenty-six disappear the
moment sections are wrapped, so the scale does not need a new row for five stragglers.

**4. Should `?theme=` become real URL state?** Today it is JS-only, and it writes the
`theme_active` cookie for a year, so previewing dark once causes a flash on every later page.
Documented honestly, the mechanism is unflattering on the very page that teaches the URL rule.
**Recommendation:** make `index.js` treat a query-param theme as transient (apply it without
calling `setStoredActiveTheme`) — a three-line change that lets `#overview` and `#theme` drop two
caveats. Making it server-read is the purist answer but is out of scope here.

**5. Are the `Uses` counts computed or hand-maintained?** A literal will rot exactly as the stale
section-number banner comments did. **Recommendation:** compute at render time (glob + grep across
app templates, ~50ms, fine in a `DEBUG`-only view), **excluding the design-system pages
themselves** — raw repo-wide greps are inflated by the page's own demos, which is how the current
`text-body-tertiary` claim became self-falsifying. Render `—` for a missing count so a gap is
visible rather than wrong.

**6. Adopt or delete the three dead includes?** `core/includes/empty_state.html`,
`core/includes/alert.html` and `core/includes/_alert_inner.html` have **zero references
repo-wide**, while the markup they encapsulate is hand-rolled in 9 files (empty states) and 3
banner variants (alerts). **Recommendation:** delete all three. `c-callout` supersedes the alert
pair outright, and `empty_state.html` implements only the two basic forms of the five that
`#empty-states` documents. Do not leave them.

**7. Do the `{% verbatim %}`-style code samples all move to `{% ds_demo %}` at once?** Sections
whose demos are `{% for %}` loops over context data (Colour, Icons, Layout's sizing scales) would
print the loop rather than the markup. **Recommendation:** `ds_demo` grows a
`{% ds_demo rendered %}` mode that emits the *rendered* HTML rather than the captured source, and
those three sections use it. Otherwise they opt out and hand-write, which reintroduces exactly the
drift `ds_demo` exists to prevent.

**8. Should `sq-*` and the unused half of `w-em-*` be deleted?** `sq-*` has one use in the whole
app (the share QR code) and overlaps `size-em-*` at n=1 and 2; only 4 of `w-em-*`'s 7 steps are
used. **Recommendation:** document both now (they ship), and file the adopt-or-delete decision
alongside #6 rather than blocking this work on it.

**9. Fix the two live switch bugs in the same PR?** `core/campaign/campaign_packs.html:38-52` is a
POST-form switch with `data-gy-toggle-submit`, no visible submit and no `<noscript>` — unusable
with JS off. `core/list/list_skill_trees_edit.html:29` uses inline `onchange="this.form.submit()"`.
**Recommendation:** yes. `#url-state` and `#choices` both state the rule these break, and a
design-system page that documents a rule its own app violates in two named files is weaker for it.
Same argument applies to the two nameless icon-only controls on the page itself
(`design_system.html:1174`, `:1257`).

**10. Do we fix `docs/DESIGN-SYSTEM.md` in this PR?** It is four months stale and contradicts the
page in five places, and the no-modals and URL-state rules are not in it at all.
**Recommendation:** yes, in the same PR, per the precedence rule `#overview` states. Otherwise
`#principles` has to keep its awkward "rules 2 and 7 come from somewhere else" paragraph, and the
page ships a documented contradiction on day one.

**11. Is `#principles`' density demo worth keeping?** It is cleanly severable. **Recommendation:**
keep it. "Dense over spacious" is asserted in `CLAUDE.md`, in the spec and on this page, and
demonstrated in none of them.

**12. Anchors and section ids must land page-wide or not at all.** No `<section>` on the page has
an `id` today. Half-applying them gives the sidebar dead entries. **Recommendation:** the routed
shell lands with all 39 ids in one pass; the CI test in §3.13 that resolves every cross-reference
fragment is what keeps it that way.
