# necromunda-2018

This directory contains the content for the Necromunda 2018 ruleset.

The two subdirectories are:

-   [`schema`](./schema/) — JSON files that encode rules for the shape of the data in the YAML files of the `data` directory
-   [`data`](./data/) — YAML files that contain the core content

## Schema

The schema files provide the expected shape of the game content within the data directory. We use these schema files to automatically check that all data is valid.

The schema files are written using the JSONSchema standard, and support features such as cross referencing between types.

### Example

Here's a simple example to illustrate a schema. This `example` schema describes a data object that has a `name` property, and `uuid` property, which is a long, unique identifier such as `8f4b4260-d58f-ff16-bf2d-ed332b93873d`.

```json
# example.schema.json
{
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "urn:gyrinx.schema.example",
    "type": "object",
    "properties": {
        "uuid": {
            "type": "string",
            "format": "uuid"
        },
        "name": {
            "type": "string"
        }
    }
}
```

In the data files, we can create data that matches this schema:

```yaml
# example.yaml
example: # must match the part of the schema filename before .schema.json
    - name: First
      uuid: 8f4b4260-d58f-ff16-bf2d-ed332b93873d
    - name: Second
      uuid: aec55ec6-2c9c-5688-9e4b-d859d8801d63
```

### Matching data to schema

The specific schema that the data files should be checked against is indicated by the top level keys of the file. For example, the list of equipment in this YAML file would be checked against the `equipment` schema:

```yaml
# data/equipment.yaml
equipment:
    - category: Ammo
      name: Anti-plant-Grenade Launcher
      trading_post_cost: 40
    - category: Ammo
      name: Chem Darts-Needle Pistol
      trading_post_cost: 10
    - category: Ammo
      name: Chem Darts-Needle Rifle
      trading_post_cost: 10
    - category: Ammo
      name: Combat Shotgun-Firestorm Ammo
      trading_post_cost: 30
    - ...
```

Content can be split across multiple files, to make organising easer. For example, we could have two equipment files for ammo and basic weapons. Both are tested against the equipment schema:

```yaml
# data/ammo.yaml
equipment:
    - category: Ammo
      name: Anti-plant-Grenade Launcher
      trading_post_cost: 40
    - ...
```

```yaml
# data/basic-weapons.yaml
equipment:
    - category: Basic Weapons
      name: Arc Rifle
      trading_post_cost: 100
    - ...
```
