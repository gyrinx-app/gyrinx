"""Site-level platform models: the announcement banner and the impersonation log.

Both are about running Gyrinx, not about playing a game edition.

Notification deliberately is NOT here. It carries ForeignKeys to `core.List`
and `core.Campaign`, so moving it would give a platform model hard references
to edition tables. Generalising those two columns is design work, tracked
separately.
"""
