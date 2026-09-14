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

A price contains ordered `ActionPriceComponent` assignments. Every component is
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
