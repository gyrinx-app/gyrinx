# Interstitials attached to Slots — implementation plan

Status: plan only, no code written. Written against the tree at
`/home/user/gyrinx` (n26 as of this session).

## 1. What is being asked for

An **Interstitial** is an authored object — title, description, and whether it
may be skipped — attached to one or more `Slot`s. When anything that carries a
slot arrives (a gang founded, a model hired, a pick that brings slots, a
purchase that brings slots), the app collects every interstitial on the slots
that just arrived and shows them on one screen, immediately after the act and
before the reader lands where they were going.

The motivating case: an Outcast gang's Archetype is a decision almost as large
as the gang type, and today it is one question among many in the gang's choice
list.

### Assumptions made (flagged, not decided)

- **A1.** The screen is read-only about the gang: it never writes. Choosing
  still happens on the existing pick screen (`n26-choose`).
- **A2.** Nothing about "shown" or "skipped" is stored. The screen is derived
  from the address, every time. This follows the edition's "recompute, never
  nudge" and "URL state" stances, and it is why nothing needs a `core`
  migration.
- **A3.** Non-skippable means "this screen will not offer Continue while the
  slot is unresolved" — it is not a lock on the rest of the app. The reader can
  always leave by the nav; nothing is policed. ("Inform, never police.")
- **A4.** The word *interstitial* is an author's and a developer's word. No
  player-facing string uses it.

## 2. What the code actually does today

### Slots are computed, never stored

`n26/library/models/slots.py` — `SlotType` → `Pickable` → `Picklist` →
`PicklistMember` → `Slot`. A `Slot` is an `Assignable`. Only the **pick** is
stored (`Assignment.chosen_for` / `chosen_for_slot` / `chosen_for_offer`).

A slot reaches a card two ways, both folded at read time in
`n26/core/effects.py`:

- as an assignment whose `assignable` is a `Slot` — built into a thing, or an
  entry bought from a collection (`_fill_slot_choices`, the `all_nodes()` walk);
- **given** by a modifier: `AddsAssignable` with `slot_id` set
  (`n26/library/models/modifier.py:1112`), collected into `given_slots` around
  `effects.py:944` and folded by `_fill_slot_choices(computed, given, …)`.

Both end up as `ChoiceSlot` (`effects.py:209`) on `computed.choices`, carrying:

- `anchor` — the card node asking. `anchor.assignment` is the **stored
  assignment** behind it.
- `identity` — the `Slot` row (or an `OffersChoice` for the older offer shape).
- `picks`, `min_picks`, `max_picks`, `is_resolved`, `is_full`, `kind_label`.

### The pick screen and its address

`n26/core/views/choose.py`. The address is
`/n26/gangs/<gang>/choose/<card>:<carrier>:<offer>/` where `card` is a model pk
or the literal gang host key (`n26.core.render.GANG_SLOT_HOST`), `carrier` is
`anchor.assignment.pk`, `offer` is `identity.pk`.

- `link_slots(gang, *holders, back=…)` writes `line.href` onto every question on
  a card, optionally with `?return=<back>`.
- `_find_slot(gang, key)` rebuilds the card and locates the slot, 404ing when
  the carrier has gone. **This is the function the new screen reuses.**
- `_own_address(request, url)` is the local return-URL check. There is **no
  `safe_redirect` in n26** — `gyrinx.safe_redirect` must not be imported
  (n26 boundary rule). `n26/core/views/permissions.py:24` has `_safe_redirect`,
  which is the one to promote and share.

### The single choke point for writes

`n26/core/operations.py`. **Every** state change in the edition goes through
`operation(gang, actor=…)` (38 call sites across `n26/core/views/*.py`), and
every assignment is written by exactly one method: `Operation.assign()`
(`operations.py:348`) — 14 internal call sites, nothing outside may create an
`Assignment`. `op.settle()` runs at the end of the context manager.

