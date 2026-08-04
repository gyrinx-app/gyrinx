# Gang Attributes

## Overview

Gang attributes represent characteristics that apply to an entire list rather than to individual fighters. A list represents a user's collection of fighters (called a "gang" in Necromunda). These are properties like a list's Alignment (Law Abiding or Outlaw), its Alliance affiliations, or its broader political Affiliation within the underhive.

Attributes are defined in the content library as named categories, each with a set of allowed values. When a user creates or manages a list, they can assign values to the available attributes. These assignments have a direct mechanical effect on gameplay: they determine which equipment list expansions are available to the list, adding or removing equipment options based on the list's chosen attributes.

The attribute system is intentionally flexible. Administrators can define any number of attributes with any number of values, restrict certain attributes to specific houses, and control whether an attribute allows a single selection or multiple selections. This makes it straightforward to model both current Necromunda rules and future rule additions.

## Key Concepts

**Attribute** -- A named category of list characteristic, such as "Alignment" or "Affiliation". Each attribute has a defined set of allowed values and a selection mode (single-select or multi-select).

**Attribute Value** -- A specific option within an attribute. For example, "Law Abiding" and "Outlaw" are values within the "Alignment" attribute.

**Single-select vs Multi-select** -- An attribute marked as single-select allows only one value to be chosen per list. A multi-select attribute allows the user to pick multiple values simultaneously.

**House Restriction** -- An attribute can optionally be restricted to specific houses. If restrictions are set, only lists belonging to those houses will see the attribute. If no restrictions are set, the attribute is available to all houses.

**Attribute Assignment** -- The record that links a specific attribute value to a user's list. Assignments can be archived (soft-deleted) rather than permanently removed.

## Models

### `ContentAttribute`

Represents an attribute category that can be associated with lists.

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (unique) | The attribute name, such as "Alignment", "Alliance", or "Affiliation". Must be unique across all attributes. |
| `is_single_select` | BooleanField (default: True) | Controls selection mode. When `True`, users can pick only one value for this attribute per list. When `False`, users can select multiple values. |
| `restricted_to` | ManyToManyField to `ContentHouse` (optional) | Limits which houses can see and use this attribute. When empty, the attribute is available to all houses. |

**Ordering:** Attributes are ordered alphabetically by `name`.

**Admin interface:** The attribute admin displays each attribute's name, whether it is single-select, and a count of its values. You can filter the list by the `is_single_select` flag. The `restricted_to` field uses a horizontal filter widget for easy house selection. Attribute values are managed inline directly on the attribute's edit page.

### `ContentAttributeValue`

Represents a specific allowed value within an attribute.

| Field | Type | Description |
|-------|------|-------------|
| `attribute` | ForeignKey to `ContentAttribute` | The parent attribute this value belongs to. Deleting an attribute cascades to delete all its values. |
| `name` | CharField | The value name, such as "Law Abiding", "Outlaw", or "Chaos Cult". Must be unique within its parent attribute. |
| `description` | TextField (optional) | An optional description explaining what this value represents in the game. |

**Ordering:** Values are ordered first by their parent attribute's name, then alphabetically by their own name.

**Constraints:** The combination of `attribute` and `name` must be unique -- you cannot have two values with the same name under the same attribute.

**Admin interface:** Attribute values can be managed in two ways. You can edit them inline on the parent `ContentAttribute` page, where they appear as a tabular inline with `name` and `description` fields. You can also manage them through their own admin list, which shows name, parent attribute, and description, with search across all three fields and filtering by parent attribute.

## How It Works in the Application

### Viewing Attributes on a List

When a user views their list, the Attributes section appears alongside other list details. It shows a table with every attribute available to the list's house. Each row displays the attribute name and either the currently assigned value(s) or "Not set" if no value has been chosen. List owners see an Edit link next to each attribute.

