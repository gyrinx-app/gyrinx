# Data Model

How is content stored and how does user data overlay?

## Content

The models that store "game content" are [Content](../gyrinx/content/models.py). They hold the information that comes in the rulebooks, and support the fundemtnals of the game. You should be able to play a game on paper from the Content models.

From the user's perspective, Content is immutable (unless they are customising, which we plan to support in the future).

## Core

The [Core](../gyrinx/core/models.py) models are where user's can set up their own lists, gangs, etc. This is mutable data, owned by a specific user, to support list-building, gameplay, campaigns etc.

### List

To support the most basic use-cases for Gyrinx, we have Lists. This is the first big deviation from YakTribe's approach.

The List is there to support:

-   List building: trying out ideas with fighters, equipment, skills, hangers-on etc
-   Guides: enabling guide-writers to show their readers what the gang might look like
-   On-paper gameplay: print-outs from Lists should directly enable playing simple skimishes

In particular, Lists have a "live" total cost: as fighters are added, and equipment is added to those fighters, the total cost of the List changes. Lists do not have a "budget" per-se, because they are not associated with a campaign. This makes them useful for List-building and experimentation.

The following restrictions apply to Lists:

-   They do not support gameplay modes — the fighters can be modified, but not in a way that tracks what is happening in gameplay
-   They cannot be taken into campaigns
