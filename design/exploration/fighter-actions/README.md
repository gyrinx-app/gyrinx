# Fighter actions

An interactive exploration of n26 Suit Evolution and XP advancements, with the accepted design for generic assignable actions, payments and earned allowances. It supports discussion of [#2313](https://github.com/gyrinx-app/gyrinx/issues/2313) and [#2296](https://github.com/gyrinx-app/gyrinx/issues/2296).

## Open it

From the repository root on macOS:

```sh
open design/exploration/fighter-actions/index.html
```

On other systems, open `index.html` in a browser. No server, login or installation is needed. The page links to the [data model and diagrams](action-data-model.html), including the [naming comparison](action-data-model.html#naming).

Choose Suit Evolution or XP advancement at the top. Use the numbered previews to jump to a stage, or follow the buttons through the flow. The Restart button resets the current example. Progress is saved in browser local storage under `choice-payment-prototype-v7`; moving the file or changing browsers may start a fresh example. The final-checkout revision uses a new storage key so examples saved under the earlier payment order start fresh.

## What it explores

- Equipment tiers appear on the fighter card. Separate panels below it start or continue a flow on the fighter edit view.
- Suit Evolution shows the available Kill Count, price and balance after payment. Choose the item and tier before the final review. Confirmation pays and applies the result together; unfinished choices remain unpaid and can be resumed or cancelled. Each carried item has its own tier selector. Clearing glitches is the other branch.
- XP thresholds grant advancements while XP stays unchanged. The example records a roll and lets the player choose a characteristic result.
- Every form shows the flow's steps horizontally on wide screens and vertically on narrow screens.
- The data proposal covers four actions: Suit Evolution, Suit Maintenance, the Hunt Master's recruitment augmentation and model advancement. It includes entity relationships, allowance processing and atomic payment diagrams.

**Status:** the application now implements all four server-rendered flows, final checkout, recorded rolls, earned allowances and corrections. After deployment, these flows remain unavailable until counter history has been explicitly activated and n26 writes have been manually resumed. The browser page in this directory remains a historical simulation with fixed local data. It demonstrates Suit Evolution and characteristic advancement only; it does not execute the application code. The YAML records the accepted design and is not importable library content. See the [implementation guide](../../../n26/design/fighter-actions.md) for the canonical model and API details.

The implemented names are **Action** for assignable content, **ActionRecord** for one use and **Activity** for the gang task. Activity replaced the old `core.Action` name for gang founding and Trading Post visits. The naming comparison preserves the alternatives considered during design.

Corrections keep the same ActionRecord, payment, earned allowance and recorded roll. They replace the result, including moving an augmentation to another carried item, only when the original changes can be safely reversed. Both changes are recorded together and preserve the history. Refunds require a separate explicit operation. Correction controls are not included in the historical browser prototype.

Unused earned advancements remain available when Action access is removed; ordinary unpaid shop drafts recheck current access at checkout. Existing fighters are assumed to have taken no advancements, with no reconciliation of past use.

Agreed rank handling: award allowances during the player’s XP save for thresholds crossed in the current table. Changing the table itself does nothing. This requires no scheduled job, replacement baseline or table-period history.

Checkout must produce a change. Clearing glitches is available when either Glitch Count is nonzero or glitch picks remain. Campaign timing and action limits remain guidance. Explicit Undo and refund and migration of collection purchases are deferred. See [the build record](BUILD.md) for implementation order and progress.

## How it was built

The prototype was built iteratively in HTML, CSS and vanilla JavaScript, using a screenshot of the real fighter card and the Gyrinx design system as visual references. Example data and browser state transitions are embedded in `index.html`, allowing fast discussion of each screen without a database or application build. The implemented flows use server-rendered pages, URL state and Cotton components.

The data proposal was developed against existing n26 assignments, availability, slots, operations and ledger code. YAML records the proposed entities and concrete examples. A small Ruby script renders that YAML into HTML and Markdown. Python's standard library produces the diagram SVGs from fixed layouts; companion Mermaid files express the same relationships for Markdown readers. The SVGs are **not** rendered from Mermaid, so both representations need updating when a diagram changes.

The original files lived in `.claude/notes/`. They moved here on 13 September 2026 so future explorations can use the same directory structure.

## Files and rebuilding

| File | Role |
| --- | --- |
| `index.html` | Editable source of the interactive prototype; inline styles, example data and JavaScript. |
| `action-data-model.yaml` | Editable source of the proposed definitions, examples, naming comparison and decisions. |
| `data-model.template.html` | HTML shell and styles for the data-model page. |
| `build_data_model.rb` | Renders the YAML to `action-data-model.html` and `action-data-model.md`; checks several shape and reference assumptions. |
| `build_diagrams.py` | Editable SVG layouts; generates the three `action-*.svg` diagrams. |
| `action-*.mmd` | Editable Mermaid diagrams, also embedded in the generated Markdown. |
| `screenshots/current/` | Latest captures of checkout, item selection, progress, naming and diagrams. |
| `screenshots/iterations/` | Screenshots from earlier iterations; some show superseded layouts and copy. |

Edit the sources, then rebuild the generated files from the repository root:

```sh
python3 design/exploration/fighter-actions/build_diagrams.py
ruby design/exploration/fighter-actions/build_data_model.rb
```

Both builders use only their language's standard library, resolve paths relative to themselves and run without the Django environment. Generated previews are kept alongside their sources so readers can open them without rebuilding. The interactive page is edited directly and has no build step.

## Checking changes

Open both pages at desktop and phone widths. Follow item selection, leaving and resuming, final review, confirmation, cancellation, and the clear-glitches branch. Confirm that unfinished choices leave Kill Count and tiers unchanged, a repeated confirmation pays once, and changed balances or tiers require another review. In the XP example, check that an advancement leaves XP unchanged. Check the progress indicator and diagram scrolling at narrow widths.

During design these checks were also run in a fresh headless Chrome session with Playwright, with screenshots inspected afterwards. Playwright is optional verification tooling, not a dependency of the exploration. Those browser checks verify the simulation. The production payment and allowance behaviour is covered by application tests.

## Rules and code references

The rule references are the user's local n26 material: *Post-battle and post-cycle* (Advance Models, Model Ranks and Gaining Advancements), *Spyre Hunters* (Suit Evolution, Suit Maintenance and Hunt Master) and *Skills*. The full rules are not bundled here. This exploration uses n26; earlier Power Boost proposals were superseded during the discussion.

Relevant application code includes [assignable content](../../../n26/library/models/assignable.py), [modifiers and grants](../../../n26/library/models/modifier.py), [slots](../../../n26/library/models/slots.py), [access](../../../n26/core/access.py), [operations](../../../n26/core/operations.py), [ledger](../../../n26/core/models/ledger.py) and the [gang Activity](../../../n26/core/models/activity.py). The data proposal labels concepts as NEW, EXTEND or REUSE because it records the design state in which those choices were made.

The standard-content recipe defines the four actions and their supporting outcomes, prices, ranks and choices for authoring and tests. It does not seed a production database. Content authors must explicitly attach the action, rank table and advancement slot assignments to the intended profiles or rules; the runtime does not infer those bindings from names.
