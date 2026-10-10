# Founding and hire-time Trade Points

Implemented design for [issue #2753](https://github.com/gyrinx-app/gyrinx/issues/2753), 10 October 2026. Keep the existing founding action and add a separate spending action for each qualifying later hire.

## Founding completion

The existing `Activity.closed` relationship already records completion and points to a dated ledger event. Use the earliest completed founding activity's closing event as the founding boundary. Reopening or completing another founding activity does not move that boundary.

No completed founding activity means founding has not been marked complete. This applies to existing and new gangs alike. The player completes the normal founding action; no special initialisation workflow is needed.

A model's recruitment date is already stored on its membership assignment. Compare that with the first founding completion:

- Recruited before completion: founding model.
- Recruited afterwards: later hire.

Before the first completion, an open founding action enables qualifying models' personal allowances. After completion, an explicitly reopened founding action applies only to models recruited before that original boundary. Later hires use their own action. Use the dates of the actual recruitment and closing records, not an activity's modified date or a model's latest edit.

This replaces the previous proposal for an extra gang phase, a stored completion marker, a frozen group of founding models and a legacy initialisation process. Those would duplicate information already in the records.

## Player behaviour

- Rename the existing action **Spend founding TP**.
- Once completed, remove its ordinary Start suggestion. Put **Reopen action** under **Founding Trade Points** on the gang's Trade Points tab, beneath the visit form. Keep it out of the Actions square. Reopening and completion return to that tab.
- Offer **Spend hire-time TP** on a qualifying later model's Edit page, linked from the roster.
- Starting that action enables only that model's allowance. Different recruits can have independent actions open.
- Completing a personal action ends its ordinary spending opportunity. Any supported correction uses the same lifetime balance.
- Grants remain authored counter contributions. Models with no relevant grant receive no personal action. The Actions square suggests founding only when a model has founding TP; the Trade Points tab lets every eligible gang start and complete founding, including gangs with no TP grants.

Example: a Hunt Leader has 5 TP, spends 3 and finishes founding. A Hunt Champion hired afterwards can spend its own 4 TP. Opening the Champion's action leaves the Leader's remaining 2 unavailable. Explicit founding correction can expose the Leader's 2 and excludes the later Champion.

Completing ends the opportunity. Explicit correction restores its remaining balance without granting fresh points.

## Minimum implementation

Extend `Activity` with a nullable model target and a hire-time spending kind. Preserve gang-scoped founding/visit activities. Change uniqueness so there can be one open personal action per model, rather than one for the entire gang, and validate the kind/target combination and ownership.

Keep gang-scoped activity accessors intact and add batched model-scoped readers. The current kind-only activity dictionary cannot represent simultaneous recruit actions.

Generalise the existing personal TP budget reader. A model's remaining points continue to be its authored grant minus its own lifetime personal spending. Include both historical founding purchases and new hire-time purchases; ordinary visit purchases remain separate. Preserve `spent_by`, so moving equipment does not move the allowance and refunds return to the original buyer.

Keep equipment-list purchases, stash purchases, normal Trading Post visits and TP overspend confirmation as they work today. An active personal allowance remains selected when exhausted; do not silently switch to a visit's balance.

Recheck eligibility and the selected activity under the existing gang operation lock when buying or completing. A stale post must not charge a different allowance or close a replacement session. Reuse existing forms, activity cards and tallies; prepare roster information in batches with no query per model.

Use the existing `Activity` spending-session model. This does not require an authored fighter `Action`, `ActionRecord` checkout or counter-history activation.

## Existing gangs

Read their existing completion and recruitment records using the same rules. Existing purchases remain on the ledger and continue to count against the original buyer. No player-data backfill, TP purge or special gang transition is proposed.

Some later hires were equipped through the old generic action. Their spend is already recorded and reduces their allowance. The old records do not contain an individual completion for each such model; the simple approach is to let its new personal action use only the remaining balance and be completed normally. Do not reconstruct hypothetical individual sessions. This is a limited historical ambiguity, not a prerequisite for shipping the feature.

Existing reopened founding actions retain their records and adopt founding-only scope based on the first completion. A later hire previously using that generic action can start its personal action with the remaining balance. No purchases are reassigned.

The schema migration adds the personal target/kind and constraints. It does not rewrite old gang state. The existing maintenance control that opens founding on every gang is not needed to initialise this feature.

Copied models do not receive another personal allowance. Current cloning clears purchase TP and copies no activities, so test that path explicitly rather than treating copied models as fresh hires. Do not expand this feature into a general clone-history reconstruction.

## Build and verify

- [x] Rename founding and derive its first completion from existing records.
- [x] Add model-scoped activities, lifecycle operations and batched readers.
- [x] Generalise personal spending and wire the Edit/roster/Equip controls.
- [x] Verify completed founding excludes later recruits; personal completion affects only its model; repeated/stale posts preserve identity and balances.
- [x] Verify existing founding spend, refunds, sales, equipment transfers, paid weapon parts and simultaneous normal visits.
- [x] Verify existing never-completed, completed and reopened gangs without a backfill; test clones and removed models separately.
- [x] Verify permissions, no-grant action visibility, flat roster query growth and mobile/desktop interaction.
- [x] Generate one migration leaf, format, run focused tests and the N26 suite, and manually exercise the full flow.

Verification: the full N26 run passed 8,778 tests and exposed nine failures in gallery fixtures, renamed text and query-count expectations. Those were corrected, including removing a duplicate feature-flag read on Edit; the affected modules and spending/lifecycle tests then passed in a 632-test rerun. A separate rerun of all 37 gang-history tests also passed. Django checks, migration consistency, migration-overlap checks and formatting passed. The schema migration applied successfully to a realistic database snapshot.

The browser flow was exercised on desktop and mobile: start a recruit's action, buy equipment, complete it and reopen for correction with the remaining balance preserved. Ledger reconciliation passed. The roster stayed at 96 queries as the preview grew from three models to six with four open personal actions. Screenshots are saved under `screenshots/hire-time-tp/` in the task worktree.

Relevant existing code: [`Activity`](../../n26/core/models/activity.py), [`Gang`](../../n26/core/models/gang.py), [`founding.py`](../../n26/core/founding.py), [`reconcile.py`](../../n26/core/reconcile.py), [`operations.py`](../../n26/core/operations.py), and [`views/equip.py`](../../n26/core/views/equip.py).