`Operation.found()` (`:1591`), `Operation.hire()` (`:1547`),
`Operation.choose()` (`:2078`), `Operation.buy()` (`:2331`),
`Operation.rechoose()` (`:1666`) all bottom out in `assign()`.

**So there is a single choke point, and it is `Operation.assign()`.**

### The redirect points that need to change

| act | file | today |
|---|---|---|
| found a gang | `n26/core/views/gangs.py` `create_gang` (~:983–1030) | `redirect("n26-gang", pk=gang.pk)` |
| hire | `n26/core/views/hire.py` `hire_fighter` (~:497) | `redirect(back)` |
| choose a pick | `n26/core/views/choose.py` `choose` | `redirect(landing)` |
| buy | `n26/core/views/equip.py` | `redirect(...)` |
| re-option | `n26/core/views/options.py` | `redirect(...)` |

## 3. Model design

New rows in **`n26/library/models/slots.py`**, filed with the rest of the
choice machinery (an author looks for them there). Both are `Content`, not
`Assignable` — an interstitial is never assigned to anything, so it gets no
`family`, no `modifiers`, no `built_ins`, and no `qualifier`. This mirrors
`SlotType` and `Picklist`, which are also `Content`-only.

```python
class Interstitial(Content):
    """A screen shown when a slot arrives: what the choice is, and why it matters."""

    name = models.CharField(max_length=200,
        help_text='What an author calls this, e.g. "Outcast archetype".')
    title = models.CharField(max_length=200, blank=True, default="",
        help_text="The heading the screen shows. Blank uses the name.")
    description = models.TextField(blank=True, default="",
        help_text="What the screen says under the heading.")
    skippable = models.BooleanField(default=False,
        help_text=("Whether the reader may carry on without answering. "
                   "Unticked, the screen offers no way on until the choice is made."))
    position = models.PositiveIntegerField(default=0,
        help_text="Order among the interstitials on one screen. Ties fall back to name.")

    class Meta:
        verbose_name = "interstitial"
        ordering = ["position", "name"]
        constraints = [
            models.UniqueConstraint("pack", Lower("name"),
                                    name="interstitial_unique_per_pack"),
        ]

    @property
    def heading(self):
        """What the screen calls it."""   # mirrors Slot.choice_label
        return self.title or self.name


class InterstitialSlot(Content):
    """One interstitial attached to one slot."""

    interstitial = models.ForeignKey(Interstitial, on_delete=models.CASCADE,
                                     related_name="attachments")
    slot = models.ForeignKey(Slot, on_delete=models.PROTECT,
                             related_name="interstitial_attachments")
    position = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = "interstitial attachment"
        ordering = ["position", "interstitial__name"]
        constraints = [
            models.UniqueConstraint("interstitial", "slot",
                                    name="interstitial_attached_once"),
        ]
```

**Why a through model rather than a bare `ManyToManyField`.** `PicklistMember`
is the precedent. A through row has a pk, so the authoring page can list each
attachment as a part with its own Remove address, and can carry `position`. A
bare M2M gives neither.

Add a convenience on `Slot` (a property, not a column):

```python
    @property
    def interstitials(self):
        """The interstitials this slot carries, in their own order."""
        return Interstitial.objects.filter(
            attachments__slot=self, archived=False
        ).order_by("attachments__position", "position", "name")
```

Export both from `n26/library/models/__init__.py`.

**Migration.** One library migration, no core migration.

```
manage makemigrations library -n "a_slot_can_carry_an_interstitial"
```

Never hand-write `dependencies` (repo rule). Latest leaf today is
`0106_a_weapon_profile_says_who_may_use_it`. Data-free, additive, reversible;
no backfill and nothing to smoke-test on production volume beyond `migrate`
timing (two `CREATE TABLE`s).

**Vocabulary check.** No "cost" anywhere (an interstitial has no price). Never
call an attachment a "row". British spelling in prose.

## 4. Collection mechanism — how "just arrived" is known

### The chosen mechanism: anchor written by this operation

