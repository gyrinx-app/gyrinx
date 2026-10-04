# Status-offered follow-up choices

Agreed direction, 4 October 2026: a Captured result changes status and becomes a historical result. The status offers the Escape choice through authored content. Keep the existing choice machinery rather than introduce an Action flow. Issue: #2748. Deferred PRs #2790 and #2798 remain untouched.

## Authored behaviour

- Status remains the existing enum.
- Add a generic `has_status` modifier condition, with authoring and selector support.
- The carrier is an existing gang type assignment. A shared standard modifier reaches every model whose status is Captured and grants the Escape slot. Authors can attach equivalent modifiers to appropriate carriers; there is no global unattached modifier.
- Add an authored Slot flag for choices that belong to the current status revision. Add an authored Pickable flag for results retained in history rather than displayed as current choices.
- Standard Captured results retain their status effect but no longer grant Escape. Standard Escape results remain table outcomes that set status. Both are historical result records; permanent injuries remain current effects.

## Identity and writes

- Increment a model's status revision only when status actually changes. Repeating the same status writes nothing.
- Status follow-up picks store the revision they resolve. Choice addresses also include that revision, rejecting stale submissions and preventing an old pick from settling a new capture.
- Retain assignments and ledger history. No automatic removal cascade merely to change presentation.
- Remove Capture-specific manual-release handling: leaving the status naturally removes its conditional choice. Manually marking Captured offers the same authored follow-up as recording a result.

## Post-battle

- Project status changes on an in-memory model; never write during preview.
- Discover both newly offered status choices and existing pending status choices. Reuse table controls, validation and normal choose operations.
- Allow Escape in the same report or defer it to the roster/model Edit page.
- Within a result and its follow-up chain, the final selected outcome determines status. Independent conflicting result chains still ask for final status.
- Keep existing correction safeguards, idempotency and read-only preview. Preserve root/choice identities in receipts.

## UI

- Current cards show current status, persistent injuries and open status choices. Captured and completed Escape results appear in history.
- Status follow-ups use the existing choice UI and clear arrow links on the roster.
- Return from recording a lasting result to model Edit so the pending choice is visible; confirmations include actual status changes.
- No new payment checkout, counter activation requirement or ActionRecord for Escape.

## Delivery and verification

- [x] Implement generic authored condition, content flags and status revision identity.
- [x] Generate one migration leaf per app and update standard content through authoring verbs.
- [x] Integrate post-battle discovery/projection, apply and correction.
- [x] Verify manual Capture, table Capture, immediate/deferred Escape, recapture, vehicles and Clean House.
- [x] Prove renamed non-Capture content uses the same mechanism and persistent effects survive.
- [x] Verify stale submissions, repeat apply, correction, permissions and flat query growth.
- [x] Exercise mobile/desktop pages and provide test URLs/evidence.
- [ ] Format, run focused checks and the N26 suite, then open a reviewable PR.

Existing status-only and unresolved Captured models will obtain the standard choice when their carrier has the authored modifier. Existing completed results stay historical. Do not infer or backfill missing injury results from a bare status. Any later player-data repair belongs in the maintenance framework.

## Review environment

Local preview: <http://localhost:8456>. The synthetic gang is **Capture and Escape review**. Sign in as the local agent using [this one-click link](http://localhost:8456/_debug/login/?user=agent&next=%2Fn26%2Fgangs%2F01M44DSD98WKY0D0D898V6JQCS%2F).

- [ ] On the roster, **Captured by injury** and **Marked Captured by hand** both show Captured status and an Escape **Resolve →** link. Neither shows Captured as a current lasting injury.
  - Feedback:
- [ ] Open **Marked Captured by hand** and resolve Escape. Enter a roll of 6 and save Daring Escape. Status becomes In Recovery, Escape disappears from the current card, and the result appears in Result history. No Captured injury is invented.
  - Feedback:
- [ ] On that model, mark Active, then Captured again. Escape becomes available again with no old outcome selected. An earlier Escape URL should now return 404.
  - Feedback:
- [ ] Open **Escaped with a permanent injury**. Eye Injury remains on the current card; Captured and Daring Escape appear in Result history. There is no pending Escape choice.
  - Feedback:
- [ ] Open **Captured vehicle**. Resolve Escape using the same controls as a fighter; its current damage section should remain separate from the historical results.
  - Feedback:
- [ ] Open the [post-battle draft](http://localhost:8456/n26/post-battle/01M44DSFHX9J0KPB027P01ANVW/). **Post-battle Capture preview** has Captured and Daring Escape selected. The preview should say **Captured → Daring Escape**, with final status In Recovery. The roster remains Active until results are applied.
  - Feedback:
- [ ] In that draft, change Escape to None. The final status becomes Captured. Apply the report, return to the roster and resolve the pending Escape there.
  - Feedback:
- [ ] Use Correct results on the report to replace or remove its recorded results. Check the resulting status and history, and that permanent injuries are preserved. Repeat apply should not duplicate an outcome.
  - Feedback:
- [ ] Repeat the roster and model Edit checks at a narrow mobile width. Resolve links should have a small arrow; history should be readable without stretching the card.
  - Feedback:

The seeded draft is left unapplied. These examples use synthetic local data and require the local dev server to be running.
