# Pack vehicles + exotic beasts plan

Working branch: `custom-vehicles-exotic-beasts` (sits on top of the
weapon-accessory PR; will rebase onto main after that lands).

## Goal

Pack authors can define **VEHICLE** and **EXOTIC_BEAST** fighters in a
content pack. When they do, the pack also gets a corresponding
**read-only equipment item** linked to that fighter, so list-buyers can
purchase the vehicle/beast and have it spawn as a child fighter via the
existing equipment-fighter-profile signal.

## Domain model recap

- Vehicles and exotic beasts are child `ListFighter` rows spawned
  automatically when a piece of `ContentEquipment` is purchased.
- Bridge: `ContentEquipmentFighterProfile` (`content/models/equipment.py:672`)
  — `(equipment_fk, content_fighter_fk)` join row.
- Signal: `core/models/list.py:4604` `create_related_objects` — runs on
  `ListFighterEquipmentAssignment.save()`, looks up the bridge, spawns
  child fighter, sets `assignment.child_fighter` FK.
- `ContentEquipmentFighterProfile` does NOT inherit `Content`, so its rows
  are not pack-content-filtered. Lookups by `equipment_id` work for any
  pack-scoped equipment automatically.
- Cost lives on the equipment side: `ListFighter._base_cost_int` returns
  0 for child fighters.

## Decisions (locked in)

| Topic | Decision |
|---|---|
| Categories | VEHICLE + EXOTIC_BEAST only. GANG_TERRAIN deferred. |
| Auto-equipment naming | Same as fighter `type`. |
| Auto-equipment category | `"Vehicles"` (group `Vehicle & Mount`) for vehicles; `"Status Items"` (group `Gear`) for exotic beasts. Both already exist in the DB. |
| Auto-equipment cost | `equipment.cost = fighter.base_cost`. Single source of truth. |
| Editability | Visible read-only on pack detail page. No Edit/Archive on the equipment. Editing happens via the fighter only. Cost auto-syncs on fighter save. |
| Statline | Auto-pick the `ContentStatlineType` whose `default_for_categories` matches when the user picks VEHICLE / EXOTIC_BEAST. Force a picker if no default exists. |
| Pack rendering | Inline note on fighter card: "Available as equipment 'X' for Y¢". Not a separate section. |
| Equipping flow | `VehicleSelectionForm` queryset becomes pack-aware via `with_packs(list.packs.all())`. |
| Default assignments | Wire it up. The default-equipment picker for pack fighters gains the ability to assign a vehicle/beast equipment. The existing `create_related_objects` signal then spawns the child fighter when the gang is hired. |
| Out of scope | GANG_TERRAIN, vehicle damage states, decoupled equipment editing, per-pack equipment categories. |

## Verifiable outcomes (test-first list)

Tests live in `gyrinx/core/tests/test_pack_vehicles_beasts.py` (new).

### Form layer

1. `test_create_vehicle_form_allows_vehicle_category` — POST a vehicle to
   the pack create-fighter form, assert 302.
2. `test_create_vehicle_form_allows_exotic_beast_category` — same for
   exotic beasts.
3. `test_vehicle_statline_auto_selected` — when category is VEHICLE,
   the form's statline_type is auto-populated.
4. `test_exotic_beast_statline_auto_selected` — same for beasts.
5. `test_create_form_rejects_vehicle_when_no_statline_type_exists` —
   if the DB has no ContentStatlineType for VEHICLE, submission fails
   with a clear error.

### Equipment + bridge auto-creation

6. `test_creating_pack_vehicle_creates_equipment` — after POST, a
   ContentEquipment row exists with name=fighter.type, category="Vehicles",
   cost=base_cost.
7. `test_creating_pack_vehicle_creates_bridge` — a
   ContentEquipmentFighterProfile row links the new equipment to the new
   fighter.
8. `test_creating_pack_vehicle_registers_equipment_as_pack_item` — the
   equipment has a CustomContentPackItem in this pack.
9. `test_creating_pack_beast_uses_status_items_category` — beasts get
   the "Status Items" category, not "Vehicles".
