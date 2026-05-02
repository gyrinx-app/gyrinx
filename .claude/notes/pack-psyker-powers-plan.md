# Pack support for psyker disciplines + powers — plan

## Scope

Pack authors can:
1. Create `ContentPsykerDiscipline` (with `name`, `generic`, new `description`)
2. Create `ContentPsykerPower` (with `name`, `discipline`, new `description`)
3. Assign disciplines to a pack fighter via `ContentFighterPsykerDisciplineAssignment` (M2M-checkbox on fighter pack form, edit-only, non-generic only)
4. Set default powers on a pack fighter via `ContentFighterPsykerPowerDefaultAssignment` (separate page accessed from the fighter card on pack detail, gated on `is_psyker`)

Subscribed lists see pack-authored disciplines, powers, discipline-assignments, and default-power-assignments via pack-aware reads.

## Model changes

Migration `0164_add_psyker_descriptions`:

- `ContentPsykerDiscipline`: add `description = TextField(blank=True)`
- `ContentPsykerPower`: add `description = TextField(blank=True)`

## Pack content-type registration

`gyrinx/core/views/pack.py` — `SUPPORTED_CONTENT_TYPES`:

```python
ContentTypeEntry(
    ContentPsykerDiscipline,
    "Psyker Disciplines",
    "Custom psyker disciplines for your Content Pack.",
    "bi-stars",
    ContentPsykerDisciplinePackForm,
    "psyker-discipline",
),
ContentTypeEntry(
    ContentPsykerPower,
    "Psyker Powers",
    "Custom psyker powers for your Content Pack.",
    "bi-magic",
    ContentPsykerPowerPackForm,
    "psyker-power",
),
```

Place in display order between Skills and Equipment groups.

## Pack forms (gyrinx/core/forms/pack.py)

### ContentPsykerDisciplinePackForm

```python
class Meta:
    model = ContentPsykerDiscipline
    fields = ["name", "generic", "description"]
    labels = {
        "name": "Name",
        "generic": "Available to all psykers?",
        "description": "Description",
    }
    help_texts = {
        "name": "The name of the discipline (e.g. 'Biomancy').",
        "generic": (
            "If checked, any psyker fighter can use powers from this discipline. "
            "Unchecked disciplines must be explicitly assigned to fighters."
        ),
        "description": "Optional flavour text or rules summary.",
    }
```

`clean_name` checks uniqueness against `.all_content()`.

### ContentPsykerPowerPackForm

```python
class Meta:
    model = ContentPsykerPower
    fields = ["name", "discipline", "description"]
```

Takes `pack` kwarg; filters `discipline` queryset via `with_packs([pack])` and groups Custom (pack) vs Default (base library) — exactly mirror `ContentSkillPackForm`.

## Pack detail page

Two new sections in pack.html mirroring skills:

- **Psyker Disciplines** — flat list (like Skill Trees section)
- **Psyker Powers** — grouped by discipline (use the same `skill_groups` shape; rename to `power_groups`)

Build the grouped structure in `pack.py` `get_context_data` like skills.

Pack fighter card updates (`fighter_preview_card.html`):
- Show assigned disciplines if `is_psyker`
- Show default powers if any
- Link to "Edit psyker disciplines" and "Edit default powers" pages from the fighter card actions

## Pack fighter form changes

`ContentFighterPackForm` (edit mode only):

- New field `psyker_disciplines` (BsCheckboxSelectMultipleCompact, queryset = `ContentPsykerDiscipline.objects.with_packs([pack]).filter(generic=False)`)
- Initial value = current discipline assignments for this fighter
- `_save_m2m` creates/deletes `ContentFighterPsykerDisciplineAssignment` rows AND corresponding `CustomContentPackItem` entries (so pack-aware reads see them)

**Default powers** are NOT on the main fighter form — instead, a separate page:

### New view: pack_fighter_default_powers

URL: `/pack/<pack_id>/fighter/<pack_item_id>/default-powers/`  (analogue of `pack-fighter-default-gear-add`)

Behaviour:
- Visible only if `fighter.is_psyker` (otherwise return 404 / show explanation page)
- Lists current default powers + remove buttons
- Add form: dropdown of available powers (from disciplines that are assigned-to-fighter OR generic; via `with_packs([pack])`)
- POST creates `ContentFighterPsykerPowerDefaultAssignment` + `CustomContentPackItem`

