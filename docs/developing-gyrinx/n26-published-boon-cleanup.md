# Remove published journal boon placeholders

The retired journal seed created eleven empty **Goliath Controlled** and
**Escher Controlled** rules, with modifiers on their named territories. The
journal content update removes unchanged staged placeholders. Published
placeholders need the separate **n26: remove published journal boon
placeholders** maintenance operation.

## Deployment and run order

After deploying both maintenance entries, open **Admin → Maintenance**:

1. Preview and run **n26: update journal territories and gang supertypes**.
   This updates the journal catalogue and removes the seed's unchanged staged
   placeholders and the Amneo-vats modifier. Published Controlled rules are
   reported as skipped.
2. Wait for that run to finish, then preview **n26: remove published journal
   boon placeholders**. For the eleven unchanged published placeholders, the
   preview lists removal of each named modifier and its unused rule.
3. Run the published-placeholder cleanup and inspect its recorded report.
   Reopening the preview should show nothing to remove, apart from any retained
   candidates whose reason is listed.

Edited or archived rules, changed House conditions and modifiers used on other
content are retained. An unused rule can be removed even if its obsolete
modifier was already deleted. Rules referenced by content or player history
remain protected; their exact obsolete territory modifier can still be removed.

Both operations preview their writes with rollback and record their task result
in a Backfill. The published cleanup makes its changes in one transaction and
can be repeated. Territory holdings, their ledger history and baseline Income
are preserved. This cleanup does not add replacement boons.
