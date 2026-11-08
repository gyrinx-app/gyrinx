# Campaign cycles

Cycle tracking uses the `campaign-cycles` feature flag. Its migration seeds the
flag closed. Existing campaigns remain usable without configuring a schedule.
Closing the flag hides the new controls and refuses new cycle-attributed writes;
it preserves identities, receipts and committed notification deliveries.

## Boundaries

- `n26/core/schedule.py` calculates immutable schedules without database access.
  A saved cycle has an identity and authoritative order. Projected cycles have
  a plan revision and position. Planning dates never determine that position.
- `n26/core/cycles.py` owns locked commands, prefix saving, command receipts and
  transitions. It reuses `campaign_operation`; only committed transitions create
  notification deliveries. Planning and cycle selection execute no rewards.
- `n26/core/battle_workflow.py` shares validation and durable save receipts between
  HTML and JSON battle adapters. The `battle-editor` React root owns creation and
  metadata editing. It composes the shared scenario component; crews, scenario
  attachment, outcome recording and post-battle reports retain their separate
  workflow entry points.
- `CycleContext` pins a campaign and cycle for an action. `ActionRecord.cycle` and
  `LedgerEvent.cycle` are optional, so historical records need no inferred context.

## Starting a cycle-attributed action

Select and apply through the shared transaction:

```python
from n26.core import cycles

with cycles.action_operation(campaign, gang, actor=player, target=cycle_ref) as op:
    record = op.start_action(fighter, action, request_key)
```

The target can be a saved or projected reference. The operation saves a required
prefix and takes the campaign lock before gang locks. An invalid action or outer
rollback removes that prefix too. The action's request key rejects a retry with
a different cycle. Selecting a future cycle does not advance the campaign.

For an already saved context, `operation(..., cycle_context=CycleContext(...))`
validates campaign membership under those locks before creating an action.
Existing records retain their original context through application, correction,
reopening and undo:

```python
with operation(gang, actor=player) as op:
    op.complete_action(record, revision=revision, review=review, outcome=outcome)
```

Lifecycle steps use the record's cycle even after campaign advancement or a gang's
move to another campaign. Ledger creation takes no campaign lock. Unrelated work
later in the same operation uses its own campaign context. Applied terms and
payment receipts remain unchanged by subsequent schedule edits.

Cycle selection grants no collection allowance or historical reward entitlement.
Reward execution and the player post-cycle workflow are separate follow-up work.
