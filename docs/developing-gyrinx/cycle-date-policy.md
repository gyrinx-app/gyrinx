# Proposal: independently optional cycle dates

This is an executable proposal, not an application change. The current public
cycle editor still requires both dates or neither. The model lives in
`scripts/experiments/cycle_date_policy.py`; its tests also exercise the existing
pure schedule engine without database writes.

## Meaning of a missing date

A missing date means **unknown**, not an interval extending to infinity. It
must remain null when saving, advancing a cycle or changing future settings.
Dates describe a cycle; they never choose its order, identity or current status.

| Start | End | Recommended behavior |
| --- | --- | --- |
| Missing | Missing | Allow an undated cycle, advanced manually. |
| Set | Missing | Allow a known start with an undecided end. |
| Missing | Set | Allow a known end with an undecided start. |
| Set | Set | Allow when end is on or after start. |

Start and end on the same day describe a one-day cycle. Dates are inclusive:
a cycle ending on 13 November and another starting on 13 November conflict;
starting the next on 14 November is valid. Gaps are allowed.

A partially dated cycle necessarily includes its known date. A complete cycle
includes every day between its bounds. Those are the only occupied days the
validator can assert. It does not write the known date into the missing field.

## Relationships between cycles

**Recommendation: known dates should follow cycle order.** This would be a new
restriction: the application currently permits date ranges in reverse cycle
order when they do not overlap. The experiment tests both policies so this
choice can be reviewed before integration.

The following matrix enumerates all 16 combinations for an earlier cycle A and
a later cycle B under the recommended chronological policy. Each complete range
must also pass its own start/end check. A condition requires strict inequality
because dates are inclusive.

| A / B | Undated | Start only | End only | Both dates |
| --- | --- | --- | --- | --- |
| Undated | Allow | Allow | Allow | Allow |
| Start only | Allow | A start < B start | A start < B end | A start < B start |
| End only | Allow | A end < B start | A end < B end | A end < B start |
| Both dates | Allow | A end < B start | A end < B end | A end < B start |

Consequences:

- A starts on 13 November, end unknown; B runs 20–27 November: allow.
- Later setting A's end to 19 November: allow. Setting it to 20 November or
  later: reject unless the arbitrator also shifts the subsequent dates.
- A runs 13–20 November; B has a known start or end on 17 November: reject.
- Two start-only cycles on different days: allow in chronological order.
  Two on the same day: reject because both necessarily include that day.
- Two end-only cycles follow the same rule.
- A wholly undated cycle between two dated cycles reserves no guessed days.
  We do not require a hypothetical day for every undated cycle.
- Filling a missing bound may reveal a conflict. Clearing either bound can
  remove constraints, never introduce one.
- Archived cycles impose no constraints and are not shifted.

Allowing a partial range is provisional: it says the known dates are compatible,
not that an unknown eventual duration is guaranteed to fit. Filling dates later
must revalidate the candidate. Normal forms need no extra warning banner.

## Manual schedules and calendar projections

| Case | Recommended behavior |
| --- | --- |
| No calendar | Future projections are undated. Manual advancement still works. |
| Calendar enabled | Generated projections have complete start/end dates. |
| Edit a projected cycle | Save its required prefix and selected override; do not start a cycle. An explicitly cleared bound stays null. |
| Preview projected cycles | Read-only; save no cycles. |
| Install/change/remove a calendar | Preserve all saved bounds, including nulls. Apply settings to projections. |
| Saved partial cycle before dated projections | Every known saved date must precede the first projected start. Unknown endpoints remain unknown. |
| Start/advance/finish a cycle | Change status/current pointer and transition timestamps; do not fill planning dates from today's date. |
| Record a battle | Retain explicit cycle selection; do not infer or reject it from the battle date. |

The saved-prefix boundary is checked even under the alternative policy allowing
out-of-order saved dates: projections must still follow the saved prefix.

## Changing an end date and offering a shift

Dates never move silently. Offer an explicit choice where there are later known
saved dates or dated projections:

| Edit | Recommended offer |
| --- | --- |
| Old and new end both known | Shift subsequent dates by their difference, earlier or later. |
| Previously unknown end becomes known and reaches a later known date | Offer the smallest forward shift that puts all later known dates after the new end. |
| Previously unknown end becomes known without a conflict | No shift needed; preserve the gap. |
| End cleared | No shift; preserve all subsequent dates. |
| Every later cycle is undated and there is no calendar | Nothing to shift. |

For example, A's previously unknown end becomes 10 November and B starts on
8 November. Offer to move later dates forward three days, so B starts on
11 November. This is alignment to the new end, not a guessed change in A's old
duration. If the arbitrator declines, reject conflicting dates and keep editing.

An accepted shift moves each known bound independently. A start-only cycle stays
start-only, an end-only cycle stays end-only, and an undated cycle stays undated.
Move the future calendar by the same amount. Preserve cycle identities, ordering,
phase/source references and current selection. Revalidate the whole affected
candidate before committing; an invalid or out-of-range date rejects the action
without partial writes. A proposed shift is not itself proof that saving will
succeed, especially when moving dates earlier.

## Application integration after agreement

No schema change appears necessary: the persisted start and end columns are
already independently nullable. The following application work is still needed:

1. Replace the paired-date form/API/public-engine guards with independent-date
   validation. Existing validation skips partial ranges, so removing only those
   guards would be unsafe.
2. Apply date-order rules to newly configured or edited dates. Do not block
   unrelated operations because legacy dates are already out of order, and never
   silently reorder cycles to repair them. The experimental validator reports
   all conflicts; command integration must select the affected relationships.
3. Include known starts, not just ends, in the saved-prefix/projection boundary.
4. Preserve nulls through calendar changes. Existing `set_calendar()` defaults
   can fill missing saved bounds; explicit preservation must cover each caller.
5. Shift partial saved bounds and calendar offsets together; validate and write
   atomically through the existing locked command boundary.
6. Version changed command semantics without breaking old command receipts or
   exact retries. Update body/help text once per form, without repeated
   instructions requiring both dates.
7. Test form/API/receipt paths and native date controls. The experiment proves
   date-policy behavior and underlying representation, not public UI support.

## Verification

Run only the focused experiment:

```sh
.codex/run.sh pytest scripts/experiments/test_cycle_date_policy.py -n 0 -q
```

The tests cover all 16 date-shape pairs, inclusive boundaries, clearing dates,
shifting partial bounds, date overflow and archived entries. An independent
bounded oracle enumerates possible completed ranges for 1,296 input pairs under
each chronology policy, plus 252 saved-prefix/projection boundary cases.

Bridge tests use the actual immutable schedule engine to check that partial
bounds can be represented, prefix saving preserves them, transitions do not
invent dates, and a future-calendar offset shifts projections without changing
cycle identity. A separate test confirms that the public editor still rejects
partial dates: the proposal has not altered application behavior.
