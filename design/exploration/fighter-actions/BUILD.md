# Fighter actions: build order

The implementation uses ten stacked PRs. Each layer builds on the previous one;
review and merge them in this order. The stack starts at
[PR #2579](https://github.com/gyrinx-app/gyrinx/pull/2579).

| Order | Layer | What it supplies |
| --- | --- | --- |
| 1 | [Activity rename](https://github.com/gyrinx-app/gyrinx/pull/2579) | Frees the name Action while preserving existing gang activities and references. |
| 2 | [Assignable content](https://github.com/gyrinx-app/gyrinx/pull/2580) | Actions, outcomes, prices and rank tables; existing access and authoring tools; explicit tier levels. |
| 3 | [Records and counter history](https://github.com/gyrinx-app/gyrinx/pull/2581) | Earned allowances, durable action records, typed selections and structured counter events. |
| 4 | [Checkout and corrections](https://github.com/gyrinx-app/gyrinx/pull/2584) | Unpaid drafts, exact price review, atomic final payment, repeat-safe confirmation and operation receipts. |
| 5 | [Item augmentation](https://github.com/gyrinx-app/gyrinx/pull/2585) | Select a carried item, replace its tier and correct the result without paying again. |
| 6 | [Progression and standard actions](https://github.com/gyrinx-app/gyrinx/pull/2586) | Recruitment and rank allowances, saved advancement and skill rolls, all four standard actions. |
| 7 | [Existing-fighter initialisation](https://github.com/gyrinx-app/gyrinx/pull/2587) | One explicit maintenance operation using trustworthy starting XP and current XP. |
| 8 | [Card and picker display](https://github.com/gyrinx-app/gyrinx/pull/2588) | Tier effects and rating in pickers; tiers beneath equipment in screen, print, text and captured state. |
| 9 | [Fighter edit flows](https://github.com/gyrinx-app/gyrinx/pull/2589) | Action panels beneath the card, responsive step indicators, resumable forms and final review. |
| 10 | [Gallery and design record](https://github.com/gyrinx-app/gyrinx/pull/2590) | Production-component examples, an implementation guide and this reusable exploration directory. |

The shop remains generic. Actions use existing availability and assignment
concepts. Every component of a mixed price is paid together. Outcomes provide
their own validation and result handling; the shared checkout controls locking,
review, payment and completion. XP grants uses at thresholds and remains held.

## Validation

Focused tests cover payment races and stale reviews, duplicate confirmation,
correction dependencies, immutable rolls, retained allowances, authoring
validation, ownership, fixed query growth and all rendered forms. The complete
n26 suite is also run on the assembled stack; current CI results are attached to
each PR.

Real browser checks cover paid augmentation, moving a corrected augmentation to
another item, clearing glitches, the recruitment allowance and XP advancement.
Desktop and narrow layouts were inspected, including horizontal and vertical
progress indicators. Screenshots are attached to the UI PR.

Both data migrations were rehearsed separately. The Activity rename preserved
2,593 activity rows and 87 references. The counter checkpoint migration was
rehearsed forward and backward with 19,940 synthetic counters matching production
value and archive distributions. All values and references were preserved.
Production was read only for aggregate counts; no production data was changed.

## Activation and deferred work

After deployment, the maintainer must seed the standard actions and author their
profile/rule links and item tier levels. Then the one-off allowance maintenance
operation can initialise existing fighters. The
[implementation guide](../../../n26/design/fighter-actions.md) gives those steps.
Nothing in this stack runs that production activation automatically.

Explicit undo/refund, migration of collection purchases, campaign phase budgets
and an ActionRecord-to-Activity relation remain deferred. Changing a rank table
alone does nothing; no scheduler or retrospective table assessment was added.
