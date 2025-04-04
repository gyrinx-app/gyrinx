# Lists

One of the first features Gyrinx users encounter is the list building tools. This is the biggest diversion from previous Necromunda tools which did not distinguish clearly between the actions you could take on a gang during a campaign or a battle and those carried out before or after.

In developing Gyrinx we decided that these are in fact very different activities a player undertakes, and that a separate, simple list-building feature would be useful. We began by building out the core content library and a flexible list building feature that supports experimentation in a low stakes way to help experiment with ideas and build interesting gang ideas.

## Principles of Lists

### Lists are not gangs

When list-building, users are trying ideas for a gang set up. Perhaps they have a fixed budget they are working towards, or just want to test out new ideas.

Lists and list building are unencumbered by the parts of Necromunda involved in campaigns or battle features. That means fighters cannot gain advancements or XP and the concepts of capturing and dying are not present. This allows lists to be reused and replayed and iterated on over time even as the user plays their actual list in a campaign as a gang.

Instead, taking a list into a campaign as your gang is like taking a _snapshot_ of a list, so that advancements and XP and deaths and other campaign-specific activities can be tracked separately. If the list is tweaked and changed later, the campaign version of that list that was actually played is unaffected so that there is a historical record.

{% hint style="info" %}
At time of writing, the campaign and battle features were not actually built, but the idea is that a list is converted into something that can be fought in a campaign or a battle, and the underlying list isn't unaffected.
{% endhint %}

### Immutable Layers... ish

Lists are built in a **layered, immutable approach** — as much as possible, values like cost are _calculated_ (not mutated) from the state of the list and its fighters.\
\
For example, the state (e.g. cost) of a fighter within a list (`ListFighter` model) is constructed from the following layers:

1. A **base** `ContentFighter` cost, which can be overridden...
   1. ...by the user manually
   2. ...to zero because the fighter is "linked" via equipment (e.g. Exotic Beast)
   3. ..to a cost specific to a House
2. The **sum** of the costs of the fighter's **assigned equipment** ("assignments")

The figher's assignments are constructed from two places:

1. Direct assignments (`ListFighterEquipmentAssignment` )
2. Default assigments (sourced from the `ContentFighter` )

Each assignment has its own cost, either manually set or built from the **sum** of these layers:

1. A **base** cost which can come from...
   1. the equipment list of the `ContentFighter`
   2. the Trading Post
2. The **sum** of the costs of the equipment's **weapon profiles** (e.g. special, paid-for ammo)
3. The **sum** of the costs of the equipment's **accessories** (e.g. sights)
4. The **sum** of the costs of the equipment's **upgrades** (e.g. cyberteknika)

This approach has some complexities and some advantages.

The complexities are around making sure that (to a user) there _appears_ to be no difference between "default" and "direct" assignments, and around keeping the app performance good even as we dynamically recalculate cost.

The advantage is that we can easily introduce new kinds of content, or fix bugs in the application of existing content to fighter cost, and all fighters will automatically update. It's simple to test and doesn't require us to manually update various fighter and list costs whenever anything changes.

### Trust & advise the player

A key principle of list building is that players should be allowed to do almost anything they like.

Necromunda is so complex that it's almost impossible for us to capture every rule and we would end up with a very frustrating tool if block players from taking legitimate actions.

Instead: we allow them to do whatever they like, will over time implement more and more advisory rules that feed back to the player when they're doing something that looks like it shouldn't be allowed under normal circumstances.

Examples of advisory rules that could be implemented include over-filling a fighters weapon slots or not following gang composition rulebook stipulations.

{% hint style="info" %}
At time of writing, advisory rule implementations are not yet implemented.
{% endhint %}

