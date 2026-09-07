# Collections

A collection defines a list of content available to a gang or fighter. A house equipment list is the simplest example: it names the items a fighter can buy and any house-specific prices. You can give the same collection to several fighter entries, so you only maintain the list once.

Giving a fighter an equipment collection adds a list to their equip page. It does not give them the equipment itself. The player still chooses and buys the items they want.

Collections also provide the fighters on a hire list and the options for some choices. Start with an equipment list; the later sections explain how those other uses differ.

## Creating an equipment list

Suppose you want to write a house equipment list and make it available to the house's fighters. Create a collection in the content library and leave **Prices its entries** on. This enables the price and restriction fields you need for equipment.

Use **Add an entry** to select an item from the library. Each entry puts that item on this list. Repeat for the other items the house offers.

An entry can override the item's credit price and Trade Point price. Leave either blank to use the corresponding reference price. These overrides belong to the collection: changing a weapon's price here does not change its price on another house's list.

The collection page's preview shows the resulting list and prices. You do not need to create sections for an equipment list; the equip page groups items by their existing library sections and categories.

Once the entries are live, add the collection to a fighter entry's built-in items. Fighters hired from that entry will have the list on their equip page. Add the same collection to the other fighter entries that use it.

For stash access, add a *gives* modifier to the gang type, naming the collection and using the scope **The gang carrying it**. That scope gives access to the stash only.

## Restricting an entry

Sometimes an item appears on a house list with a restriction, such as a heavy rock saw offered only to Forge-born. Put that restriction on the collection entry. You can restrict an entry by profile type, subtype or specific fighter entries.

This restriction applies wherever that collection is used. Restrictions on the item itself still apply too. The listing marks unmet restrictions, but allows the player to buy the item.

A rule can also grant access to a small collection. For example, to offer a familiar to Leaders and Champions, create a collection containing the familiar and give it through a modifier targeting those fighters. You do not need to add it to every house equipment list. Use **All models in the gang** when the modifier should give access across the gang, or **The model carrying it** for one model. The older **The gang carrying it and all models** scope is deprecated.

## Preparing a collection for players

You can stage entries from the authoring pages while you prepare them. Collections and their sections also support staging, but their authoring forms do not offer a staging control. Finish the entries and make them live before assigning a new collection to players.

Collections and entries can be archived. An archived entry no longer appears in the listing.

## Using a collection as a hire list

To create a hire list, add entries for the fighters it offers, with price overrides where needed. Equipment collections each have their own tab; the hire page combines fighters from the gang's collections into one hire listing.

A collection can have its own named sections. On the hire page, the collection's default section determines how the fighters are grouped. For a house's main hire list, add a section named **Gang List** and mark it as the default. The hire page then shows the collection's fighters under the usual rank headings. Capitalisation does not affect the section name's meaning. Then add the collection to the gang type's built-in items.

Add that built-in last, after the entries are live. A collection becomes the gang's main list when it and its default Gang List section are live and the gang is assigned it. If all its entries are staged or archived, players see an empty hire list. A staged collection is hidden from players; staff and players with staged-content access can preview it. Until the gang has a main hire collection, it uses the fighter entries filed under its gang type.

You can also offer extra fighters alongside the main list, such as those available through a corruption. Put them in a separate collection and assign it to the gang through a modifier on the corruption's pickable. Leave that collection without a default section to show the extra fighters *under its collection name*. To use a different heading, create a default section with that name.

The hire page merges groups with the same heading, including categories with the same name inside those groups. Two additional collections with the same default section name therefore appear together. An additional collection can also join an existing hire section by using that section's name. This combines their displayed fighters; the collections remain separate to edit. Two main hire lists each appear under their collection name instead.

| Behaviour | Equipment collections | Hire collections |
| --- | --- | --- |
| Browsing several collections | Each collection has its own tab. | Fighters from the gang's collections appear in one hire listing. |
| Collection sections | Do not affect the equip page's layout. | The default section determines where the fighters appear. |
| Matching section names | Do not combine collections. | Groups with the same heading merge, as do matching categories within them. |
| Main list | No special main-list setting. | One collection with a **Gang List** default section uses the usual rank headings. Two main lists each appear under their collection name. |

### Replacing the main list

An archetype such as an Escher Chem Cult can replace the house's hire list. Create the archetype's collection with a default section named **Gang List**. On the archetype's pickable, add two modifiers with scope **The gang carrying it**: *takes something away* for the house list, and *gives* for the archetype's list.

If you leave both lists assigned, the hire page shows them as separate groups named after their collections. See “Gang archetypes” in [Recipes](/n26/authoring/docs/recipes/) for the slot setup.

## Sections for skills and powers

Skill access is the reason collections need sections and placements. The same skill set can be Primary for one fighter and Secondary for another. The skills belong to a single collection; what changes is where their category appears for each fighter.

The standard Skills & Powers collection automatically includes every skill and power. Skill sets and power families are library categories. Primary, Secondary and Other are sections within this collection.

A **placement** is a modifier effect that puts a category in a collection section for the fighters it targets. If Agility is Primary for a fighter, add a placement to their fighter entry that puts the Agility category in Primary. Subtypes can add placements too, such as access to power families. This lets you build each fighter's skill access from the same collection.

An *offers a choice* modifier can then use one of those sections. A choice of skill from Primary offers skills from the categories placed there for that fighter. The same mechanism supports choices of power or subtype; other choices, such as Chaos gods and gang archetypes, use picklists.

Placements group content already in the collection; they do not add content to it. Categories without a placement go into the collection's default section, or under “Other” if none is set. A choice from the default section therefore includes unplaced categories too. If two placements assign the same category to different sections, the section with the lowest position wins.

The skill selection page uses the fighter's placements to determine which collections and sections to show. You do not assign Skills & Powers as you would an equipment list. Unplaced sets appear only if the fighter's placements include the default section. Without any placements, the page has no skills to select.

## The Trading Post

The standard Trading Post is another collection, but it appears on every equip page without being assigned. It automatically includes weapons, wargear and weapon accessories with a Trade Point price. You can add an entry to override the price of an included item.

During a trading trip, **Exclusive** items appear only if the collection has an explicit entry for them, marked **E**. Creating another collection called Trading Post does not replace the standard N26 Trading Post.

As with any collection, its prices are separate from how the player pays. The purchase screen controls budgets and Trade Point spending, so the same collection can be browsed as an equipment list or a trading trip.
