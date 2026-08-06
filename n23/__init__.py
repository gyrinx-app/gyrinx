"""Necromunda 2023 — the current game edition.

A regular package (it has this ``__init__.py``, which setuptools' package
discovery needs) and deliberately without an AppConfig of its own: the Django
apps are ``n23.core`` and ``n23.content``. Both pin their app *label* to
``core``/``content``, which is why moving them out of ``gyrinx.`` changed no
table, migration record or content type.

Editions never import each other. They do depend on the platform (``gyrinx.*``)
— but note the reverse is also still true in a handful of places: ``gyrinx.urls``
mounts ``n23.core.urls``, and ``gyrinx.forms``/``api``/``maintenance``/``analytics``
reach into edition models. Those are the concrete blockers to standing up a
second edition, and are tracked on #2093 rather than fixed here. Background
tasks are no longer among them: this package declares its own routes in
``n23/core/tasks.py`` and the platform discovers them.
"""
