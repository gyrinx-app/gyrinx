# Battle Crews — design (battle flow step 3)

Part of epic #1346 (crew-selection half; the XP half shipped as the post-battle
editor, PR #1987). Supersedes the standalone-template approach of PR #1360 /
issue #1353 — see "Relationship to prior work" below.

## Goal

A **crew** is a virtual sub-gang assigned to a battle: which fighters attend,
with which equipment set, plus credit-consuming extras (tactics cards, hired
help). It is *not* a second `List` — it is a read-model overlay that computes
its own rating and never touches the gang's canonical caches, credits, or
`ListAction` audit stream. No hard rule enforcement; warnings come later.

Two concepts, deliberately separated:

1. **Selection recipe** — how the crew *will be* chosen ("Custom (10)",
   "Hybrid (4+D3)"). Stored on the crew; editable while the battle is
   pre-battle.
2. **Attendees** — the frozen roster after the random draw executes at battle
   start. This is what gets printed and rated. No re-rolls.

## Rules research (rule-reference mirror)

Scenario crew selection uses exactly three methods (Core Rulebook,
Battlefield Set-up; vocabulary confirmed across
`text/docs/scenarios/scenario-list/*`):

- **Custom Selection (X)** — player chooses X fighters. X can be a fixed
  number, a dice expression (e.g. D3+6 — the *count* is rolled, then the
  player picks that many), or unbounded ("Custom Selection without a number
  in brackets" = whole gang; see `arbitrator-tools/house-sub-plots`).
- **Random Selection (X)** — X drawn at random (e.g. 6, D3+4, D3+5).
- **Hybrid Selection (A+B)** — A chosen + B random (e.g. 4+D3, 3+D6, 2+2).

The dice grammar is tiny: `N`, `DX`, `DX+N` per component. Scenarios also
apply per-scenario eligibility filters (no Leader, max one Champion, no
Hangers-on/Brutes/Hired Guns in the deck — `scenarios/gang-raids-scenarios`);
we do not enforce these (warnings later).

Crew credits value is a real rules quantity: e.g. The Trap grants underdog
tactics-card draws per full 100¢ of starting-crew value difference.

**Rating ruling (from human expert, 2026-07-12):** the equipment set the
fighter brings to the battle contributes to *crew* rating; the totality of
their equipment contributes to *gang* rating. So crew rating is a
set-scoped virtual computation — this does not violate the #1853 rule that
equipment sets never touch canonical cost, because gang rating remains
full-equipment and crew rating is computed on the fly.

## Schema (baby step)

```
Crew (AppBase)
    battle          FK → Battle          # v1: crews exist only on battles
    list            FK → List            # the gang; unique (battle, list) in v1
    name            CharField (optional)
    chosen_fighters M2M → ListFighter    # the explicit "custom" picks
    random_spec     CharField            # "D3", "6", "" = none (rolled at lock)
    status          DRAFT → LOCKED       # locked at battle start; no re-draw

CrewMember (AppBase)
    crew          FK → Crew
    list_fighter  FK → ListFighter     # v1 required; later nullable (see below)
    equipment_set FK → ListFighterEquipmentSet (nullable)  # battle loadout
    was_random    bool                 # audit of the draw

CrewLineItem (AppBase)                 # generic credit-consuming line item
    crew          FK → Crew            # denormalised for easy querying
    member        FK → CrewMember (nullable)  # member-linked or crew-level
    label         CharField            # "Tactics card: Click", "Hired: Scum"
    cost          PositiveIntegerField # credits
    payment       CREDITS | FREE | PATRONAGE
    reason        CharField (blank)    # required-ish when payment=FREE
```

- **As built:** the "custom" component is a direct `chosen_fighters` M2M (the
  player picks specific fighters up front), not a `custom_spec` count. This
  keeps lock-time execution trivial — there's no "roll a count, now the absent
  player must pick that many" step. `random_spec` uses the `N | DX | DX+N`
  grammar via a ~5-line parser/validator, rolled once at lock. Known gap
  (warning-later): a *rolled custom count* (Custom Selection "D3+6") isn't
  directly representable — the player rolls it themselves and picks that many.
- Method label is derived: chosen + random → Hybrid; random only → Random;
  chosen only → Custom; neither → Custom (whole gang).
- **Line items are the payment seam.** Payment/provenance lives here, not on
  CrewMember: a roster fighter has no line item; a hired gun later gets a
  member + a linked line item ("Hired: …", credits/free/patronage). Line
  items can grow links to other objects later (add nullable FKs or a generic
  relation when needed).
- **Rating**: `crew.rating()` = Σ member fighter cost *scoped to the chosen
  equipment set* (falling back to full cost when no set) — computed on the
  fly, no caches. Line-item costs are shown as a separate "extras" total, not
  folded into fighter rating. Deltas view: crew rating vs gang rating, extras
  total, later vs opposing crews.
- **As built:** the lock also *snapshots* that rating onto
  `Crew.rating_locked` / `CrewMember.rating_locked`. The crew is a historical
  record but the gang it came from keeps changing (new gear bought, sets
  re-cut), which would otherwise silently move the rating of a battle already
  fought. This is a read-model snapshot on a virtual overlay object, not a cost
  cache: it never feeds gang rating, credits, audit, or pins, and it is never
  reconciled — where the live figure has moved, `crew.rating_drift()` reports
  it and the crew/battle pages say so. Crews locked before this shipped keep
  `rating_locked = NULL` and compute live (deliberately not backfilled).
- Implementation note: a set-scoped fighter cost does not exist yet (#1853
  made sets display-only). Build it as a pure virtual computation from the
  set's assignments; do NOT touch `cost_int()`/caches.

## Lifecycle

1. **Create** (battle in `pre_battle`): owner or arbitrator creates a crew for
   their gang on the battle page — name, specs, chosen fighters (eligibility:
   active, non-stash, non-archived — reuse the #1360 form logic), equipment
   set per fighter where applicable.
2. **Edit** freely while pre-battle.
3. **Lock at battle start** (explicit action, and/or hooked to the
   pre_battle → in_progress transition): roll `random_spec`, draw that many
   at random from eligible-not-chosen (drawing each of their cards at random
   too, per the rulebook's one-card-per-model deck), create `CrewMember` rows
   (`source=random` for draws), snapshot the rating, set status LOCKED, write a
   CampaignAction ("Crew drawn: rolled D3 = 2 → X, Y") linked to the battle.
4. Locked crews are frozen: no re-draw, no member swaps, no loadout edits. The
   equipment set each model brings is part of *selection*, not something edited
   afterwards.

## Crew-only fighters (line of sight, NOT in v1)

There will be fighters that exist *only* on a crew (hired guns for one
battle) and must never appear on the gang roster or its costs. v1 keeps
`CrewMember.list_fighter` required; the later relaxation is: make it nullable
and add the hire flow. Candidate mechanisms (decide later):

- ListFighter on the gang list with a crew-only exclusion (precedent: the
  stash fighter is excluded from active_fighters/rating everywhere — but this
  entangles list cost caches and every roster query; high blast radius).
- A separate lightweight crew-fighter object (avoids entanglement but
  duplicates fighter/equipment machinery).
- ListFighter on a hidden annex list (keeps machinery, spawns list overhead).

Non-foreclosure rules for v1: centralise a `member.fighter` accessor (never
assume `member.list_fighter.list == crew.list` inline), and keep all crew
computations independent of `List` caches. "Add fighter to crew (not gang)"
flow is explicitly out of scope for now.

## Scope cut

- **PR 1 (baby step):** models + migration, spec parser, battle-page
  pre-battle section (create/edit/lock), rating + deltas display,
  CampaignAction on lock, tests.
- **PR 2:** crew as a selectable filter in print config (#1355).
- **Later:** hire-into-crew flow (crew-only fighters), reusable templates
  ("save selection as template" — the deferred #1353), wizard chrome (#1357),
  warnings (crew size vs spec, scenario eligibility).

## Relationship to prior work

- **PR #1360** (Jan 2026, open): built a standalone reusable `CrewTemplate`
  (list-scoped, `random_count` int, full CRUD). Superseded: templates are
  deferred sugar; randomness must execute at battle start (so a fixed count
  rolled at creation is wrong); crews bind to battles. Salvage: eligibility
  queryset, chosen+random form validation, test patterns. Close #1360 with a
  note once PR 1 lands.
- **Issue mapping:** PR 1 ≈ #1354 + #1356 (the battle FK *is* the link);
  #1357 becomes the battle-page flow (wizard polish later); #1355 is PR 2;
  #1353 deferred. Dependency order in the issues is deliberately inverted.