10. `test_pack_vehicle_equipment_has_no_edit_or_archive_links` — view
    the pack detail page, find the auto-equipment, assert no Edit/Archive
    URL.

### Cost sync

11. `test_editing_pack_vehicle_base_cost_updates_equipment_cost` — edit
    the pack fighter's base_cost via the form, assert the linked equipment
    row's cost updates.

### Equipping flow on subscribed lists

12. `test_subscribed_list_can_buy_pack_vehicle` — VehicleSelectionForm
    queryset includes a pack vehicle for a subscribed list. POST through
    the vehicle purchase flow → child fighter spawned.
13. `test_unsubscribed_list_cannot_buy_pack_vehicle` — list not subscribed
    to the pack does not see the vehicle in the picker.
14. `test_subscribed_list_can_buy_pack_exotic_beast_via_equipment` — beast
    purchased through the regular equipment route → child fighter spawned.

### Default assignments

15. `test_default_assignment_picker_shows_pack_vehicle` — the pack-fighter
    "Default equipment" UI lists vehicle/beast equipment when adding
    defaults.
16. `test_default_vehicle_assignment_spawns_child_when_fighter_hired` —
    a pack fighter with a default vehicle assignment, when hired into a
    subscribed list, automatically gets a vehicle child fighter.

### Pack detail page

17. `test_pack_detail_shows_inline_equipment_note_on_vehicle_fighter` —
    the fighter card on the pack detail page contains the "Available as
    equipment" note with cost.

## Implementation sequence

Each step gets a commit. Red → green; never green-on-green.

1. **Plan + test file scaffolding** — write all 17 failing tests with
   markers like `@pytest.mark.skip(reason="not implemented yet")` for
   layers we haven't built. Or write them all unskipped and accept a
   long red bar that shrinks as we implement.
2. **Permit categories + statline auto-pick** — `forms/pack.py`
   - Drop VEHICLE + EXOTIC_BEAST from `_EXCLUDED_FIGHTER_CATEGORIES`
   - Auto-pick statline-type based on category
   - Tests #1-#5 pass.
3. **Auto-create equipment + bridge + pack-item** — in the pack create
   flow (`add_pack_item` in `views/pack.py` or in a `save()` override on
   ContentFighter) when category is VEHICLE/EXOTIC_BEAST.
   - Tests #6-#9 pass.
4. **Read-only display** — `pack.html` template tweak to suppress edit
   links on auto-equipment AND show inline equipment note on the fighter
   card.
   - Tests #10, #17 pass.
5. **Cost sync** — `ContentFighter.save()` hook (or signal) updates linked
   equipment's cost when base_cost changes.
   - Test #11 passes.
6. **Pack-aware vehicle picker** — `forms/vehicle.py:79` uses
   `with_packs(list.packs.all())`.
   - Tests #12-#13 pass.
7. **Pack-aware beast equipping** — verify regular equipment picker
   already shows pack beasts (likely already works post-accessory PR).
   - Test #14 passes.
8. **Default-assignment picker support** — extend
   `_build_default_equipment_choices` (or its callers) to include
   vehicle/beast equipment for pack fighters' default assignments.
   - Tests #15-#16 pass.
9. **Final pass** — full suite + format. Commit and push.

## Open risks / things to watch

- `ContentEquipmentFighterProfile.unique_together = ["equipment", "content_fighter"]`
  prevents duplicate bridges. If a pack author edits the fighter type
  (rename), we must NOT recreate the equipment — only update its name +
  cost.
- The signal at `list.py:4604` raises `ValueError` if multiple bridges
  exist for one equipment. Our auto-create flow creates one bridge per
  equipment — keep it that way.
- If a pack fighter is archived/deleted, the equipment + bridge should
  follow. CASCADE on `ContentEquipmentFighterProfile.equipment` is set,
  so deleting the equipment cascades the bridge. Need to delete the
  equipment when the fighter is deleted (or rely on `Content` archiving).
- Migration risk: zero — we're not changing any schema. All net-new
  records follow existing schemas.
