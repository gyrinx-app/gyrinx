"""Necromunda 2023 — the current game edition.

A plain namespace package, deliberately without an AppConfig: the Django apps
live in ``n23.core`` and ``n23.content``. Their app *labels* stay ``core`` and
``content`` (the default, taken from the last dotted component), so no database
table, migration record or content type changes when this package is renamed.

Edition packages depend on the platform (``gyrinx.*``) and never on each other.
"""
