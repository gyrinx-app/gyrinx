# N26 Scenario Generator: developer handover

This document explains how the N26 Scenario Generator is built, so a
developer can maintain or extend it. For what the feature does, see
[scenario-generator.md](scenario-generator.md).

## Design in brief

- **The pages are rendered by the server, with no React and no new
  JavaScript.** The generator is a GET form of four native selects. The
  battle form's details section is a native `<details>` element.
- **Roll, then redirect.** **Generate scenario** submits `?generate=1`. The
  view resolves every table once, rolling where asked, then redirects to an
  address that holds the result. A reload never rolls again, and the
  standard **Share** control passes the same scenario on.
- **The address carries the result and the choices.** Each result is under
  its table's key, and each choice that is not the default is under
  `<key>_pick`. For example,
  `?deployment_pick=3&side_job_pick=leave&deployment=3&objective=4&crew=4`
  means Deployment was chosen, Side job was left out, and Objective and Crew
  were rolled. **Generate again** keeps the choices and rolls the rest
  again.
- **The content lives in the library and is read by core.**
  `n26/library/scenario_tables.py` holds the fixed definitions.
  `n26/core/scenarios.py` rolls, checks and describes scenarios.
- **Only the table key and roll are stored.** Battles and log notes never
  hold an entry's text. The text is looked up when a page is drawn.
- **Checking is strict.** A supplied component that is not on its table
  refuses the whole scenario. A component left out is valid.

## Files

### New

| File | Purpose |
| --- | --- |
| `n26/library/scenario_tables.py` | `ScenarioEntry`, `ScenarioTable`, the four tables, `TABLES` and `table(key)`. |
| `n26/core/scenarios.py` | `ScenarioResult`, `roll`, `parse`, `results`, `rolls_of`, `describe`, and the log-note helpers. |
| `n26/core/templates/n26/scenario_generator.html` | The generator page. |
| `n26/core/templates/n26/save_scenario.html` | The **Save scenario** page. |
| `n26/core/templates/n26/includes/scenario_results.html` | Full results: the table, the entry, the die, the description and the map. |
| `n26/core/templates/n26/includes/scenario_summary.html` | A compact list of each table and its entry. |
| `n26/core/static/n26/scenarios/deployment-{1..6}.png` | The Deployment maps. |
| `n26/core/migrations/0079_scenario_generator.py` | Adds `Battle.scenario_rolls` and the `SCENARIO_SAVED` log kind. It was regenerated on current main with `makemigrations`. |
| `n26/library/test_scenario_tables.py` | Tests for the content: six entries per table, and that the maps ship. |
| `n26/core/test_scenarios.py` | Unit tests for `scenarios.py`. |
| `n26/tests/test_views_scenario_generator.py` | View tests for generating, saving, permissions and recording a battle. |

### Changed

| File | Change |
| --- | --- |
| `n26/core/models/campaign.py` | Adds the `CampaignEvent.Kind.SCENARIO_SAVED` kind and the `Battle.scenario_rolls` field (a `JSONField` holding `{key: roll}`). |
| `n26/core/campaigns.py` | `record_battle(..., scenario_rolls=None)` checks and stores the rolls. Adds `save_scenario(rolls, *, name)`. |
| `n26/core/forms.py` | Adds `ScenarioGeneratorForm` (the four `<key>_pick` selects), `ScenarioComponentsMixin` (the hidden component fields) and `SaveScenarioForm`. `BattleForm` uses the mixin when a battle is added. |
| `n26/core/history.py` | Words the `SCENARIO_SAVED` log line. `BATTLE_RECORDED` is unchanged. |
| `n26/core/views/campaigns.py` | Adds the `scenario_generator` and `save_scenario` views. `add_battle` reads and checks the rolls. |
| `n26/core/views/battles.py` | The battle page passes `scenario_results`. |
| `n26/urls.py`, `n26/core/views/__init__.py` | Register the two new routes. |
| `campaign.html`, `add_battle.html`, `battle.html` | Add the **Generate scenario** button, the components box and the Scenario section. |
| `designsystem/shell/campaign.html`, `demos/view-campaign-sheet/10-sheet.html` | Mirror the new Battles button in the gallery copies of the campaign page, which must be kept in step with `campaign.html`. |

## Routes

| Name | Path | View | Who may use it |
| --- | --- | --- | --- |
| `n26-scenario-generator` | `campaigns/<pk>/scenario/` | `scenario_generator` | Anyone who can read the campaign (`_any_campaign_or_404`). |
| `n26-save-scenario` | `campaigns/<pk>/scenario/save/` | `save_scenario` (GET and POST) | `may_record_campaign`, through `_recording_campaign_or_404`: the arbitrator and accepted players, on a campaign that is not archived. |

Both routes sit behind `requires_flag(CAMPAIGNS)` and `login_required`.
Every redirect is built with `reverse(...)`.

