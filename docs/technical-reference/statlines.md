# Statlines

Statlines represent the statistical characteristics of fighters and vehicles (Movement, Weapon Skill, Ballistic Skill, etc.).

## Two Systems

Gyrinx uses two statline systems:

1. **Legacy System** - Simple stat fields on `ContentFighter` with `_override` fields on `ListFighter`
2. **New System** - Flexible custom statline types with separate override storage

The new system supports vehicles and crew with different stat requirements (e.g., Toughness Front/Side/Rear for vehicles).

## Calculation Flow

Both systems follow this pattern:

1. Get the statline from the underlying `ContentFighter`
2. Apply any overrides from the `ListFighter`
3. Apply any mods from equipment or advancements

## Performance

The new system requires careful query optimisation to avoid N+1 queries. See the models diagram below for the relationship complexity.

## Visual Examples

Custom statlines for vehicles:

<figure><img src="https://cdn.gyrinx.app/98619d14-566f-434c-9553-a3b3c2b55203.png" alt="Vehicle statline showing Front/Side/Rear toughness"><figcaption></figcaption></figure>

## Model Relationships

<figure><img src="../.gitbook/assets/gyrinx-statlines.png" alt="Statline model relationships diagram"><figcaption></figcaption></figure>
