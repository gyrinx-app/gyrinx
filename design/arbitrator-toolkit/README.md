# N26 Arbitrator Toolkit demo

This feature runs inside the existing N26 campaign dashboard and shell. The dashboard links to the arbitrator-only toolkit with Lucide `tool-case`. Interventions, communications, alerts and tags use existing Cotton-derived React controls and theme tokens. Django validates and applies commands; the gang operation pipeline maintains roster and ledger totals.

## Run locally

From the shared contribution workspace, run `bash arbitrator-toolkit.command`. This Mac assigns [localhost:8210](http://localhost:8210) and database `gyrinx_wt_3e67c721`. The worktree is on `feat/n26-arbitrator-toolkit`, based on upstream main `13612ee4` from 11 November 2026. Upstream instructions and the relevant N26 guidance were read from that revision; no rebase or copied instruction files were needed.

Use `bash arbitrator-toolkit.command manage agent_login_url /n26/campaigns/ --username agent-toolkit` for the arbitrator. The sample campaign is **Ash Road — Arbitrator Toolkit**, with The Glass Vipers, Iron Lanterns and Sump Runners. Player logins are `agent-toolkit-ada`, `agent-toolkit-bram` and `agent-toolkit-cora`.

The idempotent sample setup is `scripts/seed_arbitrator_toolkit_demo.py`, run through this worktree's `manage shell`. It creates its own campaign and content once and leaves an existing sample campaign unchanged. Browser validation may add tags or resolve one sample choice; other players retain their independent choices. Sample rosters are synthetic, not rulebook rosters.

## Behaviour

- A single intervention can contain one reward, multiple rewards or a choice of exactly N rewards. Every selected gang chooses independently. There is no expiry. The current UI treats each listed option as one reward, with its own quantity.
- Credits are added to the gang ledger. Equipment enters the stash at its rating with no credit payment. Resources use existing gang counters. Fighter and vehicle profiles create roster models with the profile's default built-ins.
- Tags are informational. A gang or accepted player can have multiple tags, each with a name, icon and explanatory text. The arbitrator can remove tags. Tags have a separate toolkit card and assignment screen for gangs or players. Gang tags appear in the gang table; player tags appear beside players on the campaign dashboard. Narrow layouts retain icons and accessible descriptions.
- Allowed icons are `crosshair`, `gem`, `badge-cent`, `sprout`, `siren`, `octagon-x`, `user-round-shield`, `parasol`, `key-round`, `paintbrush`, `printer` and `library-big`. `user-round-shield` resolves to the pinned Lucide package's `shield-user` drawing.
- Recipients get site notifications. “Inform all gangs” announces an offer once. Each confirmed selection notifies its recipient; arbitrators can separately enable the offer-selection alert. Communications consolidate multiple gangs with the same owner. Notification bodies include a linked campaign name, and interventions and communications show the sender’s current player name and chosen badge.
- Alerts cover a player adding or removing their own gang, battle creation, battle outcomes, fighter removal from a roster, offer selections and asset ownership changes. The event registry is `ALERT_EVENTS` in `n26/core/models/toolkit.py`; domain methods call `alert_event` with a stable event identity. Further events can be added here without changing the alert editor.
- Alerts can arrive immediately, as wrap-up reports every 1–365 days, or both. Reports use fixed consecutive windows and arrive even without actions, stating “No alerted actions took place” with the covered dates. Changing the interval preserves the unreported window. Only actions selected when they occur are captured.
- The local launcher runs a DEBUG-only report clock every 30 seconds; its log is `logs/toolkit-alert-clock.log`. Application deployments use the N26-seam task route in `n26/notifications.py` every minute. Window advancement and delivery queuing are atomic; retries and catch-up do not repeat a report. No production scheduler has been deployed.
- Server commands retain their request key and canonical payload under the campaign lock. Replays do not duplicate rewards or communications. The shared workflow controller retains unresolved commands for reload and retry. Inbox deliveries are recorded in the same transaction as the command and retried separately from rewards.

## Validation and scope

Run focused Django checks with `bash arbitrator-toolkit.command pytest n26/tests/test_arbitrator_toolkit.py -n 2`. Run frontend checks with `bash arbitrator-toolkit.command npm run typecheck` and `bash arbitrator-toolkit.command npm run test:react`. The sample uses only this worktree's local database. No deployment or pull request is part of the demo setup.

Follow the repository [instructions](../../AGENTS.md), [React workflow guide](../../docs/developing-gyrinx/react.md) and [design-system skill](../../.agents/skills/design-system/SKILL.md) for follow-up work. Shared preparation currently reports missing Git metadata in older history, campaign and tactics worktrees; those unrelated worktrees were left untouched.
