# Scenario generator shipping plan

The revised generator meets the agreed layout and flow: four native component
selects, controls beside the result on desktop, stacking on phones, a named-save
page, and a compact summary in the battle form. Content lives in the library.
Sharing uses the existing control. Outcome permissions are outside this change.

## Implementation

- [x] Rebase the latest author commits onto freshly fetched origin/main. Preserve
  battle archive/restore and stake revision checks, remove obsolete campaign
  flag references, and regenerate the existing migration using Django.
- [x] Preserve chosen and omitted components through saving, errors and Cancel.
- [x] Reject an entirely omitted scenario with a useful form error.
- [x] Preserve invalid hidden battle components after errors so another submit
  cannot silently remove them. Reject non-integral values in operations.
- [x] Align buttons and error states with N26. Keep native form navigation.
- [x] Fix the Share URL's escaped query separators and test reopening it.
- [x] Exercise desktop, mobile, keyboard and dark-mode flows, reader permissions,
  invalid inputs and archived campaigns and battles.
- [x] Add regression coverage, inspect query growth, and verify migrations and
  broader suites.
- [ ] Refresh PR screenshots and validation, then verify required CI checks.

## Product decision

Keep the published Tunnel Clash wording. The technical lead confirmed that
players will understand the rule; no marker-count clarification is required.

## Local verification

- Full N26 suite: 8,907 passed, one skipped and one expected failure.
- Generator query count remains 14 with one or four components.
- Current-main database upgrade and empty-database migrations both pass.
- Browser checks cover choosing, omitting, rolling, saving, cancelling and
  recording a battle, plus validation, keyboard use, mobile and dark mode.

## Release criteria

Components and selections survive navigation and validation. Malformed inputs
write nothing. Existing campaign recording permissions control saves and battle
recording. Archived battles retain their scenarios when restored. The migration
applies after current main and from an empty database. Required checks and the
manual flow pass on the final head.
