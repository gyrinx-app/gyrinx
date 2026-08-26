# How to build an n26 screen with cotton, Alpine, and htmx

n26 — the app for the game's 2026 edition, under `n26/` — is built from
server-rendered Django templates. Three libraries sit on top, and each one
has a fixed job:

| Layer | Job | Never its job |
|-------|-----|---------------|
| **django-cotton** | Components. Every reusable piece of UI is a `<c-n26.*>` tag under `n26/core/templates/cotton/n26/`. | Behaviour. A component renders markup; it does not fetch or decide. |
| **Alpine.js** | Narrowing and reordering content that is already on the page — a search box filtering a table, a tab strip hiding sections. | Anything the server would render differently. Alpine never swaps form variants, computes prices, or invents content. |
| **htmx** | Submitting a form or link the page already has, and applying the partial response the server sends back. | Being the only way anything works. Every htmx control is a plain link or form underneath. |

Two rules bind all three, and they are the ones reviewers hold the line on:

1. **UI state lives in the URL.** Which list, which section, which row is
   open, which dialog is showing — all of it is in the path or query string,
   so every state is linkable and a reload renders it. Alpine may hold
   transient presentation state (a filter's current text); the moment state
   changes what the server would render, it goes in the URL.
2. **Everything works without JavaScript.** Turn scripting off and every
   control still functions as a full-page link or form post. JavaScript makes
   the same controls cheaper, never possible.

The equip screens — where a player buys and sells a fighter's gear
(`n26/core/views/equip.py`, `n26/core/templates/n26/equip.html`) — use all
three layers together and are the reference implementation for this guide.
If you are here to add partial updates to a screen, the recipe is the
numbered list in "htmx: partial updates" below.

## Cotton: writing and calling components

A tag name maps to a file path: dashes in the tag become underscores in the
filename, and dots are directories. `<c-n26.filter-menu>` is
`cotton/n26/filter_menu.html`; a directory resolves to its `index.html`, so
`<c-n26.collection-picker>` is `cotton/n26/collection_picker/index.html` and
`<c-n26.collection-picker.item>` is `item.html` beside it.

A component declares its inputs in a `<c-vars>` block at the top of the file
(each attribute there is a prop with its default), and opens with a
`{% comment %}` block documenting the tag, a usage example, and the props.
The full authoring rules are in `n26/core/CLAUDE.md`, including registering
new components in the component gallery — the living design-system
reference at `/n26/design/`, which renders each component on its own page.

What follows is the list of ways cotton silently breaks. None of these
raises an error.

**A template tag inside a component's attribute list renders as text.**
This is the one that costs the most time. You cannot write:

```html
<c-ui.button {% if urgent %}variant="danger"{% endif %}>…</c-ui.button>
```

The `{% if %}` lands in the page as literal characters. To vary a
component's attributes, draw the whole element once per case:

```html
{% if urgent %}
    <c-ui.button variant="danger">…</c-ui.button>
{% else %}
    <c-ui.button>…</c-ui.button>
{% endif %}
```

If the duplication is painful, that is a sign the condition belongs *inside*
the component as a declared prop, where `{% if %}` parses normally.

**A `:`-prefixed attribute passes a variable, and only a variable.**
`:count="items"` hands the component the template variable `items` rather
than the string "items". But it takes a plain variable or a literal only:
filters, comparisons and negations (`:count="items|length"`,
`:selected="a == b"`, `:disabled="not next"`) evaluate to nothing. The prop
arrives empty, so a `:disabled` control stays enabled and a `:selected`
option never selects — with no error. Compute the flag in the view.

**Undeclared context leaks into components.** A variable in the surrounding
template context is visible inside a component even if it is not a declared
prop. Code that works this way is a trap: any page with a same-named context
variable changes the component's behaviour. Declare every input in
`<c-vars>` and pass it at the call site.

**`{% comment %}` inside `<c-vars>` must contain no quotes or apostrophes.**
One apostrophe swallows every prop declared after it.

**`class=""` must be declared to be merged.** Cotton collects attributes
that are not declared props into `{{ attrs }}`, which most components spray
onto their root element. Pass `class=` to a component that does not declare
it and the root element gets a second `class` attribute; the browser keeps
the first and drops the component's entire styling.

## Alpine: what it may hold, and what dies with the DOM

The reference pattern is the collection picker
(`n26/core/templates/cotton/n26/collection_picker/index.html`): the server
renders every row, and Alpine filters, counts and hides them client-side.
The filter text and the slider positions are transient, presentational, and
lost on reload by design. The chosen section *tab* changes what a reload
should show, so the picker writes it into the URL with
`history.replaceState`.

Three facts about Alpine matter when the other layers are involved:

**Content inside `<template x-if>` does not exist until Alpine builds it.**
Anything that wires the DOM once at page load — htmx included — never sees
it. If such content holds htmx controls, their clicks need a delegated
listener at the document level (see `n26/core/static/n26/htmx_support.js`).

**Alpine state dies with its element.** When htmx replaces an element,
Alpine initialises the replacement from scratch. That is fine for state the
server just re-derived — a row's open or closed state, carried in the URL —
and fatal for state it did not. Replacing a region that contains a live
widget, such as a tab set or an open popover, throws `Expression Error`s in
the console and loses the user's place. The rule: **a partial update only
replaces elements whose entire state the server can re-derive.** The equip
screens update the gang's wealth readout but not the model tally beside it,
for exactly this reason.

**Registration must be keyed if the element can be replaced.** The picker's
rows report themselves into a shared dictionary on init, which is how the
picker counts and filters them. That dictionary is keyed by what each row is
for, so a replaced row overwrites its own registration instead of being
counted twice. A plain list would drift upwards with every update.

## htmx: partial updates

The full protocol is documented in `n26/core/views/htmx.py` — read that
docstring first; it is the canonical statement. The short version:

- A form or link carries `hx-post`/`hx-get` with `hx-swap="none"`. The
  control targets nothing.
- The server detects htmx (`is_htmx(request)`) and responds with a fragment
  in which each element carries `hx-swap-oob` — htmx's out-of-band swap,
  where the response element itself names, by id, the page element it
  replaces. Which parts of the page an action updates is therefore decided
  in one server template (`n26/core/templates/n26/includes/equip_update.html`
  is the example), not spread across call sites.
- Queued Django messages ride the `HX-Trigger` response header as one
  `n26-toasts` event and appear as toasts (`with_toasts`, `no_update` in
  `n26/core/views/htmx.py`). Without htmx, the same messages render in the
  normal alert block.
- URL parameters that hold live UI state (`section` and `owned` on the
  equip screens) are declared per page in a `<meta name="n26-carry">` tag.
  The URLs baked into the page's controls were rendered before the user
  last changed tab or opened a row, so the client glue re-adds the current
  values to every htmx request.

**Opting a screen in is all-or-nothing.** htmx drops an out-of-band element
whose id is missing from the page, silently: on a screen missing the
targets, an action would run server-side and nothing on screen would
change. So a screen opts in by rendering the host elements — fixed-id
containers the update responses fill, shared in
`n26/core/templates/n26/includes/equip_hosts.html` — *and* passing
`htmx=True` in its render context, which is what makes the screen's
controls emit `hx-get` and forms carry `hx-post` at all. A screen that does
neither — the gang sheet, the component gallery — gets plain links and full
pages, automatically.

To add partial updates to a new screen:

1. Render the host elements the update template names, or write a new
   update template naming your own. Fixed ids, one per replaceable region.
2. Pass `htmx=True` in the view's render context, and add the `n26-carry`
   meta tag for whatever URL parameters your screen keeps live.
3. In the view, branch on `is_htmx(request)`: plain requests redirect as
   ever; htmx requests get the update fragment (wrapped in `with_toasts`)
   or `no_update(request)` when the action changed nothing.
4. Test both paths. The house pattern is in
   `n26/core/test_views_equip.py`: post once plainly and assert the
   redirect, post once with `headers={"HX-Request": "true"}` and assert the
   fragment names every element it replaces — plus one test that the page
   itself contains every id the update uses.

## Cross-layer pitfalls

Each of these produced a real bug during the first build. They are cheap to
avoid and expensive to rediscover.

- **htmx never wires Alpine-built DOM.** Controls inside `<template x-if>`
  fall back to full-page navigation unless the delegated click handler in
  `htmx_support.js` catches them. If you add a new kind of late-built
  control, check it against that handler's selector.
- **Only replace what changed, and only what the server owns.** Replacing a
  live Alpine widget breaks it (see above). The update template should name
  the smallest set of elements the action genuinely changed.
- **htmx wraps trigger payloads.** A non-object `HX-Trigger` payload
  reaches listeners as `{value: …}` — read `event.detail` as the list
  itself and it is silently empty. The toast listener in
  `htmx_support.js` documents this; do not simplify it away.
- **htmx's history cache is off** (`historyCacheSize: 0` in the base
  layout). Every URL we write is one the server renders in full, so the
  back button can simply re-request it — and snapshotting large pages into
  localStorage overruns the quota.
- **The two id derivations must not drift.** A row's DOM id comes from the
  `row_dom_id` template filter (`n26/core/templatetags/listing.py`), used
  both where the row is drawn and where an update replaces it. Reuse it;
  do not spell the id out.

## Checking your work

- `./scripts/dev.sh` starts the server (with the per-worktree database and
  CSS watch); the startup banner prints the port.
- `pytest n26` — the suite covers both request paths and the no-JavaScript
  behaviour.
- Load the screen in a browser **with the console open**. Alpine and htmx
  both fail silently or near-silently; several of the bugs above were
  invisible except as console errors.
- Check the component gallery page for any component you touched
  (`/n26/design/c/<slug>/`) — gallery pages fail silently too.
- Turn JavaScript off and walk the screen once. Every control must still
  work as a link or form.
