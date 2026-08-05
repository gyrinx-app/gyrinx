"""Site-level platform models: the announcement banner, the impersonation log,
and the per-user notification inbox.

All three are about running Gyrinx, not about playing a game edition. The
inbox in particular is per-user, not per-edition: one badge, one list, one
broadcast, whatever editions the user has gangs in.

`Notification` refers to edition objects through generic `target` / `scope`
relations rather than ForeignKeys, so nothing here has a schema dependency on
an edition table. Its inbox *views* stay in the edition, under the `core:` URL
names they have always had.
"""
