# N26 Scenario Generator: developer handover

This document explains how the N26 Scenario Generator is built, so a
developer can maintain or extend it. For what the feature does, see
[scenario-generator.md](scenario-generator.md).

Branch: `feat/n26-scenario-generator`, based on `origin/main` at `7f620910`.
The changes are local and uncommitted.

## Design in brief

- **The page is rendered by the server, with no React and no new JavaScript.**
  The generator's whole state is in the query string, for example
  `?mode=full&deployment=6&objective=2&side_job=3&crew=1&check=…`. This
  follows the project's rule that page state belongs in the URL.
- **Roll, then redirect.** Pressing the button sends a GET with `?roll=1`.
  The view rolls once, then redirects to an address holding the rolls, so a
  reload never rolls again and the link can be shared.
- **The tables are Python constants, not library content.** They are fixed
  text that ships with the code, which follows the pattern of
  `n26/library/territory_table.py`.
- **Only the table key and roll number are stored.** Battles and log notes
  never hold an entry's text. The text is looked up from the constants when a
  page is drawn.
- **Rolled links are signed.** A rolled result carries `check`, a Django
  `Signer` signature over the campaign id and the rolls. Edited or hand-picked
  results fail the check and are treated as chosen.

## Files

### New

| File | Purpose |
| --- | --- |
| `n26/core/scenarios.py` | The four tables and every helper: rolling, parsing results, signing, log notes and descriptions. |
| `n26/core/templates/n26/scenario_generator.html` | The generator page. |
| `n26/core/templates/n26/includes/scenario_results.html` | Draws a list of results. Used by the generator, the Record a battle page and the battle page. |
| `n26/core/templates/n26/battle_outcome.html` | The outcome-only page for players. |
| `n26/core/static/n26/scenarios/deployment-{1..6}.png` | The Deployment maps. The `PLACEHOLDERS/` folder holds the old SVGs. |
| `n26/core/migrations/0079_scenario_generator.py` | Adds `Battle.scenario_rolls` and the `SCENARIO_SAVED` log kind. It merges main's two `0078` migrations. |
| `n26/core/test_scenarios.py` | Unit tests for `scenarios.py`. |
| `n26/tests/test_views_scenario_generator.py` | View tests for generating, permissions, saving and recording. |
| `n26/tests/test_views_battle_outcome.py` | View tests for players recording an outcome. |

### Changed

| File | Change |
| --- | --- |
| `n26/core/models/campaign.py` | Adds the `CampaignEvent.Kind.SCENARIO_SAVED` kind, the `Battle.scenario_rolls` field (`JSONField`, `{key: roll}`) and the `Battle.scenario_results` property. |
| `n26/core/campaigns.py` | `record_battle(..., scenario_rolls=None)` stores the rolls. Adds `save_scenario(rolls, *, rolled, name)` and `record_outcome(battle, *, result, winners, revision)`. |
| `n26/core/campaign_permissions.py` | Adds `may_record_outcome(battle, user)`. |
| `n26/core/forms.py` | Adds `ScenarioGeneratorForm` and `BattleOutcomeForm`. `BattleForm` gains hidden roll fields on add, which reach `cleaned_data` as `scenario_rolls`. |
| `n26/core/history.py` | Log wording for `SCENARIO_SAVED`, and `BATTLE_RECORDED` wording for battles that have scenario rolls. |
| `n26/core/views/campaigns.py` | Adds the `scenario_generator` and `save_scenario` views. `add_battle` reads rolls from the query string. |
| `n26/core/views/battles.py` | Adds the `record_battle_outcome` view. The battle page passes `may_record_outcome`. |
| `n26/urls.py`, `n26/core/views/__init__.py` | Register the three new routes. |
| `campaign.html`, `add_battle.html`, `battle.html` | Add the buttons, the generated-scenario box and the Scenario section. |
| `designsystem/shell/campaign.html`, `demos/view-campaign-sheet/10-sheet.html` | Mirror the new Battles button in the gallery copies, which must be edited with `campaign.html`. |
| Share control: `Share.tsx`, `templatetags/share.py`, `cotton/n26/share.html` and their tests | Optional `label` (default "Share"), `compact` (default on) and `title` props. Existing uses are unchanged. |

