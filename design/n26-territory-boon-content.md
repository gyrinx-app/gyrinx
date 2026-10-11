# N26 territory boon content

The holding-choice framework is in #2911. The replacement content pass remains
tracked by #2907 and is divided into two reviewable increments: #2920 adds
baseline Income and supported standing effects; #2921 adds real alternatives
and per-holding Income eligibility. Replacement boons are not ready to launch
until both increments have been verified.

## Audited baseline and standing effects

The sources are the local core Territory reference and the House of Chains and
House of Blades journal references. These tables contain names and numeric facts;
all application summaries are original short descriptions.

| Asset | Income | Additional supported standing effect |
| --- | ---: | --- |
| Settlement | 15 | |
| Bullet Den | 15 | |
| Rogue Doc Shop | 15 | |
| Mess Shack | 15 | |
| Drinking Hole | 15 | |
| Fence Hangout | 15 | |
| Bounty Den | 25 | |
| Generatorium | 15 | +1 Reputation |
| Corpse Farm | 25 | |
| Tunnels | 20 | |
| Tech Bazaar | 15 | |
| Promethium Cache | 15 | |
| Collapsed Dome | 20 | |
| Bone Shrine | 25 | |
| Mine Workings | 20 | |
| Gambling Den | 15 | +1 Reputation |
| Synth Still | 20 | |
| Old Ruins | 20 | |
| Fighting Pit | 25 | |
| Slug House | 20 | |
| Flesh-makers Theatre | 15 | |
| Fight Arena | 15 | |
| Amneo-vats | 15 | +10 Income for Goliath |
| Feasting Hall | 20 | |
| Badzone Smelter | 20 | |
| Phelynx Pen | 20 | |
| Bio-lab | 15 | |
| Wyld Den | 15 | |
| Rogue Las Factoria | 20 | |
| Chem Arena | 15 | |
| Shivver Den | 15 | +1 Reputation for Escher |

The additional effects are ordinary typed counter contributions on the assets.
House conditions read the hidden Gang supertype pick, including a House supplied
by a Clan House Outcast choice or authored House variant. No territory names are
dispatched by the runtime. Each holding supplies its own contribution for its
current ownership period. Losing a holding removes that contribution.

## First content operation

**Add territory income and standing boons** is a separate maintenance operation.
The existing journal seed and cleanup operations stay unchanged. It requires the
system pack's Territory campaign, its Settlement and Territory asset types, and
Income and Reputation counters. The House additions also require the matching
Gang supertype picks; missing prerequisites are reported.

The preview executes the same authoring writes inside a rolled-back transaction.
Apply runs through a recorded task, with exclusive admission and a separate
operation lock. A redelivered completed task stands down. A rerun creates no
additional effects. Matching uses pack, case-insensitive name and qualifier,
then checks the asset type and the complete modifier shape. Archived or
conflicting authored content is preserved and reported.

New assets and modifiers are staged. Existing asset flags are preserved.
Staging gates discovery; it does not suspend effects for a gang already holding
the asset. Applying this operation changes existing holders' readings immediately.
It creates no recruitment rewards, equipment, credit collection or battlefield
automation. Verification must compare those unrelated player records before and
after applying it.

## Alternatives that need the next increment

| Asset | Alternative to Income | Eligibility |
| --- | --- | --- |
| Settlement | Ganger recruitment discount 25, minimum price 0 | |
| Bullet Den | Ammo-Jack recruitment discount 30 | None already held |
| Rogue Doc Shop | Rogue Doc recruitment discount 30 | None already held |
| Mess Shack | Slopper recruitment discount 30 | None already held |
| Drinking Hole | Hive Watcher recruitment discount 30 | None already held |
| Fence Hangout | Dome Runner recruitment discount 30 | None already held |
| Promethium Cache | 3 hazard suits | |
| Mine Workings | 2 respirators | |
| Flesh-makers Theatre | Forge Patcher recruitment discount 25 | Goliath, fewer than 3 held |
| Wyld Den | Wyld Runner recruitment discount 20 | Escher |
| Rogue Las Factoria | 2 lasguns | Escher |
| Chem Arena | 1 Chem-alchemy Elixir | Escher |

These are post-cycle rewards, not permanent computed equipment or grants that
run when the territory is acquired. A selectable option can record the policy,
but the reward needs a recorded action with its own timing and duplicate guards.
The recorded post-cycle executor is tracked by #2922. Trading Post benefits,
advancement or XP benefits, action restrictions and
battlefield effects also need their respective executors before being offered as
automation. A modifier that opens a cheaper collection does not implement a
recurring recruitment reward.

The next increment must explicitly identify an asset's selectable base-Income
contribution. A normal Income contribution currently cannot distinguish base
Income from an additive bonus. Neither the option name nor list order is a safe
substitute for that authoring fact. Overrides must apply only when the declared
base-Income modifier runs through that exact holding's selected option. Other
Income contributions, including House additions, remain additive. Catalogue
Income must still show the baseline when another option is selected.

Test both identical holdings with different options, including one overridden
holding, and verify the asset detail, gang section and campaign table agree.
Changing a selection, a House choice or ownership must re-evaluate the effects.
New ownership uses the first available Income option; existing holdings need an
explicit default during conversion. Zero overrides remain meaningful.

## Selectable base-Income declaration

The proposed narrow extension for #2921 is one nullable reference from Asset to
its ordinary base-Income modifier. The number remains in the counter effect;
the choice remains an ordinary Pickable assignment. Existing direct Income
continues to work. A guarded conversion moves that same modifier to the Income
Pickable and establishes the declaration. The Income editor follows that
reference, including when the authored amount is zero.

For selectable base Income, a holding does not carry a separate unconditional
override contribution. The effect uses the override amount only when the
referenced modifier runs through the recorded option for that holding's current
ownership period. Substitute the amount during effect execution, before later
counter conditions inspect readings. Final display attribution alone is too late.
House and other additive modifiers remain independent.

Initially require one visible standard single-pick gang slot directly granted
by the asset and one directly carried Income modifier on its unique Income
option. Refuse ambiguous shared or nested choice graphs and guard later edits
that invalidate the declaration. A selected stored answer remains meaningful
for its ownership period even if the offer is later hidden or dismissed.

| Selectable baseline | Selected option | Override | Base contribution |
| ---: | --- | ---: | ---: |
| 15 | Income | blank | 15 |
| 15 | Income | 42 | 42 |
| 15 | Alternative | 42 | 0 |
| 15 | Unanswered | 42 | 0 |
| 15 | Income | 0 | 0 |
| 0 | Income | 42 | 42 |

The catalogue always displays the authored baseline. An independent standing
House addition is applied on top of the selected contribution. Two holdings,
even of the same asset, must never establish each other's selection eligibility.

Before converting Settlement, extend effective contribution attribution to its
ordinary owning asset assignment. Current possession lines read catalogue Income;
only transferable holding lines read computed contributions. This boundary must
be covered by a Settlement alternative test before its real choices are seeded.
