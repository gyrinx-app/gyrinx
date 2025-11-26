# Content

Necromunda is a complex game. The content application within the Django project captures the static content library from which gangs can be built, campaigns can be run, and battles can be fought.

{% hint style="info" %}
The content is managed by the Gyrinx team and is not currently extensible by users. We have plans to support user-defined content in the future.
{% endhint %}

The Django models within the content application are all prefixed with C`ontent` to help us distinguish them. The most important models are `ContentHouse`, `ContentFighter`, `ContentEquipment`, and `ContentWeaponProfile`.

There's a range of supporting models that help with default equipment assignments, equipment list items, weapon accessories, links between equipment and fighters to support exotic beasts, house additional rules for game concepts like legendary names, modifications that can allow equipment to modify weapon stats and fighter stats, page references that support linking game concepts to their rulebook entry, Psyker models around the disciplines and default assignments of powers, the rules and skills that are built into the game, and weapon accessories and traits.

Extending the core content models is one of the more complex aspects of developing Gyrinx because it requires time spent designing how to accurately capture all the possible and complex scenarios that can crop up within Necromunda.

## Managing the content library

The actual content library itself is managed directly within the Django admin application on Gyrinx. In many ways, when using Gyrinx, this is the critical part that users find valuable. A large amount of the Gyrinx team's time is spent updating content and copying information in from the rulebooks.

{% hint style="info" %}
The size and complexity of the content library can make developing Gyrinx locally difficult because you have to set up a reasonable representation of the production content library locally.

A development content fixture is available - see the [Content Data Management](./operations/content-data-management.md) guide for details.
{% endhint %}

## Content Library Principles

The content library follows these key principles:

1. **Accuracy** - Content should match the rulebooks as closely as possible
2. **Completeness** - All options available to players should be represented
3. **Consistency** - Similar concepts should be modelled in similar ways
4. **Testability** - Content models should be covered by automated tests

For questions about content modelling or to report content issues, please open a [GitHub issue](https://github.com/gyrinx-app/gyrinx/issues) or discuss in the #development Discord channel.

## Extending Support for New Content Types

Adding support for new content types (e.g., new gang types, equipment categories, or game mechanics) requires:

1. **Discussion** - Open a GitHub issue or Discord thread to discuss the approach
2. **Design** - Document the proposed model changes and their implications
3. **Implementation** - Create the Django models with appropriate tests
4. **Content Entry** - Add the actual game content via the admin interface

See the [Contributing Guide](../CONTRIBUTING.md) for more details on the development process.