## Routes

| Name | Path | View | Who may use it |
| --- | --- | --- | --- |
| `n26-scenario-generator` | `campaigns/<pk>/scenario/` | `scenario_generator` | Anyone who can read the campaign (`_any_campaign_or_404`). |
| `n26-save-scenario` | `campaigns/<pk>/scenario/save/` | `save_scenario` (POST only) | Accepted players (`_plays_in`). Anyone else gets a 404. |
| `n26-campaign-battle-outcome` | `campaigns/<pk>/battles/<battle_pk>/outcome/` | `record_battle_outcome` | `may_record_outcome`. Anyone else gets a 404. |

Every route sits behind `requires_flag(CAMPAIGNS)` and `login_required`.

## `n26/core/scenarios.py`

### Data

- `ScenarioEntry(roll, name, text, image="")`. `label` is the name without a
  trailing colon or spaces, for use inside sentences.
- `ScenarioTable(key, name, entries)`. `entry(roll)` returns the entry for a
  roll, or `None`.
- `DEPLOYMENT`, `OBJECTIVE`, `SIDE_JOB` and `CREW` are the tables, and
  `TABLES` lists them in display order.
- The table keys are `deployment`, `objective`, `side_job` and `crew`. Saved
  battles and links use these keys, so do not rename them.

### Rolling and reading results

- `roll(keys, rng=None)` returns `{key: roll}` for the named tables, using
  `Dice.roll(Dice.D6, rng)`. Pass a seeded `rng` in tests.
- `results(mapping)` turns `{key: roll}` (or a `QueryDict`) into
  `ScenarioResult` objects in table order. It skips unknown keys and
  out-of-range rolls, so a hand-edited address draws what it can.
- `rolls_of(results)` turns results back into `{key: int}`.
- `choosable(mapping)` gives every table with its entries, marking the ones
  already picked. It drives the radio cards in "Choose my own".

### Signing

- `stamp(campaign_id, rolls)` signs a canonical string of the campaign id and
  the sorted rolls. The salt is `n26.core.scenarios.stamp`.
- `is_stamped(campaign_id, rolls, check)` checks a stamp in constant time.
- `generator_query(campaign_id, rolled, rolls)` builds a result's query
  string, using the mode that would have produced it and, when rolled, its
  stamp. The view, the save redirect and the log links all use it.

### Log notes

`CampaignEvent` stores no sentences, only a note that the reader turns into
one (see the model docstring).

- A `SCENARIO_SAVED` note looks like `rolled deployment=6,crew=2 Grudge match`:
  the verb, then the rolls, then the name. The name may contain spaces.
- `history_note(...)` writes a note and `read_history_note(note)` returns
  `(rolled, rolls, name)`.
- `describe(results)` returns text such as
  `Deployment 6 (Chance Encounter), Crew 2 (Patrol)`. Both log lines use it.

## Request flows

### Generating

`scenario_generator` binds `ScenarioGeneratorForm` from `request.GET`.

- `mode` is `full`, `components` or `choose`.
- `tables` lists the components to roll.
- One pick field per table key is used by "Choose my own".

The "select at least one" checks run only when `?roll` is present
(`rolling=True`), so an address that only shows a result is never refused.

The template draws every part of the form, and the radio button that is
ticked decides what shows. CSS reads the real radio with
`group-has-[input[name=mode][value=…]:checked]/scenario:…`, which is the
same technique `cotton/n26/radio_cards` uses. Parts that are hidden still
submit, but the view reads only what the chosen mode needs.

### Saving

The save form posts the rolls, `check` and `name`.

