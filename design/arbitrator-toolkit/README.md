# N26 Arbitrator Toolkit demo

This feature runs inside the existing N26 campaign dashboard and shell. The dashboard links to the arbitrator-only toolkit with Lucide `tool-case`. Interventions, communications, alerts and tags use existing Cotton-derived React controls and theme tokens. Django validates and applies commands; the gang operation pipeline maintains roster and ledger totals.

## Run locally

From the shared contribution workspace, run `bash arbitrator-toolkit.command`. This Mac assigns [localhost:8210](http://localhost:8210) and database `gyrinx_wt_3e67c721`. The worktree is on `feat/n26-arbitrator-toolkit`, based on upstream main `13612ee4` from 11 November 2026. Upstream instructions and the relevant N26 guidance were read from that revision; no rebase or copied instruction files were needed.

Use `bash arbitrator-toolkit.command manage agent_login_url /n26/campaigns/ --username agent-toolkit` for the arbitrator. The sample campaign is **Ash Road — Arbitrator Toolkit**, with The Glass Vipers, Iron Lanterns and Sump Runners. Player logins are `agent-toolkit-ada`, `agent-toolkit-bram` and `agent-toolkit-cora`.

The idempotent sample setup is `scripts/seed_arbitrator_toolkit_demo.py`, run through this worktree's `manage shell`. It creates its own campaign and content once and leaves an existing sample campaign unchanged. Browser validation may add tags or resolve one sample choice; other players retain their independent choices. Sample rosters are synthetic, not rulebook rosters.

## Behaviour

- A single intervention can contain one reward, multiple rewards or a choice of exactly N rewards. Every selected gang chooses independently, either on its offer page or directly in the site notification. There is no expiry. The current UI treats each listed option as one reward, with its own quantity.
- Credits are added to the gang ledger. Equipment enters the stash at its rating with no credit payment. Resources use existing gang counters. Fighter and vehicle profiles create roster models with the profile's default built-ins.
- Tags are informational. A gang or accepted player can have multiple tags, each with a name, icon and explanatory text. The arbitrator can remove tags. Tags have a separate toolkit card and assignment screen for gangs or players. Each assignment sends one tag to one or more recipients; recipients can hold multiple tags. Gang tags appear in the gang table; player tags appear beside players on the campaign dashboard. Narrow layouts retain icons and accessible descriptions.
- Allowed icons are `crosshair`, `gem`, `badge-cent`, `sprout`, `siren`, `octagon-x`, `user-round-shield`, `parasol`, `key-round`, `paintbrush`, `printer`, `library-big`, `tombstone`, `trophy` and `snail`. `user-round-shield` resolves to the pinned Lucide package's `shield-user` drawing.
- Recipients get site notifications. “Inform all gangs” announces an offer once. Each confirmed selection notifies its recipient; arbitrators can separately enable the offer-selection alert. Communications consolidate multiple gangs with the same owner. Notification bodies include a linked campaign name, and interventions and communications show the sender’s current player name and chosen badge.
- Alerts cover a player adding or removing their own gang, battle creation, battle outcomes, fighter removal from a roster, offer selections and asset ownership changes. The event registry is `ALERT_EVENTS` in `n26/core/models/toolkit.py`; domain methods call `alert_event` with a stable event identity. Further events can be added here without changing the alert editor.
- Alerts can arrive immediately, as wrap-up reports every 1–365 days, or both. Reports group actions under the selected event types, omitting empty groups. Reports use fixed consecutive windows and arrive even without actions, stating “No alerted actions took place” with the covered dates. Changing the interval preserves the unreported window. Only actions selected when they occur are captured.
- The local launcher runs a DEBUG-only report clock every 30 seconds; its log is `logs/toolkit-alert-clock.log`. Application deployments use the N26-seam task route in `n26/notifications.py` every minute. Window advancement and delivery queuing are atomic; retries and catch-up do not repeat a report. No production scheduler has been deployed.
- Server commands retain their request key and canonical payload under the campaign lock. Replays do not duplicate rewards or communications. The shared workflow controller retains unresolved commands for reload and retry. Inbox deliveries are recorded in the same transaction as the command and retried separately from rewards.

Message bodies and intervention text use the same TinyMCE configuration and authenticated image-upload service as the campaign description. Rich text renders through the N26 sanitiser and server-prepared element data on offer pages, sent messages and notifications. Plain-text examples retain their paragraph breaks. The React editor owns its lifecycle, follows the page theme and uses fresh CSRF for uploads. Site inbox choices reuse the same command, permissions, ledger operations and recovery key as the dedicated offer page.

Form groups use the Cotton-derived section spacing inside the disabled-state fieldset. The fieldset must remain a block with its own `space-y-8`; `display: contents` prevents section margins from separating the fields. Choice limits accept positive whole numbers, matching the server’s existing validation. New interventions require explicit application mode, reward type and recipients. Incomplete rewards appear in red in the review, sending stays disabled, and the final warning states that sent interventions cannot be undone.

Communications can be edited from their toolkit list. Each edit appends a revision without changing the original command receipt, updates the same notification records through retryable delivery, and retains the original title/body for the inbox’s **View original** control. Read/archive/delete state is preserved. Signed snapshots prevent stale forms from overwriting newer edits.

Tag edits update one assignment group’s definition and recipients. Retained recipients keep their existing tag records and receive no repeat notification; only newly added recipients are notified. Removed recipients lose that assignment. `assignment_key` keeps a group stable through renames and recipient changes, including existing tags grouped by the migration.

The **Arbitrator Toolkit — examples** campaign belongs to `agent-toolkit` and has a pending three-option offer at `/notifications/?q=Example+choice`, an edited-message example at `/notifications/?q=Example+message`, and an editable tag assignment. It uses separate synthetic gangs and does not change the Ash Road rosters. Tombstone uses the unmodified, licensed Lucide 1.60.0 SVG supplement documented under `n26/core/static/n26/icons/lucide/`; trophy and snail come from the pinned package.

Two explicitly labelled example wrap-ups (active and quiet periods) are in the `agent-toolkit` inbox. Open `/notifications/?q=Example+wrap-up`. They leave the campaign’s real alert preferences unchanged. Rich editor and inline-choice browser checks use the separate **Toolkit interaction checks** campaign with `agent-toolkit-preview` and `agent-toolkit-preview-player`; they do not resolve Cora’s pending original offer. Local screenshots are in the ignored `screenshots/arbitrator-toolkit-rich-text/` folder.

## Validation and scope

Run focused Django checks with `bash arbitrator-toolkit.command pytest n26/tests/test_arbitrator_toolkit.py -n 2`. Run frontend checks with `bash arbitrator-toolkit.command npm run typecheck` and `bash arbitrator-toolkit.command npm run test:react`. The sample uses only this worktree's local database. No deployment or pull request is part of the demo setup.

Follow the repository [instructions](../../AGENTS.md), [React workflow guide](../../docs/developing-gyrinx/react.md) and [design-system skill](../../.agents/skills/design-system/SKILL.md) for follow-up work. Shared preparation currently reports missing Git metadata in older history, campaign and tactics worktrees; those unrelated worktrees were left untouched.

Follow-up guidance was compared with current upstream: root repository instructions and the design-system skill match. The live gallery requires staff access; the local authenticated gallery and its component source remain the design reference. No source or dependency synchronisation was performed.
