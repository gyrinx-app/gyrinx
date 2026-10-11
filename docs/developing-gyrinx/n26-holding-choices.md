# Choices from campaign holdings

A `CampaignAsset` records which gang holds a territory. The campaign owns
the territory; the gang has no Asset Assignment for it. Its library Asset
can grant a normal `Slot`, directly or through a computed carrier such as
`Hidden`.

That Slot appears on the holding gang's card and territory detail page.
The existing picker writes the selected `Pickable` as an ordinary
gang-hosted Assignment. Its modifiers, ledger entry, stored effects and
nested choices use the same pipeline as any other selected Pickable.
Holding modifiers are still computed from the CampaignAsset once, without
copying the territory into an Assignment.

## Identity and lifetime

A root pick names `chosen_for_holding`, `chosen_for_holding_revision` and
`chosen_for_slot`. Its `chosen_for` and `caused_by` are empty: the holding
is its origin, rather than an Assignment. Nested picks use ordinary
Assignment origins and causes.

The choice address is `holding:<holding id>@<ownership revision>:<Slot id>`.
Two territories from the same library Asset can select independently.
Effective acquisition, release and transfer advance `ownership_revision`.
Reacquiring the same territory creates a fresh choice with a new default;
old forms, rolls and dismissal addresses belong to the old period.

Release, transfer and leaving the campaign call ordinary recursive removal
on that period's root picks before changing ownership. This archives their
Assignment descendants and stored acquisitions in the same transaction.
Gang and campaign archive use the same leaving path. Deleting an unclaimed
holding nulls the historical reference; archived picks retain their Slot,
revision and ledger history.

Cloning excludes picks dependent on a holding and their descendants, because
a clone holds no territory. A model brought by a holding pick cannot be
cloned independently.

## Acquisition defaults

Assignment and transfer call `Operation.gain_asset` after setting the new
holder. In the same transaction, each visible, required single-pick holding
Slot selects its first available standing option in the picklist's authored
order. Put the income option first to make it the default. The selection
uses ordinary `Operation.choose`, so its Assignment, ledger and stored
effects have the same behaviour as a selection made in the picker. The owner
can replace it there.

Availability follows the receiving gang owner's staged-content visibility.
Archived members, options and packs are excluded. Staged Slots, picklists,
members and options are excluded for recipients who cannot see staged
content. Record-only options belong in history and are skipped. An empty
available list stays unselected. Optional, multiple-pick, hidden, status,
tier-ladder and rolled choices keep their own selection rules and receive
no automatic selection.

Only acquisition applies a default. Reads, content changes and repeated
assignment to the same holder preserve the current selection. A removed
pick stays unselected until the player chooses again or a new ownership
period starts. Nested choices introduced by the selected option remain available
through the ordinary picker. Each subsequent holding choice is rederived
before its default is selected, because an earlier selection can retract it.

## Write and read boundaries

Holding choice writes take the campaign lock before the gang lock, like
ownership writes. The shared picker rederives the choice inside that
transaction. `Operation.choose` also checks the current holder, ownership
revision and computed Slot. Transfers lock both gangs in key order.

`card.py` loads holdings together and carries scalar origin fields on Nodes.
It excludes choices from inactive ownership periods using those preloaded
holdings. `effects.py` preserves explicit holding origins through computed
grant chains, then resolves picks by holding, revision and Slot. Compute
and choice rendering issue no queries after loading; library hydration remains shared.

The origin adds a lifetime to standing choices. Recurring rewards, income
collection and battlefield effects require their own operations and are
separate from this choice mechanism.