The system determines which attributes to show by checking the `restricted_to` field on each `ContentAttribute`. An attribute appears if it has no house restrictions at all, or if the list's house is included in its `restricted_to` set.

### Editing Attributes

When the list owner clicks Edit on an attribute, they see a form tailored to the attribute's selection mode:

- **Single-select attributes** present radio buttons with all available values plus a "None" option to clear the selection.
- **Multi-select attributes** present checkboxes for all available values.

Saving the form archives any existing assignments for that attribute and creates new assignments for the selected values. If the list is in campaign mode, the change is also recorded as a campaign action.

Attribute editing is not available on archived lists.

### Effect on Equipment Availability

This is the most important downstream effect of attribute assignments. The Equipment List Expansions system uses attribute values as one of its rule types to determine which additional equipment becomes available to a list's fighters.

Attribute values drive which equipment list expansions apply. See [Equipment List Expansions](equipment-list-expansions.md) for details on configuring expansion rules.

A `ContentEquipmentListExpansionRuleByAttribute` links an expansion to a specific attribute and optionally to specific values of that attribute. When the system evaluates which expansions apply to a list:

- If the rule specifies particular attribute values, the list must have one of those values assigned for the expansion to apply.
- If the rule specifies only the attribute (with no specific values), the expansion applies as long as the list has any value set for that attribute.
- If the list has no value set for the relevant attribute, the expansion does not apply.

For example, if an equipment list expansion is configured with a rule matching the "Affiliation" attribute with the value "Chaos Cult", then only lists that have selected "Chaos Cult" as their Affiliation will gain access to the equipment items in that expansion.

### List Cloning

When a list is cloned, all active attribute assignments are copied to the new list. This happens before fighters are cloned so that equipment cost calculations on the new list can account for any expansion-based equipment that depends on attribute values.

## Common Admin Tasks

### Creating a New Attribute

1. Open the Gang Attributes section in the admin.
2. Click "Add Gang Attribute".
3. Enter the attribute `name` (e.g., "Alignment").
4. Set `is_single_select` based on the game rules. Most Necromunda attributes like Alignment are single-select.
5. If this attribute only applies to certain houses, use the `restricted_to` horizontal filter to select the relevant houses. Leave it empty if the attribute applies to all houses.
6. In the Attribute Values inline section, add each allowed value with a `name` and optional `description`.
7. Save the attribute.

After saving, the attribute will immediately appear on all applicable lists in the user-facing application.

### Adding a New Value to an Existing Attribute

1. Open the Gang Attributes section and click the attribute you want to modify.
2. Scroll down to the inline values section.
3. Add a new row with the value `name` and optional `description`.
4. Save.

The new value will immediately be available for users to select on their lists.

### Changing an Attribute from Single-Select to Multi-Select

1. Open the attribute in the admin.
2. Change `is_single_select` from checked to unchecked (or vice versa).
3. Save.

Be aware that switching from multi-select to single-select does not automatically clean up lists that already have multiple values assigned. Those existing assignments will remain, but the `ListAttributeAssignment` validation will prevent adding new conflicting assignments going forward.

### Restricting an Attribute to Specific Houses

1. Open the attribute in the admin.
2. Use the `restricted_to` horizontal filter to select the houses that should have access.
3. Save.

Lists belonging to houses not in the restriction set will no longer see this attribute. Existing assignments on those lists are not automatically removed, but the attribute will no longer appear in their Attributes section.

### Setting Up an Attribute-Based Equipment List Expansion

To make equipment availability depend on a list attribute:

1. Create the attribute and its values as described above (if they do not already exist).
2. In the Equipment List Expansion Rules section, create a new "Expansion Rule by Attribute".
3. Select the `attribute` to match on.
4. Optionally select specific `attribute_values` to match. Leave empty to match any value of that attribute.
5. Attach the rule to the relevant Equipment List Expansion.

See the [Equipment List Expansions](equipment-list-expansions.md) documentation for the full process of creating expansions and linking rules to them.
