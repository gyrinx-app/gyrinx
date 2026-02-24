# Weapon Profiles Display Spec

Derived from the gang screen template `list_fighter_weapon_rows.html`.

## Data model

The gang screen splits profiles into two groups:
- **`standard_profiles_cached`** — profiles that ship with the weapon (can include both unnamed and named)
- **`weapon_profiles_display`** — additional purchased profiles (always named, shown with cost)

The first decision point is **total profile count**.

## Case 1: Exactly one profile

**Condition**: `all_profiles_cached.length == 1`

```
| Weapon name (cost)  | S | L | S | L | Str | Ap | D  | Am |
|                        traits...                          |
```

- Weapon name inlined in first cell with rowspan (spans into traits row)
- Stats inline on the same row
- Traits on a second row if present, `colspan="9"` starting from column 2

## Case 2: Multiple profiles, first standard profile is unnamed (name="")

**Condition**: `all_profiles_cached.length > 1` AND `standard_profiles_cached.0.name == ""`

```
| Weapon name (cost)  | S | L | S | L | Str | Ap | D  | Am |
|                        traits for standard...             |
| – Named Prof (cost) | S | L | S | L | Str | Ap | D  | Am |
|                        traits for named...                |
```

- **No title row** — the weapon name is inlined into the first standard profile's row
- First standard profile (name=""): weapon name in first cell + stats
- Subsequent standard profiles (if they have names): `– name` prefix + stats
- Non-standard (purchased) profiles: `– name (cost)` prefix + stats
- Each profile gets its own optional traits row

## Case 3: Multiple profiles, first standard profile is named (name!="")

**Condition**: `all_profiles_cached.length > 1` AND `standard_profiles_cached.0.name != ""`

```
| Weapon name (cost)                                        |
| – Named Std (cost)  | S | L | S | L | Str | Ap | D  | Am |
|                        traits...                          |
| – Named Prof (cost) | S | L | S | L | Str | Ap | D  | Am |
|                        traits...                          |
```

- **Title row** — weapon name spans all columns (`colspan="9"`), no stats on this row
- ALL profiles (standard and non-standard) shown with `– name` prefix + stats
- Standard profiles don't show cost; non-standard show `(cost)` if non-zero

## Key details

- **Traits row**: always `colspan="9"` starting from column 2 (column 1 covered by rowspan from the name/profile cell)
- **Rowspan on first cell**: `2` if traits exist, `1` otherwise
- **Dash prefix**: `<i class="bi-dash"></i>` for all named profile rows
- **Cost display**: non-standard profiles show `(cost)` only if cost != 0; standard profiles never show cost
- **Weapon name**: in Cases 1 and 2, appears in the first `<td>` of a data row. In Case 3, appears in a dedicated title row with `align-bottom` class

## Pack context mapping

Pack profiles only have the `name=""` (standard) vs `name!=""` (named) distinction:
- Case 1: single standard profile
- Case 2: multiple profiles where the first is unnamed (standard)
- Case 3: multiple profiles where ALL are named (unlikely — pack creates a standard profile on weapon add — but handle for robustness)
