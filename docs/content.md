# Content

Necromunda is a complex game. The content application within the Django project captures the static content library from which gangs can be built, campaigns can be run, and battles can be fought.

{% hint style="info" %}
The content is managed by the Gyrinx team and at time of writing is not extensible by users. However, we do have plans to support user-defined content which can be used within Gyrinx alongside the core content library.
{% endhint %}

The Django models within the content application are all prefixed with C`ontent` to help us distinguish them. The most important models are `ContentHouse`, `ContentFighter`, `ContentEquipment`, and `ContentWeaponProfile`.

There's a range of supporting models that help with default equipment assignments, equipment list items, weapon accessories, links between equipment and fighters to support exotic beasts, house additional rules for game concepts like legendary names, modifications that can allow equipment to modify weapon stats and fighter stats, page references that support linking game concepts to their rulebook entry, Psyker models around the disciplines and default assignments of powers, the rules and skills that are built into the game, and weapon accessories and traits.

Extending the core content models is one of the more complex aspects of developing Gyrinx because it requires time spent designing how to accurately capture all the possible and complex scenarios that can crop up within Necromunda.

## Managing the content library

The actual content library itself is managed directly within the Django admin application on Gyrinx. In many ways, when using Gyrinx, this is the critical part that users find valuable. A large amount of the Gyrinx team's time is spent updating content and copying information in from the rulebooks.

{% hint style="info" %}
The size and complexity of the content library can make developing Gyrinx locally difficult because you have to set up a reasonable representation of the production content library locally.

We are considering providing a development export of a representative part content library to support development & testing. If that would be useful, let's chat in the #development Discord channel.
{% endhint %}

TODO: What are the principles of the content library? How is it put together and what rules are we trying to adhere to? How are tests written?

## Extending support for new types of content

TODO: How do we think about this? What are the expectations? e.g. discuss on GitHub or Discord.&#x20;