- `save_scenario` checks the stamp again on the server and does not trust the
  page.
- It runs `CampaignOperation.save_scenario` inside `campaign_operation`. The
  operation enforces accepted-player status and the name rule (1–200
  characters, the same as a battle's scenario), then writes one
  `SCENARIO_SAVED` event.
- It redirects back to `generator_query(...)` rebuilt from what was saved, so
  it never redirects to an address from the request.

### Recording a battle

**Record result** links to `n26-campaign-add-battle?deployment=6&…`.

- `add_battle` passes the rolls as initial data. `BattleForm` (add only)
  carries them as hidden `TypedChoiceField`s and collects them into
  `cleaned_data["scenario_rolls"]`.
- `record_battle` stores `rolls_of(results(...))`, which drops anything that
  is off a table.
- The Scenario name is left blank on purpose, so the reader has to give one.
- The existing `BATTLE_RECORDED` event is unchanged. `history.py` words it
  from the battle's rolls when there are any.

### Recording an outcome later

`may_record_outcome(battle, user)` is true when all of these hold:

- no outcome is recorded yet
- `may_record_campaign` is true
- the reader is the arbitrator, or owns one of the battle's gangs

`CampaignOperation.record_outcome` locks the battle, checks
`may_record_outcome` again, and calls `edit_battle` with the battle's own
scenario, date and gangs, and with the stake left as it is (`KEEP`). As a
result, the revision check, outcome validation, the `BATTLE_EDITED` event and
the rule that stakes move only when changed all come from the existing code.
The full `edit_battle` view stays arbitrator-only, and upstream's
`test_players_can_create_battles_but_cannot_edit_or_remove_them` still passes.

## Existing features reused

- `Dice.roll` from `n26/library/models/slots.py`.
- `<c-n26.die>`, `<c-n26.radio-cards>`, `<c-n26.form-page>` and
  `<c-n26.section>`.
- The share island, extended with optional props.
- `campaign_operation`, `CampaignOperation.event`, `may_record_campaign`,
  `_plays_in` and `_any_campaign_or_404`.
- The existing `BattleForm`, `record_battle` and `edit_battle`, along with
  their validation messages.

## Changing the content

Edit the entries in `n26/core/scenarios.py`. Each table must keep exactly six
entries with rolls 1–6, which `test_every_table_has_one_entry_for_each_face_of_a_d6`
checks. Do not change the `key` values. Deployment images live in
`n26/core/static/n26/scenarios/` and are referenced by the `image=` paths.

Because only keys and rolls are stored, changing the wording updates old
battles and log lines too. If an entry ever needs to read differently on old
records, that would need a new design, such as storing the text.

## Testing

```bash
.venv/bin/python -m pytest -n 4 n26/core/test_scenarios.py n26/tests/test_views_scenario_generator.py n26/tests/test_views_battle_outcome.py n26/core/test_views_share.py
npx vitest run n26/frontend/islands/share
```

There are 44 feature tests in the three new files, plus 2 share-control tests.
At handover the full N26 suite passed (8,485 tests), as did `npm run
typecheck` and `./scripts/fmt.sh`.

## Local development notes

- The worktree is `~/gyrinx-scenario-generator`, served at
  http://localhost:8811 by `./scripts/dev.sh`. Run that from the worktree,
  not from the main checkout.
- The local database has no N26 library content. Two test gang types were
  created with `create_gang_type`, and the `campaigns` feature flag was set
  to Everyone in the worktree database.
- Sign in with `/_debug/login/?user=agent` (arbitrator) or
  `?user=agent-player` (accepted player in ScenGenCamp).
- `scripts/dev.sh` needs Node 22.12 or later for Sass. On this machine that is
  Homebrew `node@24`.

## Open items

- Run the `microcopy` copy review on the new interface strings.
- In the pull request, call out the change that lets players record
  outcomes, since it changes a rule the maintainers chose.
- Consider adding these documents to `docs/SUMMARY.md`.