## The content: `n26/library/scenario_tables.py`

- `ScenarioEntry(roll, name, text, image="")`. Its `label` is the name
  without a trailing colon or spaces, for use inside sentences.
- `ScenarioTable(key, name, entries)`. `entry(roll)` returns the entry for
  that roll, or `None`.
- The keys are `deployment`, `objective`, `side_job` and `crew`. Links and
  saved battles name these keys and rolls, so do not change them.
- Names and text can change freely. Older battles and log lines show the new
  wording.

## The logic: `n26/core/scenarios.py`

- `roll(keys, rng=None)` rolls a D6 with `Dice.roll(Dice.D6, rng)` for each
  named table. Pass a seeded `rng` in tests.
- `parse(mapping)` returns `(results, wrong)`. It reads the value under each
  table's key. A missing or blank value means the table was left out. A value
  that is not 1 to 6 goes into `wrong`.
- `results(mapping)` is `parse` that returns nothing if anything is wrong.
- `rolls_of(results)` returns `{key: int}`.
- `describe(results)` returns text such as
  `Deployment 6 (Chance Encounter), Crew 2 (Patrol)`.
- `history_note(rolls, name)` and `read_history_note(note)` write and read a
  `SCENARIO_SAVED` note, such as `deployment=6,crew=2 Vent ambush`. The name
  may contain spaces.

## Request flows

### Generating

`ScenarioGeneratorForm` binds to `request.GET`.

- Each table's field is `<key>_pick`. Its value is `roll`, `leave` or a roll
  from 1 to 6. A missing value means `roll`.
- `generate()` resolves the scenario.
- `chosen_picks()` returns only the choices that are not the default, so
  the link stays short.

When the page draws a result, it uses `parse(request.GET)`. A wrong component
shows an error and no scenario.

### Saving

**Save to log** links to `n26-save-scenario?deployment=…`.

1. The GET shows the summary and a `SaveScenarioForm`. The components ride
   as hidden fields, and **Cancel** returns to the same scenario.
2. The POST validates the form: a required name of up to 200 characters,
   every component on its table, and at least one component.
3. If the form is valid, the view calls `CampaignOperation.save_scenario`.
   The operation checks the permission through `_require_recorder`, then
   checks the name and the components again, and writes one `SCENARIO_SAVED`
   event.
4. Errors render the bound form, so the name and the scenario stay visible.
5. On success the view redirects to the generator with the saved scenario.

### Recording a battle

**Record a battle** links to `n26-campaign-add-battle?deployment=…`.

- `add_battle` uses `parse` on the GET. A wrong component attaches nothing
  and says so.
- `BattleForm` carries the components through `ScenarioComponentsMixin`.
  Hidden fields cannot show errors of their own, so a wrong component
  becomes one error on the form.
- `record_battle` refuses wrong components again, then stores
  `rolls_of(...)` in `Battle.scenario_rolls`.
- The scenario name starts blank. Validation errors keep the hidden
  components and the fields already entered.

## Existing features reused

- `Dice.roll` from `n26/library/models/slots.py`.
- `<c-n26.share>` (the standard Share control), `<c-n26.die>`,
  `<c-n26.page-header>`, `<c-n26.section>`, `<c-n26.form-page>` and
  `<c-n26.form-section>`, plus the `c-ui` fields, native selects and buttons.
- `campaign_operation`, `CampaignOperation.event`, `_require_recorder`,
  `may_record_campaign` and `_recording_campaign_or_404`.
- The existing `BattleForm` and `record_battle`, and the battle scenario's
  name rule and message.

## Testing

```bash
.venv/bin/python -m pytest -n 4 n26/library/test_scenario_tables.py n26/core/test_scenarios.py n26/tests/test_views_scenario_generator.py
```

The full N26 suite also passes: `.venv/bin/python -m pytest -n 4 n26`. Check
migrations with `manage makemigrations --check`,
`manage check_migration_conflicts` and
`manage check_migration_overlap --base origin/main`.

## Local development

- Use a dedicated worktree, for example `~/gyrinx-scenario-generator`, and
  start it with `./scripts/dev.sh` from that worktree. The script prints the
  worktree's own URL, which is a port from 8100 to 9599. Port 8000 belongs to
  the main checkout. On this machine the worktree uses
  http://localhost:8811.
- `scripts/dev.sh` needs Node 22.12 or later, because Sass needs it. The CI
  workflows use Node 24.
- A database copied from a fresh `gyrinx_main` has no N26 library content
  and the `campaigns` feature flag is off. Turn the flag on with
  `FeatureFlag` in `manage shell`, and create a test gang type with
  `n26.library.authoring.create_gang_type`.
- Sign in through the dev-only link printed by
  `manage agent_login_url /n26/campaigns/`, or with
  `/_debug/login/?user=agent-<purpose>`.