A `ChoiceSlot` is addressable only when `anchor.assignment` exists (that is
already `choose.py`'s own rule). A slot **just arrived** exactly when its
anchor assignment was written by the operation that just ran.

1. `Operation.__init__` gains `self._written = set()`.
2. `Operation.assign()` adds `assignment.pk` to it after create (one line,
   inside the single choke point — every arrival route is covered: built-in,
   grant, purchase, hire, founding, pick, clone).
3. New module **`n26/core/arrivals.py`**:

```python
def arrived(gang, written, *, cards=None):
    """The choice slots these assignments just put on this gang's cards.

    Returns [(card_key, ChoiceSlot)] — card_key is the model pk, or
    GANG_SLOT_HOST for the gang's own card, so a caller can build the
    address n26-choose reads.
    """
```

It builds the gang card once (`build_gang_card` + `build_modifier_index` +
`compute_gang` / `compute`, or `render_gang` when the caller wants the sheet
anyway), walks `computed.choices` for the gang and each member, and keeps the
slots whose `anchor.assignment.pk ∈ written`.

**Cost.** One card derivation per acting request, and only when interstitials
exist at all. Short-circuit first:

```python
def any_interstitials():
    """Whether the library holds any live interstitial. One query, cached
    for the request; a library with none pays nothing for this feature."""
```

**Why not a before/after diff of the computed slot set.** It costs two full
derivations per act, has to invent a "before" for a gang that did not exist a
moment ago, and would count a slot as arriving when a *condition* turned true
rather than when anything arrived. The anchor test is exact and costs one pass.

**Known limit (accept and note).** A slot whose anchor is an older assignment
but which only became live because a condition flipped is not counted as
arriving. Nothing in the current content does that, and the gang page's
existing unresolved-slot `Note` (`effects.py:1565`, "Archetype — 0 of 1
chosen") still surfaces it.

### The view-side seam

`n26/core/arrivals.py` also holds the one function views call:

```python
def onward(request, gang, op, back):
    """Where the reader goes after an act: the interstitial screen when
    the slots that just arrived carry one, else `back`."""
```

It filters `arrived(...)` to slots carrying a live, unarchived, non-staged
interstitial (staged only for `sees_staged(request.user)`), drops slots already
resolved and slots with `max_picks == 0`, and builds

```
/n26/gangs/<gang>/introducing/?ask=<key>&ask=<key>&next=<back>
```

`ask` keys are the same `card:carrier:offer` triples `n26-choose` uses. If
nothing is left, it returns `back` unchanged — no blank screen ever renders.

Views change from `return redirect(back)` to
`return redirect(onward(request, gang, op, back))`. `op` must outlive the
`with` block; it does (the context manager yields the object).

## 5. The screen

### Address

```python
path("gangs/<str:pk>/introducing/", views.introducing, name="n26-introducing"),
```

in `n26/urls.py`, beside `n26-choose`. Whole state in the address: `ask`
(repeated) and `next`. Linkable, reloadable, works with scripting off, back and
forward behave.

### Structures before renderers

In `n26/core/render.py` (named to avoid clashing with the library model):

```python
@dataclass(frozen=True)
class IntroBlock:
    """One interstitial, as the screen draws it."""
    heading: str
    description: str      # editor HTML; sanitised at draw
    skippable: bool
    label: str            # what the slot asks — "Archetype"
    bearer: str           # whose question it is: a model's name, or the gang's
    chosen: str | None
    href: str             # the pick screen, filled in by the view

@dataclass(frozen=True)
class Introduction:
    blocks: tuple[IntroBlock, ...]
    next_url: str

    @property
    def blocking(self):
        """The blocks that must be answered before the reader may carry on."""
        return [b for b in self.blocks if not b.skippable and not b.chosen]

    @property
    def may_continue(self):
        return not self.blocking
```

Tests assert on `Introduction`, not on HTML.

### View — `n26/core/views/introducing.py`

```python
@login_required
def introducing(request, pk):
    """What just arrived, and the choices it brought.

    GET only; writes nothing. Every question named in the address is
    located again (`find_slot`), so one that has since gone stops being
    asked rather than 404ing the whole screen. A screen with nothing left
    to say sends the reader on rather than drawing an empty page.
    """
```

Steps:

1. `gang = _own_gang_or_404(request, pk)` — only the owner; a shared roster
   link never lands here.
2. `next_url = _safe_redirect`-style check of `request.GET.get("next")`,
   falling back to `reverse("n26-gang", args=[gang.pk])`.
3. For each `ask` (cap at 20, ignore the rest): `find_slot(gang, key)` inside a
   `try/except Http404` — skip what has gone.
4. Skip slots that are resolved, hidden, or `max_picks == 0`.
5. Collect interstitials: one query,
   `Interstitial.objects.filter(attachments__slot__in=slots).selectable(include_staged=shown).distinct()`
   prefetching `attachments`. De-duplicate by interstitial (see decision D3).
6. Build `IntroBlock`s; `href = reverse("n26-choose", args=[gang.pk, key])` with
   `?return=<this page's own full address>` via `with_query`, so settling one
   comes back here and the answered one drops off.
7. If `blocks` is empty → `redirect(next_url)`.
8. Render.

**Refactors this needs:** promote `choose._find_slot` → `find_slot` and
`permissions._safe_redirect` → `safe_redirect` (n26's own). Leave
`choose._own_address` alone or fold it into the promoted helper.

### Template — `n26/core/templates/n26/introducing.html`

Extends `n26/layouts/base.html`, `{% block content %}`. Cotton only, no
hand-written Bootstrap:

- `<c-n26.page-header>` for the title and lead.
- `<c-ui.breadcrumbs>` — dashboard → gang → this screen (copy the shape from
  `n26/choose.html`).
- one `<c-n26.section>` per block, heading `{{ block.heading }}`,
  `<c-n26.rich-text :value="block.description" />` for the body, and
  `<c-n26.action-links>` carrying `<c-ui.button variant="primary">Choose
  {{ block.label }}</c-ui.button>` at `block.href`.
  `primary`, not `success` — it *starts* a form (n26 button stance).
- footer: `<c-ui.button href="{{ intro.next_url }}">Continue</c-ui.button>` when
  `intro.may_continue`, else a `<c-n26.callout>`-style line naming what is still
  needed. Confirm exact tag names against `/n26/design/` before writing —
  several cotton call-site traps fail silently
  (`n23/core/templates/CLAUDE.md`).
- Mobile-first: one column, `col-12 col-md-8`; nothing wider than the screen.

**Skippable, concretely.** There is no per-block dismiss control and nothing to
record. A skippable block simply does not appear in `blocking`, so Continue is
offered. That is the whole of "not now", and it keeps the screen stateless.
(See decision D2 if a visible "Not now" per block is wanted.)

### Re-showing

Nothing is stored, so the screen never re-shows on its own. What already
nags is the gang sheet's unresolved-slot `Note` (`effects.py:1565`). Optional
follow-up, not part of this build: on the gang sheet, when a non-skippable
slot with an interstitial is unresolved, draw a callout linking to
`n26-introducing?ask=<key>&next=<gang>` — derived, no state.

### Print and text renderers

Untouched. `n26/core/printing.py` and `n26/core/render_text.py` read cards and
never touch `Interstitial`. A guard test asserts this.

## 6. Authoring

1. **Verbs** in `n26/library/authoring.py`, beside `create_slot` (~:1020):
   - `create_interstitial(name, title="", description="", skippable=False, position=0, **kwargs)`
   - `attach_interstitial(interstitial, slot, position=0, **kwargs)` — refuses a
     duplicate with a sentence, matching `add_picklist_member`'s manner.
2. **Specs** in `n26/library/specs.py` `_build_registry()`, in the "Slots and
   picks" block (~:1052):
   - `Spec(authoring.create_interstitial, {"name": Text(...), "title": Text(...),
     "description": Text(source=(Interstitial, "description"), long=True),
     "skippable": Bool(...), "position": Int(...)})`
   - `Spec(authoring.attach_interstitial, {"slot": One(model=Slot, source=(InterstitialSlot, "slot")),
     "position": Int(...)}, model=InterstitialSlot)`
3. **Menu** — `LEAF_KINDS["interstitial"] = "create_interstitial"` in
   `n26/library/views.py:55`, placed after `"slot"`.
4. **Detail page parts** — `DETAIL_KINDS["interstitial"] = {...}`
   (`views.py:479`) with `verb: "attach_interstitial"`, `parts: "attachments"`,
   `describe: _describe_interstitial_attachment`, `parts_label: "slots"`,
   `part_name: "slot"`, a `parts_description`, a `nothing_yet`, and a
   `removes` route. `_part_sections` picks it up automatically.
5. **Descriptions** — `_describe_interstitial`, `_describe_interstitial_attachment`;
   extend `_slot_notes` (`views.py:1305`) so a Slot's own page says which
   interstitials it carries and links to them.
6. **Remove route** — an `authoring-interstitial-detach` view + url, following
   the picklist-member removal (`test_authoring_views.py` "taken off at its own
   address" tests are the shape).
7. **References** — `n26/library/references.py` so "what points at this slot"
   includes its interstitials, and deletion says what would break.
8. **Admin** — `n26/library/admin.py`, registered like the other choice models.

Guard tests already in the repo that will fail until this is complete:
`n26/library/test_authoring_index.py` (every kind backed by a spec, every verb
labelled unambiguously) and the `_kind_slugs` coverage check.

## 7. Sample data and the design system

- `n26/designsystem/sampledata.py`: an `introduction()` returning a hard-coded
  `Introduction` with three blocks — one non-skippable (Archetype, unresolved),
  one non-skippable already chosen, one skippable. Hard-coded, per that
  module's own docstring: the gallery must render on an empty database.
- A component page for `c-n26.intro-block` in `n26/designsystem/catalog.py`
  plus a demo in `demos.py`.
- A shell page `path("shell/introducing/", views.shell_introducing,
  name="shell_introducing")` in `n26/designsystem/urls.py`, so the screen is
  seen inside the real nav and footer at phone width.

## 8. Edge cases

| case | behaviour |
|---|---|
| Slot arrives already settled (`with_pick`, or a starting pick) | not asked; block dropped |
| `min_picks=0` / `max_picks=0` | never blocking; `max_picks=0` dropped entirely |
| Hidden slot | never reaches `computed.choices`; invisible here too |
| Carrier removed between act and screen | `find_slot` 404s → that block is dropped, the rest still draw |
| Every block drops | redirect straight to `next`, no empty page |
| Founding brings gang slots *and* a starting model's | one screen, blocks ordered by `position` then name |
| Same interstitial on two arriving slots | see D3 |
| Non-owner opens the address | 404 (`_own_gang_or_404`) |
| Reader navigates away | nothing re-shows; the card's existing unresolved Note remains |
| Staged interstitial | hidden unless `sees_staged(request.user)` |
| Archived interstitial or attachment | never shown |
| Address with 200 `ask` keys | capped at 20; the rest ignored |
| `next` pointing off-host | falls back to the gang sheet |
| Nested encoding: `next` inside `return` inside `next` | encode with `urlencode`/`with_query` at every hop; explicit test |
| Clone a gang | `clone_gang` writes through `assign()`, so arrivals fire — but cloning redirects to the clone, and a clone's choices are already settled, so nothing draws. Verify. |

## 9. Testing strategy

Follow `n26/tests/CLAUDE.md`: classes as narrative headings, sentence-length
test names, authoring verbs over the ORM, fixtures from
`n26/tests/fixtures.py`.

**Colocated — `n26/library/test_slots.py` (extend)**
- an interstitial is unique per pack by name
- one interstitial attaches to a slot once
- `heading` falls back to the name
- `Slot.interstitials` leaves out archived ones and keeps the attachment order

**Colocated — `n26/core/test_arrivals.py` (new)**
- `arrived()` names the slots a founding brought and nothing else
- `arrived()` names a hire's slots and not the gang's standing ones
- `arrived()` names a slot a purchase brought
- `arrived()` names a slot brought by a pick made in the same act
- a slot whose anchor predates the operation is not named
- `any_interstitials()` is one query and short-circuits the rest

**Sandbox — `n26/tests/sandbox/test_interstitials.py` (new)**
Build a slot type, picklist, two pickables, a slot given by a gang type, and an
interstitial on it. Then:
- founding a gang lands on the interstitial screen, not the gang sheet
- the screen names the choice and offers no Continue while it is unresolved
- following the Choose link, picking, and being returned lands back on the
  screen with the block answered and Continue offered
- Continue lands on the address `next` named
- a skippable interstitial offers Continue from the start
- founding a gang whose slots carry no interstitial goes straight to the sheet
- an address naming a question that has since gone draws the rest
- an address whose questions have all gone redirects to `next`
- a reader who does not own the gang gets a 404
- `next` pointing at another host falls back to the gang sheet
- **the printed sheet and the text card are byte-identical with and without an
  interstitial attached** (use `n26.core.capture.gang_state` / `differences`)
- hiring costs the same number of queries with no interstitials in the library
  as it does today (`CaptureQueriesContext`)

**Sandbox — `n26/tests/sandbox/test_authoring_views.py` (extend)**
- an interstitial is made from the menu
- a slot is attached to it from its own page, and detached at its own address
- a slot's page names the interstitials it carries

**Designsystem — `n26/designsystem/tests.py`**
- the shell page renders on an empty database

Run: `pytest n26 -n auto` (drop to `-n 4` if another agent is testing — check
`board who`). Format with `./scripts/fmt.sh`.

## 10. Risks

| risk | mitigation |
|---|---|
| An extra card derivation on every write request | `any_interstitials()` short-circuit, cached per request; only the wired views call `onward`; query-count test on hire |
| Redirect chain (`hire → introducing → choose → introducing → next`) loses the flash message | Django messages survive redirects; assert the hire confirmation renders on the interstitial screen, and decide (D4) whether it should |
| Nested query-string encoding of `next` inside `return` | encode once per hop with `with_query`/`urlencode`; explicit round-trip test |
| Importing `gyrinx.safe_redirect` by reflex | forbidden by the n26 boundary rule — use n26's own `_safe_redirect`; add it to the review checklist |
| Cotton call-site traps that fail silently | verify every tag against `/n26/design/` before writing the template (`n23/core/templates/CLAUDE.md`) |
| The anchor test misses a slot made live by a condition flip | accepted; the card's unresolved Note still says so; documented in the module docstring |
| Authoring guard tests fail halfway through the build | land the spec, the menu entry and the detail-kind entry in the same chunk |
| Founding a gang with several starting models produces a long screen | ordered by `position`; cap at 20 asks; watch it on real Outcast content |
| An interstitial's description is editor HTML | render through the same sanitiser `c-n26.rich-text` uses; never `|safe` by hand |

## 11. Build sequence

| # | chunk | files | rough size |
|---|---|---|---|
| 1 | Models + migration + `Slot.interstitials` + exports + colocated tests | `n26/library/models/slots.py`, `models/__init__.py`, one library migration, `n26/library/test_slots.py` | S |
| 2 | Authoring: verbs, specs, menu, detail-kind parts, detach route, descriptions, admin, references | `authoring.py`, `specs.py`, `views.py`, `admin.py`, `references.py`, `urls`, `test_authoring_views.py` | L |
| 3 | Arrival mechanism: `Operation._written`, `n26/core/arrivals.py`, `find_slot`/`safe_redirect` promotions, colocated tests | `operations.py`, `arrivals.py`, `views/choose.py`, `views/permissions.py`, `test_arrivals.py` | M |
| 4 | Structures + screen: `IntroBlock`/`Introduction`, the view, the url, the template, the cotton component | `render.py`, `views/introducing.py`, `urls.py`, `introducing.html`, `cotton/n26/intro_block.html` | M |
| 5 | Wire the redirects: founding, hire, choose, equip, options | `views/gangs.py`, `views/hire.py`, `views/choose.py`, `views/equip.py`, `views/options.py` | S |
| 6 | Sample data, gallery entry, shell page; sandbox suite; copy pass | `sampledata.py`, `catalog.py`, `demos.py`, `designsystem/urls.py`+`views.py`, `test_interstitials.py` | M |

Chunks 1–2 and 3–4 are independent of each other and can run in parallel.
Chunk 5 needs 3 and 4. Chunk 6 needs 4.

Run the **copywriter** agent over chunks 2, 4 and 6 (they add author- and
player-facing strings) and load the `microcopy` skill before writing any of
them.

## 12. Needs Tom's decision

- **D1 — the name in the address.** `/gangs/<id>/introducing/` is the proposal.
  "Interstitial" must not appear in a URL a player sees. Alternatives:
  `/welcome/`, `/first/`, `/decisions/`.
- **D2 — skippable, precisely.** Proposed: skippable simply means "does not
  block Continue", with no per-block control and nothing recorded. The
  alternative is a visible "Not now" per block — which needs stored state to
  mean anything, and would be the first thing in this feature that is stored.
- **D3 — one interstitial on two arriving slots.** Proposed: show it once,
  listing both questions under it. Alternative: show it twice, once per slot.
- **D4 — the act's confirmation message.** A hire's "Hired Kal — Leader, 135¢."
  will land on the interstitial screen rather than the gang sheet. Keep it
  there, or suppress it until the reader reaches `next`?
- **D5 — inline pickers.** The proposal links out to the existing pick screen
  and comes back. Rendering the picker inline on the interstitial screen is
  nicer but duplicates `choose`'s POST handling; worth it, or later?
- **D6 — feature flag.** `n26/flags.py` gates `campaigns`, `founding`,
  `built-in-propagation`, `staged-content`. Should this ship behind an
  `interstitials` flag, or is it safe to ship open given it only appears when an
  author attaches one?
- **D7 — the Archetype content itself.** This plan builds the mechanism. Whether
  the Outcast gang archetype's four duplicated Leader offers get folded into one
  slot first (`.claude/notes/archetype-today.md`, the "wart in system 1") is
  content work that changes what a founding actually shows.
- **D8 — is the gang-page nag in scope?** §5 "Re-showing" proposes it as a
  follow-up. Confirm it is out of this build.

## 13. Verification checklist

- [ ] Founding a gang whose type brings an interstitial-bearing slot lands on
      the new screen and offers no Continue until the choice is made
- [ ] Hiring a model whose profile brings one does the same
- [ ] Buying a thing that brings one does the same
- [ ] Choosing a pick that brings one does the same
- [ ] Acts that bring no interstitial land exactly where they landed before
- [ ] Continue honours `next`, and refuses an off-host address
- [ ] The address survives a reload, a share, and back/forward
- [ ] The page works with scripting off
- [ ] Print and text renderers byte-identical (`capture.differences` empty)
- [ ] Query count on hire unchanged when the library holds no interstitial
- [ ] An author can make an interstitial, attach it to a slot, and detach it
- [ ] The slot's page names its interstitials
- [ ] `/n26/design/` shows the component and the shell page at 390px
- [ ] `pytest n26 -n auto` green
- [ ] `./scripts/fmt.sh` clean
- [ ] One library migration, generated not hand-written, `manage check_migration_conflicts` clean
- [ ] No `n23.*` / `gyrinx.*` import added outside the four sanctioned seams
- [ ] Copywriter pass done on every new string; no "interstitial" in player copy
- [ ] `bandit -c pyproject.toml -r n26` clean