Templates: `pack_fighter_default_powers.html` (mirror `pack_fighter_default_gear_add.html`)

## Pack-aware read fixes (audit findings)

9 sites total; all in `core/`:

### High priority — used in subscribed list flows

1. `core/views/fighter/helpers.py:149` — `get_fighter_powers` discipline query → `ContentPsykerDiscipline.objects.with_packs(lst.packs.all())`
2. `core/views/fighter/helpers.py:156` — `get_fighter_powers` powers query → `ContentPsykerPower.objects.with_packs(lst.packs.all())`
3. `core/views/fighter/helpers.py:175–187` — `assigned_default` Exists subquery → `ContentFighterPsykerPowerDefaultAssignment.objects.with_packs(lst.packs.all())`
4. `core/views/fighter/powers.py:58` — remove-default 404 → with_packs
5. `core/views/fighter/powers.py:81` — (no fix — list-scoped)
6. `core/views/fighter/powers.py:107` — enable-default 404 → with_packs
7. `core/views/fighter/powers.py:130` — add-power 404 → with_packs

### Reverse-FK reads on Content models

8. `core/models/list.py:2499` — `ListFighter.get_available_psyker_disciplines` switch from reverse-FK to `ContentFighterPsykerDisciplineAssignment.objects.with_packs(self.list.packs.all()).filter(fighter=...)`
9. `core/models/list.py:3245` — `ListFighter.psyker_default_powers` switch reverse-FK to `with_packs`
10. `core/models/list.py:5212` — `ListFighterPsykerPowerAssignment.clean()` switch reverse-FK to `with_packs`

## Save-side: registering pack-authored Content rows

When the pack fighter form (or default-powers page) creates a `ContentFighterPsykerDisciplineAssignment` or `ContentFighterPsykerPowerDefaultAssignment`, we must ALSO create a `CustomContentPackItem` row pointing at it. Pattern matches how skills, rules, etc. are registered today (see `add_pack_item` view).

Helper extraction: `_register_pack_item(pack, content_obj, user)` — create CustomContentPackItem with appropriate ContentType. (Probably already exists somewhere; reuse.)

## Tests (TDD red-first)

New file: `gyrinx/core/tests/test_pack_psyker.py`

Form layer:
- `test_create_pack_discipline`
- `test_create_pack_discipline_with_description`
- `test_create_pack_discipline_generic_default_false`
- `test_create_pack_power`
- `test_create_pack_power_with_description`
- `test_pack_power_form_groups_disciplines_custom_default`

Pack fighter integration:
- `test_pack_fighter_form_psyker_discipline_field_excludes_generic`
- `test_pack_fighter_form_save_creates_discipline_assignment_and_pack_item`
- `test_pack_fighter_form_save_removes_dropped_discipline_assignment`

Default-powers page:
- `test_default_powers_page_404_for_non_psyker_fighter`
- `test_default_powers_page_lists_current_defaults`
- `test_default_powers_page_only_shows_powers_from_assigned_or_generic_disciplines`
- `test_default_powers_add_creates_assignment_and_pack_item`
- `test_default_powers_remove_archives_assignment_and_pack_item`

Pack-aware read regressions (subscribed list):
- `test_subscribed_list_sees_pack_discipline_in_powers_edit_view`
- `test_subscribed_list_sees_pack_power_in_powers_edit_view`
- `test_unsubscribed_list_does_not_see_pack_power_in_powers_edit_view`
- `test_subscribed_list_sees_pack_default_power_on_pack_fighter`
- `test_subscribed_list_can_disable_pack_default_power`
- `test_subscribed_list_can_re_enable_disabled_pack_default_power`
- `test_get_available_psyker_disciplines_includes_pack_assignments`
- `test_listfighter_psyker_default_powers_includes_pack_defaults`
- `test_listfighter_assignment_clean_validates_against_pack_defaults`

Templates / fighter card:
- `test_pack_fighter_card_lists_assigned_disciplines`
- `test_pack_fighter_card_lists_default_powers`

Pack detail rendering:
- `test_pack_detail_shows_psyker_disciplines_section`
- `test_pack_detail_shows_psyker_powers_section_grouped_by_discipline`

## Commit strategy

Single PR. Target ~25 tests, all green before push.

Branch: `pack-psyker-powers`
