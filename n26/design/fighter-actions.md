# Fighter actions

Fighter actions are authored capabilities that appear beneath a fighter's card on
their Edit page. `library.Action` describes a capability a fighter can receive
through the existing assignment and access systems. `core.Activity` records a
gang's campaign activity and serves a different purpose.

## Authoring

An action names its timing, its outcomes and any price paid to use it. Outcomes
are ordered through `ActionOutcome` and each outcome selects one typed operation:
augment a carried item, resolve an advancement, or apply configured changes. Add
new result behaviour as another typed handler with its own validation, preview,
application and correction functions. Keep action checkout and payment in the
shared lifecycle.

A price contains ordered `ActionPriceComponent` rows. Every component is
required: a mixed credits and counter price spends both, and repeated components
for the same balance are combined. Amounts are positive in authored content. The
payment layer records credit spending and negative counter movement in the
existing `LedgerEvent` journal.

Use the existing default assignments, modifiers and availability rules to grant
actions. Do not add action-specific access rules. Rank progression also uses the
same access calculation to find the fighter's current `RankTable` for the XP
counter.

## Runtime

Starting an action creates an unpaid draft. A player can leave and resume it.
After an advancement roll is recorded, the draft must be resumed; cancelling it
cannot release the allowance for another roll.
The draft records the selected outcome and exact targets, while balances remain
available to other operations. Review stores the normalised price and a snapshot
of the content and targets. Final confirmation locks the gang, checks that review
again, writes every payment and result, and completes the record in one database
transaction. A repeated confirmation returns the completed receipt without
paying twice.

`ActionRecord` is the durable history of the flow. Typed selection records retain
the exact assignments, picks and rolls used by an outcome. `LedgerEvent` remains
the journal for payments, counter changes, rating changes and assignment changes;
events carry action-record provenance so receipts can show what that flow changed.

## Earned uses and XP

Recruitment and rank rules grant `ActionAllowance` records. A saved XP increase
grants each allowance whose threshold is crossed, using the one effective rank
table for that XP counter at that time. XP is retained. Removing later access
stops future grants but does not remove an earned allowance. Changing a rank table
does not grant uses retrospectively.

Existing fighters are handled by the one-off maintenance operation. It compares
their original opening XP with current XP and grants crossed thresholds once. It
skips fighters whose starting value cannot be established instead of assuming a
value. Normal page rendering and later rank-table changes never run this process.

## Corrections

A correction uses the completed `ActionRecord`. It keeps the original allowance,
payment, 2D6 result and any recorded random-skill rolls. Review captures the exact
current result before confirmation. The typed handler then restores the earlier
state and applies the replacement in one transaction. A later dependent edit
prevents the correction and leaves the completed result unchanged.

Explicit undo and refunds, collection-purchase migration, campaign phase budgets
and a parent activity relation are deferred. Those additions should extend the
shared operation, payment and typed-handler boundaries rather than create a second
ledger or a general workflow language.

## Standard content and activation

The standard-content entry `fighter-actions` creates these definitions:

| Action | Use price or earned use | Outcomes |
| --- | --- | --- |
| Suit Evolution | 4 Kill Count | Augment a carried item, or clear every glitch |
| Suit Maintenance | 100 gang credits | Clear every glitch |
| Recruitment augmentation | One earned use at recruitment | Augment a carried item |
| Advancement | One earned use per crossed rank threshold | Roll 2D6 and resolve an eligible advancement |

The entry also creates the advancement table's 18 results, its skill choices and
20 rank thresholds. It does not guess which profiles or rules should grant them.
Author those links with existing built-ins or modifiers:

1. Give the progression rule the Advancement action, Standard fighter ranks and
   the hidden Advancement slot.
2. Give the Spyrer rule Suit Evolution and Suit Maintenance.
3. Give the Hunt Master profile Recruitment augmentation.
4. Mark each item's augmentation slot as `tier_ladder`, with `max_picks=1`.
   Set its picklist members' numeric levels to 1, 2 and 3. Level 0 means the
   item's empty slot; it is not a picklist member. Each tier contains its complete
   effects because choosing it replaces the previous tier.
5. After those links are ready, use the existing-fighter allowance maintenance
   operation once. It assumes none of the eligible advancements have been used.

These are content activation steps for the maintainer. The PR stack does not
change production content or run the existing-fighter operation automatically.
Existing Power Boost picks and their history remain intact.

Random skill choices preserve recorded dice. Switching to a new skill category
uses the saved die; returning to a category restores that category's accepted
result. A result that is unavailable in its category can be rolled again under
the existing skill rules. Changing categories cannot replace an accepted result
with a later category's roll.

## Code and examples

- [Content models](../library/models/actions.py) and [authoring verbs](../library/authoring.py)
- [Payment quotes](../core/action_payments.py) and [action lifecycle](../core/action_records.py)
- [Augmentation handler](../core/augmentations.py) and [advancement handler](../core/advancements.py)
- [Allowance grants](../core/allowances.py) and [one-off initialisation](../core/action_initialisation.py)
- [Flow pages](../core/views/action_flows.py) and [responsive components](../core/templates/cotton/n26/flow_progress.html)
- [Accepted YAML examples and diagrams](../../design/exploration/fighter-actions/README.md)
